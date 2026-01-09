import uuid
import time
import threading
from typing import Dict, Optional, Tuple
from app.core.metrics import TASK_ENQUEUED_TOTAL, TASK_QUEUE_SIZE
from app.core.config import config
from app.core.log_utils import get_logger

logger = get_logger("queue_manager")

class MemoryBackend:
    def __init__(self):
        self.tasks = {}
        self.queues = {"api": [], "script": []}
        self.lock = threading.Lock()

    def enqueue(self, queue_name: str, payload: dict) -> str:
        tid = str(uuid.uuid4())
        task_info = {
            "id": tid,
            "task": payload.get("task"),
            "status": "pending",
            "created_at": time.time(),
            "payload": payload,
            "queue": queue_name
        }
        
        with self.lock:
            if tid not in self.tasks:
                self.tasks[tid] = task_info
            
            if queue_name not in self.queues:
                self.queues[queue_name] = []
            self.queues[queue_name].append(tid)
            
            # Prometheus Metrics
            try:
                TASK_ENQUEUED_TOTAL.labels(queue=queue_name, task_name=payload.get("task", "unknown")).inc()
                TASK_QUEUE_SIZE.labels(queue=queue_name).inc()
            except Exception:
                pass
        
        return tid

    def dequeue(self, queue_name: str) -> Optional[Tuple[str, dict]]:
        with self.lock:
            if queue_name in self.queues and self.queues[queue_name]:
                tid = self.queues[queue_name].pop(0)
                
                # Prometheus Metrics
                try:
                    TASK_QUEUE_SIZE.labels(queue=queue_name).dec()
                except Exception:
                    pass

                task = self.tasks.get(tid)
                if task:
                    return tid, task["payload"]
        return None

    def mark_done(self, tid, payload=None):
        self.update_status(tid, "completed")

    def mark_failed(self, tid, error, payload=None):
        self.update_status(tid, "failed", error)

    def update_status(self, tid, status, error=None):
        with self.lock:
            if tid in self.tasks:
                self.tasks[tid]["status"] = status
                self.tasks[tid]["updated_at"] = time.time()
                if error:
                    self.tasks[tid]["error"] = error

    def get_task(self, tid):
        with self.lock:
            return self.tasks.get(tid)

class QueueManager:
    def __init__(self):
        self.backend_type = config.get("QUEUE_BACKEND", "memory").lower()
        self.backend = None
        
        if self.backend_type == "redis":
            try:
                from app.queues.backends.redis_stream import RedisStreamBackend
                self.backend = RedisStreamBackend()
                logger.info("Using RedisStreamBackend")
            except Exception as e:
                logger.error(f"Failed to init Redis backend: {e}, falling back to Memory")
                self.backend = MemoryBackend()
        else:
            self.backend = MemoryBackend()
            logger.info("Using MemoryBackend")

    def enqueue(self, queue_name: str, payload: dict) -> str:
        return self.backend.enqueue(queue_name, payload)

    def dequeue(self, queue_name: str) -> Optional[Tuple[str, dict]]:
        return self.backend.dequeue(queue_name)
    
    def mark_done(self, tid, payload=None):
        if hasattr(self.backend, "mark_done"):
            self.backend.mark_done(tid, payload)
    
    def mark_failed(self, tid, error, payload=None):
        if hasattr(self.backend, "mark_failed"):
            self.backend.mark_failed(tid, error, payload)
    
    def get_task(self, tid):
        if hasattr(self.backend, "get_task"):
            return self.backend.get_task(tid)
        return None
        
    def status(self, tid):
        # 兼容旧 API
        info = self.get_task(tid)
        if info:
            return info.get("status", "unknown")
        return "unknown"

    def mark_done(self, tid, payload=None):
        # 传递 payload 以便 Redis Backend 进行 ACK
        if hasattr(self.backend, "mark_done"):
            # 检查 backend 方法签名，是否支持 payload
            # MemoryBackend 也更新了签名支持 payload
            self.backend.mark_done(tid, payload)
        else:
            # 兼容旧接口
            self.backend.mark_done(tid)

    def mark_failed(self, tid, error, payload=None):
        if hasattr(self.backend, "mark_failed"):
            self.backend.mark_failed(tid, error, payload)
        else:
            self.backend.mark_failed(tid, error)

    def status(self, tid):
        task = self.backend.get_task(tid)
        return task["status"] if task else "unknown"
    
    def get_task(self, tid):
        return self.backend.get_task(tid)

queue_manager = QueueManager()
