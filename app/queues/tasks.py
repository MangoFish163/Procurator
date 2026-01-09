import importlib
import asyncio
from typing import Any, Dict
from app.core.log_utils import get_logger

logger = get_logger("tasks")

# 允许的任务列表 (模拟 task_map)
ALLOWED_TASKS = {
    "feishu_get_token": "app.services.feishu.get_token",
    "feishu_set_token": "app.services.feishu.set_token",
    "system.ping": "app.services.system.ping",
    "_doc_example": "app.services.system.doc_example",
    "proxy_forward": "app.services.system.proxy_forward",
    "proxy_multi_forward": "app.services.system.proxy_multi_forward",
    "script.execute": "app.core.script_runner.execute_script",
    "demo_script": "app.services.demo_script.run"
}

def is_allowed(task: str, queue: str, role: str) -> bool:
    # 鉴权逻辑
    if task in ALLOWED_TASKS or task.startswith("test."):
        return True
    return False

def list_tasks():
    return list(ALLOWED_TASKS.keys())

def list_scripts():
    return []

def validate_task_input(task: str, data: dict) -> dict:
    # 透传，实际应调用 Pydantic 模型
    return data

def get_task_webhook(task: str):
    return None

def get_task_async_mode(task: str):
    return "Free"

async def handle_task(task_name: str, task_data: dict) -> Any:
    logger.info(f"Handling task: {task_name}")
    
    # if task_name == "proxy_forward":
    #     # Proxy forward async logic - placeholder implementation
    #     # In real app, this would use httpx to forward request
    #     return {"status": "forwarded (mock)"}

    module_path_str = ALLOWED_TASKS.get(task_name)
    if not module_path_str:
        if task_name.startswith("test."):
             return f"Test task {task_name} executed"
        raise ValueError(f"Task {task_name} handler not found")

    try:
        module_name, func_name = module_path_str.rsplit(".", 1)
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        
        if asyncio.iscoroutinefunction(func):
            return await func(task_data)
        else:
            return func(task_data)
    except ImportError as e:
        logger.error(f"Import error for {task_name}: {e}")
        raise
    except AttributeError as e:
        logger.error(f"Function not found for {task_name}: {e}")
        raise
    except Exception as e:
        logger.error(f"Execution failed for {task_name}: {e}")
        raise
