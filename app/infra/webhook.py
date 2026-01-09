import requests
from app.core.log_utils import get_logger

logger = get_logger("webhook")

def notify(tid, task, payload, status, result=None, error=None):
    webhook = payload.get("webhook")
    if not webhook:
        return

    data = {
        "task_id": tid,
        "task": task,
        "status": status,
        "result": result,
        "error": error,
        "meta": payload.get("meta")
    }
    
    try:
        requests.post(webhook, json=data, timeout=5)
    except Exception as e:
        logger.error(f"Webhook notify failed for task {tid}: {e}")
