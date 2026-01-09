from typing import Optional
from sqlalchemy.future import select
from app.core.database import AsyncSessionLocal
from app.models.system import Webhook
from app.core.log_utils import get_logger

logger = get_logger("config")

async def get_configured_webhook(task_name: str) -> Optional[str]:
    """
    获取任务配置的 Webhook URL
    优先匹配 task_name，如果没有则查找 default
    """
    async with AsyncSessionLocal() as session:
        try:
            # 查找针对该任务的活跃 Webhook
            stmt = select(Webhook).where(
                Webhook.task_name == task_name,
                Webhook.is_active == True
            )
            result = await session.execute(stmt)
            webhook = result.scalars().first()
            
            if webhook:
                return webhook.url
                
            return None
        except Exception as e:
            logger.error(f"Failed to fetch webhook config for {task_name}: {e}")
            return None
