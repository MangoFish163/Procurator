import asyncio
from app.core.log_utils import get_logger

logger = get_logger("demo_script")

async def run(data: dict):
    """
    这是一个自定义脚本示例
    :param data: 任务参数，例如 {"name": "Alice", "age": 18}
    """
    name = data.get("name", "Stranger")
    logger.info(f"Demo script started for {name}")
    
    # 模拟耗时操作
    await asyncio.sleep(3)
    
    logger.info(f"Demo script finished for {name}")
    
    return {
        "status": "success",
        "message": f"Hello, {name}! Your task is done.",
        "processed_data": data
    }
