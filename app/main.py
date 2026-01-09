import sys
import os
import time
import psutil

from app.core.config import config
from app.core.security import IPAllowlistMiddleware, verify_token, resolve_role, token_dependency
from app.queues.task_queue import queue_manager
from app.worker import worker
from app.core.log_utils import get_logger
from app.queues.tasks import (
    is_allowed, 
    list_tasks, 
    validate_task_input, 
    list_scripts, 
    get_task_webhook,
    get_task_async_mode,
    handle_task
)
from app.infra.rate_limiter import rate_limiter
from app.infra.feishu_client import get_tenant_access_token
from app.routers import logs, dlq

from fastapi import FastAPI, Header, Depends, Request
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List, Dict
import subprocess
import platform
import re
import signal
from contextlib import asynccontextmanager



def to_json_compatible(obj):
    """
    递归将对象转换为 JSON 兼容的基础类型。
    特别处理 Pydantic 的 HttpUrl 等类型。
    """
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "dict"):
        return obj.dict()
    if isinstance(obj, list):
        return [to_json_compatible(item) for item in obj]
    if isinstance(obj, dict):
        return {k: to_json_compatible(v) for k, v in obj.items()}
    if hasattr(obj, "__str__") and not isinstance(obj, (int, float, bool, type(None), str)):
        return str(obj)
    return obj


def set_custom_process_name(process_name):
    """
    仅在Linux系统下设置进程名,Windows系统不执行,且捕获所有异常避免报错
    :param process_name: 自定义进程名
    """
    if sys.platform == 'linux':
        try:
            import setproctitle
            setproctitle.setproctitle(process_name)
            print(f"Linux系统,当前进程名已设置为: {process_name}")
        except ImportError:
            print(f"警告⚠️: Linux系统:未安装setproctitle库,请执行 pip install setproctitle 安装")
        except Exception as e:
            print(f"警告⚠️: Linux系统:设置进程名失败,错误信息：{e}")

# 设置进程名（用于服务器定位异常）
set_custom_process_name("ParcelInformationTracking")

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        worker.start(["api", "script"])
        yield
    finally:
        try:
            await worker.stop()
        except Exception:
            pass

app = FastAPI(lifespan=lifespan)
app.add_middleware(IPAllowlistMiddleware)
app.include_router(logs.router)
app.include_router(dlq.router, dependencies=[Depends(token_dependency)])
logger = get_logger("api")

DEMO_WEBHOOK_EVENTS: list[dict] = []

class DispatchRequest(BaseModel):
    task: str
    taskData: dict
    queue: Optional[str] = "api"
    maxRetries: Optional[int] = 0
    webhook: Optional[str] = None
    async_mode: Optional[bool] = Field(True, alias="async")

@app.get("/ping")
def ping():
    return {"status": "ok"}

@app.get("/metrics")
def metrics():
    from app.core.metrics import get_metrics_data
    from starlette.responses import Response
    return Response(get_metrics_data(), media_type="text/plain")

