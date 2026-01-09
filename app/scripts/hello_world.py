from app.scripts.base import ScriptContext
import asyncio

async def run(context: ScriptContext):
    name = context.get_arg("name", "World")
    context.log(f"Hello from sandbox, {name}!")
    context.log(f"My working directory is {context.work_dir}")
    
    # 模拟工作
    await asyncio.sleep(15)
    
    return {
        "greeting": f"Hi {name}",
        "status": "ok"
    }
