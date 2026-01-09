import time
import asyncio
import httpx
from typing import List, Dict, Any

async def ping(data: dict):
    return "pong"

async def doc_example(data: dict):
    return "Hello World"

async def proxy_forward(data: dict):
    """
    异步并发转发 HTTP 请求 (简单模式：相同 Payload 发往多个 URL)
    """
    urls: List[str] = data.get("urls", [])
    payload: Dict[str, Any] = data.get("data", {})
    headers: Dict[str, str] = data.get("headers", {})
    timeout: int = int(data.get("timeout", 5))
    
    if not urls:
        return {"count": 0, "results": []}

    # 默认 Content-Type
    if "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    results = []
    
    async def _fetch(client, url):
        start_time = time.time()
        try:
            resp = await client.post(url, json=payload, headers=headers)
            duration = int((time.time() - start_time) * 1000)
            
            # 尝试解析 JSON 响应
            try:
                resp_data = resp.json()
            except Exception:
                resp_data = resp.text[:500]  # 截断过长的文本响应

            return {
                "url": url,
                "status": resp.status_code,
                "ok": resp.is_success,
                "response": resp_data,
                "duration_ms": duration
            }
        except httpx.TimeoutException:
            return {
                "url": url,
                "status": 0,
                "ok": False,
                "error": "timeout",
                "duration_ms": int((time.time() - start_time) * 1000)
            }
        except Exception as e:
            return {
                "url": url,
                "status": 0,
                "ok": False,
                "error": str(e),
                "duration_ms": int((time.time() - start_time) * 1000)
            }

    async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
        tasks = [_fetch(client, url) for url in urls]
        results = await asyncio.gather(*tasks)

    success_count = sum(1 for r in results if r.get("ok"))
    
    return {
        "count": len(results),
        "success": success_count,
        "failed": len(results) - success_count,
        "results": results
    }

async def proxy_multi_forward(data: dict):
    """
    异步并发转发 HTTP 请求 (高级模式：每个请求可独立定义 URL/Method/Data/Headers)
    taskData: {
        "tasks": [
            {"url": "...", "method": "POST", "data": {...}, "headers": {...}},
            ...
        ],
        "timeout": 5
    }
    """
    sub_tasks: List[Dict] = data.get("tasks", [])
    global_timeout: int = int(data.get("timeout", 5))
    
    if not sub_tasks:
        return {"count": 0, "results": []}

    results = []
    
    async def _execute_single(client, task_item):
        url = task_item.get("url")
        method = task_item.get("method", "POST").upper()
        payload = task_item.get("data")
        headers = task_item.get("headers", {})
        
        if not url:
            return {"url": None, "ok": False, "error": "url_missing"}

        # 默认 Content-Type
        if "Content-Type" not in headers and method in ("POST", "PUT", "PATCH"):
            headers["Content-Type"] = "application/json"

        start_time = time.time()
        try:
            # 根据 payload 类型决定是 json 还是 params
            kwargs = {"headers": headers}
            if method in ("GET", "DELETE"):
                if payload: kwargs["params"] = payload
            else:
                if payload: kwargs["json"] = payload

            resp = await client.request(method, url, **kwargs)
            duration = int((time.time() - start_time) * 1000)
            
            try:
                resp_data = resp.json()
            except Exception:
                resp_data = resp.text[:500]

            return {
                "url": url,
                "method": method,
                "status": resp.status_code,
                "ok": resp.is_success,
                "response": resp_data,
                "duration_ms": duration
            }
        except httpx.TimeoutException:
            return {
                "url": url,
                "method": method,
                "status": 0,
                "ok": False,
                "error": "timeout",
                "duration_ms": int((time.time() - start_time) * 1000)
            }
        except Exception as e:
            return {
                "url": url,
                "method": method,
                "status": 0,
                "ok": False,
                "error": str(e),
                "duration_ms": int((time.time() - start_time) * 1000)
            }

    async with httpx.AsyncClient(timeout=global_timeout, verify=False) as client:
        tasks = [_execute_single(client, item) for item in sub_tasks]
        results = await asyncio.gather(*tasks)

    success_count = sum(1 for r in results if r.get("ok"))
    
    return {
        "count": len(results),
        "success": success_count,
        "failed": len(results) - success_count,
        "results": results
    }