@app.post("/dispatch")
async def dispatch(req: DispatchRequest, ident=Depends(token_dependency)):
    # 拦截示例任务，直接返回 Hello World
    if req.task == "_doc_example":
        return {"code": 200, "data": "Hello World"}

    # 兼容性处理：如果 taskData 中包含 webhook 或 async，且顶层未指定，则提取到顶层
    if isinstance(req.taskData, dict):
        if not req.webhook and "webhook" in req.taskData:
            req.webhook = req.taskData["webhook"]
        if "async" in req.taskData:
            req.async_mode = req.taskData["async"]

    payload = {"task": req.task, "taskData": req.taskData}
    src = req.queue or "api"
    if not is_allowed(req.task, src, ident.get("role")):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Task not allowed or unknown")
    
    # 确定 webhook: 优先使用请求中的，否则使用任务配置中的 (DB)
    # 注意：这里的逻辑确保了如果 req.webhook 存在（用户指定），则短路求值，不会查询 DB
    webhook = req.webhook
    if not webhook:
        webhook = await get_configured_webhook(req.task)
        # 如果 DB 也没配，尝试从旧的 tasks.py 获取 (兼容旧逻辑，虽然目前是返回 None)
        if not webhook:
            webhook = get_task_webhook(req.task)
            
    if webhook:
        payload["webhook"] = webhook

    try:
        validated_data = validate_task_input(req.task, req.taskData)
        # 如果返回的是 Pydantic 模型，转换为字典以确保 JSON 可序列化
        if hasattr(validated_data, "model_dump"):
            payload["taskData"] = validated_data.model_dump(mode="json")
        elif hasattr(validated_data, "dict"):
            payload["taskData"] = validated_data.dict()
        else:
            payload["taskData"] = validated_data
    except Exception as e:
        logger.error("Validation failed for task %s: %s", req.task, e)
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Invalid task params: {e}")
    
    # 速率限制
    max_req = int(config.get("RATE_LIMIT_MAX", 30))
    win = int(config.get("RATE_LIMIT_WINDOW", 60))
    key = f"{src}:{req.task}:{ident.get('token') or ident.get('ip')}"
    if not rate_limiter.allow(key, max_req, win):
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail="Too Many Requests")

    # 确定执行模式 (Sync vs Async)
    # Must: 强制进入队列
    # Prohibited: 强制同步执行
    # Free: 根据请求参数决定
    task_async_config = get_task_async_mode(req.task)
    is_sync = False
    if task_async_config == "Prohibited":
        is_sync = True
    elif task_async_config == "Free":
        if req.async_mode is False:
            is_sync = True
    
    if is_sync:
        logger.info("Executing task %s synchronously", req.task)
        try:
            result = await handle_task(req.task, payload["taskData"])
            return {"accepted": True, "status": "completed", "result": result}
        except Exception as e:
            logger.error("Sync task %s failed: %s", req.task, e)
            return {"accepted": True, "status": "failed", "error": str(e)}

    # 异步排队逻辑
    if req.maxRetries and req.maxRetries > 0:
        payload["_max_retries"] = int(req.maxRetries)
    elif config.get("RETRY_MAX"):
        try:
            payload["_max_retries"] = int(config.get("RETRY_MAX"))
        except Exception:
            pass

    # 确保整个 payload 是 JSON 兼容的（处理 HttpUrl 等对象）
    payload = to_json_compatible(payload)
    tid = queue_manager.enqueue(src, payload)
    
    # 异步持久化到数据库 (Cold Storage)
    bg_tasks.add_task(persist_task_init, tid, src, req.task, payload)
    
    logger.info("Enqueued task %s to %s", tid, req.queue)
    return {"accepted": True, "task_id": tid}

@app.get("/task/{tid}", dependencies=[Depends(token_dependency)])
def task_status(tid: str):
    return {"status": queue_manager.status(tid)}

@app.get("/task/{tid}/detail", dependencies=[Depends(token_dependency)])
def task_detail(tid: str):
    from app.queues.task_queue import queue_manager as qm
    return qm.backend.get_task(tid)

@app.get("/tasks", dependencies=[Depends(token_dependency)])
def tasks_list():
    return {"tasks": list_tasks(), "scripts": list_scripts()}

@app.get("/feishu/token")
def feishu_token(ident=Depends(token_dependency)):
    role = ident.get("role")
    if role != "trusted":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Forbidden")
    max_req = int(config.get("RATE_LIMIT_MAX", 30))
    win = int(config.get("RATE_LIMIT_WINDOW", 60))
    key = f"feishu_token:{ident.get('token') or ident.get('ip')}"
    if not rate_limiter.allow(key, max_req, win):
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail="Too Many Requests")
    try:
        token, expires = get_tenant_access_token()
        return {"tenant_access_token": token, "expires_in": expires}
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Feishu token fetch failed")

@app.post("/demo/webhook")
def demo_webhook(payload: dict):
    try:
        DEMO_WEBHOOK_EVENTS.append(payload)
        return {"ok": True, "received": len(DEMO_WEBHOOK_EVENTS)}
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Webhook store failed")


@app.get("/demo/webhook/last")
def demo_webhook_last():
    try:
        return DEMO_WEBHOOK_EVENTS[-1] if DEMO_WEBHOOK_EVENTS else {}
    except Exception:
        return {}

class ProxyForwardRequest(BaseModel):
    urls: List[HttpUrl]
    data: dict
    mode: Optional[str] = "sync"
    timeout: Optional[int] = 3
    headers: Optional[Dict[str, str]] = None
    webhook: Optional[HttpUrl] = None
    queue: Optional[str] = "api"

