import sys
import os
import json
import importlib.util
import asyncio
import traceback
from pathlib import Path

# 强制设置 stdout/stderr 编码为 utf-8 (Windows 下尤其重要)
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 将项目根目录加入 path，确保能 import app.*
# 注意：虽然 script_runner 已经设置了 PYTHONPATH，这里保留作为双重保险
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.scripts.base import ScriptContext

async def main():
    try:
        if len(sys.argv) < 5:
            print(f"Usage: python -m app.scripts.wrapper <script_name> <task_id> <work_dir> <args_json>. Got: {len(sys.argv)}", file=sys.stderr)
            sys.exit(1)

        script_name = sys.argv[1]
        task_id = sys.argv[2]
        work_dir = sys.argv[3]
        input_file = sys.argv[4]  # 现在是文件路径
        
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                args = json.load(f)
        except Exception as e:
            print(f"Wrapper error: Failed to read input JSON from {input_file}: {e}", file=sys.stderr)
            sys.exit(1)

        # 构造上下文
        ctx = ScriptContext(task_id=task_id, args=args, work_dir=work_dir)

        # 动态加载脚本
        # 脚本文件应位于 app/scripts/<script_name>.py
        script_path = Path(__file__).parent / f"{script_name}.py"
        if not script_path.exists():
            print(f"Wrapper error: Script file not found: {script_path}", file=sys.stderr)
            sys.exit(1)

        try:
            spec = importlib.util.spec_from_file_location(script_name, script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            if not hasattr(module, "run"):
                print(f"Wrapper error: Script {script_name} must have a 'run(context)' async function", file=sys.stderr)
                sys.exit(1)
                
            # 执行脚本
            print(f"--- Script {script_name} started ---", flush=True)
            if asyncio.iscoroutinefunction(module.run):
                result = await module.run(ctx)
            else:
                result = module.run(ctx)
                
            # 保存结果
            # 只有当 result 显式为 None 时才使用默认值
            # 允许返回 [], {}, 0, False 等 Falsy 值
            if result is None:
                result = {"status": "success"}
            ctx.save_result(result)
            print(f"--- Script {script_name} finished ---", flush=True)

        except Exception as e:
            # 捕获所有业务逻辑异常，打印堆栈
            print(f"Wrapper error during execution: {e}", file=sys.stderr)
            traceback.print_exc()
            sys.exit(2)
            
    except Exception as e:
        # 捕获最外层异常
        print(f"Wrapper critical error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(3)

if __name__ == "__main__":
    asyncio.run(main())
