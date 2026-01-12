import asyncio
import time
from typing import Optional, List

from app.core.log_utils import get_logger
from app.queues.task_queue import queue_manager
from app.queues.tasks import handle_task
from app.infra.webhook import notify
from app.services.task_persistence import persist_task_start, persist_task_finish


class Worker:
    def __init__(self):
        self.logger = get_logger("worker")
        self._tasks: List[asyncio.Task] = []
        self._running = False

    def start(self, queues: List[str]):
        if self._running:
            return
        self._running = True
        loop = asyncio.get_event_loop()
        for q in queues:
            task = loop.create_task(self._run(q))
            self._tasks.append(task)
        self.logger.info("Workers started for %s", ",".join(queues))

    async def stop(self):
        self._running = False
        if not self._tasks:
            return
        
        self.logger.info("Stopping workers...")
        # 取消所有任务
        for task in self._tasks:
            task.cancel()
        
        # 等待所有任务结束
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self.logger.info("Workers stopped")

    async def _run(self, queue_name: str):
        while self._running:
            try:
                # 使用 to_thread 运行同步的 dequeue 避免阻塞事件循环
                item = await asyncio.to_thread(queue_manager.dequeue, queue_name)
                if not item:
                    await asyncio.sleep(0.5)
                    continue
                
                tid, payload = item
                try:
                    # 记录任务开始
                    await persist_task_start(tid, self.worker_id)
                    
                    # handle_task 现在是 async def，所以需要 await
                    res = await handle_task(payload.get("task"), payload.get("taskData", {}))
                    
                    # 同步的标记操作也放入 to_thread
                    await asyncio.to_thread(queue_manager.mark_done, tid)
                    
                    # 记录任务完成 (DB)
                    await persist_task_finish(tid, "completed", result=res, worker_id=self.worker_id)
                    
                    try:
                        notify(tid, payload.get("task"), payload, "done", result=res, error=None)
                    except Exception:
                        pass
                    self.logger.info("Task %s done", tid)
                except Exception as e:
                    try:
                        await asyncio.to_thread(queue_manager.mark_failed, tid, str(e), payload)
                    except Exception:
                        pass
                    
                    final = False
                    try:
                        info = await asyncio.to_thread(queue_manager.get_task, tid)
                        if info:
                            st = info.get("status")
                            rc = int(info.get("retry_count") or 0)
                            mr = int(info.get("max_retries") or 0)
                            final = (st in ("dead", "failed")) and (rc >= mr)
                        else:
                            # 注意：这里原代码调用了 queue_manager.status，但 QueueManager 类里似乎只有 status 方法在 backend.get_status
                            # 统一使用 get_status 或 status
                            st = await asyncio.to_thread(queue_manager.status, tid)
                            final = st in ("dead", "failed")
                    except Exception:
                        final = True
                    
                    # 记录任务失败 (DB)
                    # 只有当任务彻底失败（进入 dead/failed 且不再重试）或者是每次失败都记录？
                    # 建议每次失败都记录，status 为 failed，如果重试会再次变成 processing
                    # 但 persist_task_finish 会覆盖状态。
                    # 如果只是临时失败，QueueManager 里的状态可能是 queued (for retry)。
                    # 这里我们简单起见，记录当前错误。
                    await persist_task_finish(tid, "failed", error=str(e), worker_id=self.worker_id)
                    
                    if final:
                        try:
                            notify(tid, payload.get("task"), payload, "failed", result=None, error=str(e))
                        except Exception:
                            pass
                    
                    # TASK_FAILED_TOTAL.labels(queue=queue_name, task_name=task_name, error_type=type(e).__name__).inc()
                    self.logger.error("Task %s failed: %s", tid, e)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Worker loop error in %s: %s", queue_name, e)
                await asyncio.sleep(1)


worker = Worker()