@app.post("/proxy/forward")
def proxy_forward(req: ProxyForwardRequest, ident=Depends(token_dependency)):
    max_req = int(config.get("RATE_LIMIT_MAX", 30))
    win = int(config.get("RATE_LIMIT_WINDOW", 60))
    key = f"proxy_forward:{ident.get('token') or ident.get('ip')}"
    if not rate_limiter.allow(key, max_req, win):
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail="Too Many Requests")
    if (req.mode or "sync").lower() == "async":
        payload = {
            "task": "proxy_forward",
            "taskData": {
                "urls": [str(u) for u in req.urls],
                "data": req.data,
                "timeout": int(req.timeout or 3),
                "headers": req.headers or {},
            },
        }
        if req.webhook:
            payload["taskData"]["webhook"] = str(req.webhook)
        if req.queue:
            qn = req.queue
        else:
            qn = "api"
        try:
            maxr_cfg = config.get("RETRY_MAX")
            if maxr_cfg is not None:
                payload["_max_retries"] = int(maxr_cfg)
        except Exception:
            pass
        tid = queue_manager.enqueue(qn, payload)
        logger.info("Enqueued proxy_forward %s to %s", tid, qn)
        return {"accepted": True, "mode": "async", "task_id": tid}
    import json
    import time
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
    results = []
    ok = 0
    headers = req.headers or {}
    to = float(req.timeout or 3)
    for u in req.urls:
        url = str(u)
        t0 = time.time()
        body = json.dumps(req.data, ensure_ascii=False).encode("utf-8")
        reqobj = Request(url, data=body, headers={"Content-Type": "application/json", **headers}, method="POST")
        try:
            with urlopen(reqobj, timeout=to) as resp:
                code = int(resp.getcode())
                raw = resp.read()
                txt = raw.decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(txt)
                    item = {"url": url, "code": code, "ok": 200 <= code < 300, "response": parsed, "ms": int((time.time() - t0) * 1000)}
                except Exception:
                    item = {"url": url, "code": code, "ok": 200 <= code < 300, "text": txt[:200], "ms": int((time.time() - t0) * 1000)}
        except (URLError, HTTPError):
            item = {"url": url, "code": None, "ok": False, "error": "request_failed", "ms": int((time.time() - t0) * 1000)}
        if item.get("ok"):
            ok += 1
        results.append(item)
    return {"accepted": True, "mode": "sync", "count": len(results), "ok": ok, "failed": len(results) - ok, "results": results}

def free_port(port: int):
    system = platform.system().lower()
    pids = set()
    if system == "windows":
        try:
            ns = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
            for line in ns.stdout.splitlines():
                if f":{port} " in line:
                    parts = line.split()
                    if parts and parts[-1].isdigit():
                        pids.add(int(parts[-1]))
        except Exception:
            pass
        try:
            ps_cmd = f"(Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | Select-Object -Expand OwningProcess)"
            ps = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
            for s in ps.stdout.split():
                t = s.strip()
                if t.isdigit():
                    pids.add(int(t))
        except Exception:
            pass
    else:
        try:
            ss = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True)
            for line in ss.stdout.splitlines():
                if f":{port}" in line:
                    for m in re.findall(r"pid=(\d+)", line):
                        pids.add(int(m))
        except Exception:
            try:
                lsof = subprocess.run(["lsof", "-i", f":{port}", "-t"], capture_output=True, text=True)
                for line in lsof.stdout.splitlines():
                    s = line.strip()
                    if s.isdigit():
                        pids.add(int(s))
            except Exception:
                try:
                    fuser = subprocess.run(["fuser", "-n", "tcp", str(port)], capture_output=True, text=True)
                    for m in re.findall(r"(\d+)", fuser.stdout):
                        pids.add(int(m))
                except Exception:
                    pass
    failed: list[int] = []
    for pid in pids:
        if system == "windows":
            try:
                r = subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True, text=True)
                if r.returncode != 0:
                    failed.append(pid)
            except Exception:
                failed.append(pid)
            try:
                subprocess.run(["powershell", "-NoProfile", "-Command", f"try{{Stop-Process -Force -Id {pid}}}catch{{}}"], capture_output=True, text=True)
            except Exception:
                pass
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            if system != "windows":
                try:
                    r = subprocess.run(["kill", "-9", str(pid)], capture_output=True, text=True)
                    if r.returncode != 0:
                        failed.append(pid)
                except Exception:
                    failed.append(pid)
    if failed:
        logger.warning("警告⚠️: 端口 %s 清理失败的进程: %s", port, ",".join(str(x) for x in failed))

if __name__ == "__main__":
    import uvicorn
    PORT = 50002
    free_port(PORT)
    logger.info("启动FastAPI服务器")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
