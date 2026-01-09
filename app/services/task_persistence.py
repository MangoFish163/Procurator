from sqlalchemy import update
from sqlalchemy.future import select
from datetime import datetime
from app.core.database import AsyncSessionLocal
from app.models.task import Task
from app.core.log_utils import get_logger

logger = get_logger("persistence")

async def persist_task_init(tid: str, queue: str, task_name: str, payload: dict):
    """
    任务入队时：创建初始记录
    """
    async with AsyncSessionLocal() as session:
        try:
            task = Task(
                id=tid,
                queue=queue,
                task_name=task_name,
                payload=payload,
                status="pending",
                created_at=datetime.now()
            )
            session.add(task)
            await session.commit()
            logger.debug(f"Persisted init task {tid}")
        except Exception as e:
            logger.error(f"Failed to persist task init {tid}: {e}")

async def persist_task_finish(tid: str, status: str, result: dict = None, error: str = None, worker_id: str = None):
    """
    任务完成/失败时：更新记录
    """
    async with AsyncSessionLocal() as session:
        try:
            # 尝试先查询，如果不存在（比如 Redis 里有但 DB 里没写入成功）则创建
            # 但标准流程应该是 persist_task_init 先执行。
            # 这里我们直接执行 update，如果记录不存在可能需要 fallback，
            # 不过考虑到 "异步写入" 可能有延迟，update 应该能找到。
            
            stmt = (
                update(Task)
                .where(Task.id == tid)
                .values(
                    status=status,
                    result=result,
                    error=error,
                    finished_at=datetime.now(),
                    worker_id=worker_id,
                    updated_at=datetime.now()
                )
            )
            res = await session.execute(stmt)
            
            if res.rowcount == 0:
                # 这是一个兜底：如果 init 写入失败或太慢，finish 时发现没有记录，则补录
                # 但这需要知道 task_name 等信息，而 finish 时只有 tid 和 result。
                # 这种情况下，我们可能只能记录 "未知任务" 或 忽略。
                # 为了简化，我们暂时只打印警告。
                logger.warning(f"Task {tid} not found in DB during finish update. Init might have failed or is slow.")
                
            await session.commit()
            logger.debug(f"Persisted finish task {tid} ({status})")
        except Exception as e:
            logger.error(f"Failed to persist task finish {tid}: {e}")

async def persist_task_start(tid: str, worker_id: str):
    """
    任务开始时：更新开始时间和 Worker ID
    """
    async with AsyncSessionLocal() as session:
        try:
            stmt = (
                update(Task)
                .where(Task.id == tid)
                .values(
                    status="processing",
                    started_at=datetime.now(),
                    worker_id=worker_id,
                    updated_at=datetime.now()
                )
            )
            await session.execute(stmt)
            await session.commit()
        except Exception as e:
            logger.error(f"Failed to persist task start {tid}: {e}")
