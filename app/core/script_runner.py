import asyncio
import json
import os
import shutil
import uuid
from pathlib import Path
from app.core.config import config
from app.core.log_utils import get_logger

logger = get_logger("script_runner")

class ScriptRunner:
    _instance = None
    
    def __init__(self):
        # 限制并发数
        max_concurrent = int(config.get("MAX_CONCURRENT_SCRIPTS", 3))
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        # 超时时间
        self.timeout = int(config.get("SCRIPT_TIMEOUT_SECONDS", 300))
        
        # 临时目录根路径
        self.temp_root = Path(__file__).parent.parent.parent / "data" / "temp_scripts"
        self.temp_root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = ScriptRunner()
        return cls._instance

    async def execute(self, script_name: str, args: dict):
        """
        执行脚本的主入口
        """
        task_id = str(uuid.uuid4())
        work_dir = self.temp_root / task_id
        
        # 1. 申请信号量
        async with self.semaphore:
            logger.info(f"Script {script_name} ({task_id}) acquired semaphore. Preparing execution...")
            
            try:
                # 2. 创建独立工作空间
                work_dir.mkdir(exist_ok=True)
                
                # 3. 构造子进程命令
                # 使用当前 Python 解释器
                python_exe = sys.executable
                
                # 包装器路径
                wrapper_path = Path(__file__).parent.parent / "scripts" / "wrapper.py"
                
                # 将 args 写入文件
                input_file = work_dir / "input.json"
                with open(input_file, "w", encoding="utf-8") as f:
                    json.dump(args, f, ensure_ascii=False)

                cmd = [
                    python_exe,
                    str(wrapper_path),
                    script_name,
                    task_id,
                    str(work_dir.absolute()),
                    str(input_file.absolute())  # 传递文件路径而不是 JSON 字符串
                ]
                
                logger.info(f"Executing: {' '.join(cmd)}")

                # 4. 启动子进程 (改为同步 Popen + run_in_executor)
                env = os.environ.copy()
                project_root = Path(__file__).parent.parent.parent
                env["PYTHONIOENCODING"] = "utf-8"
                
                # 准备日志文件
                log_dir = project_root / "app" / "scripts" / "logs"
                log_dir.mkdir(exist_ok=True)
                log_file_path = log_dir / f"{script_name}_{task_id}.log"
                
                def _run_sync():
                    import subprocess
                    with open(log_file_path, "wb") as log_file:
                        log_file.write(f"[Main] Starting script {script_name} via Popen...\n".encode("utf-8"))
                        log_file.flush()
                        
                        process = subprocess.Popen(
                            cmd,
                            stdout=log_file,
                            stderr=log_file,
                            env=env,
                            # Windows 下不设置 close_fds=True 可能导致文件句柄继承问题
                            # 但在重定向到文件时通常不需要
                        )
                        
                        try:
                            exit_code = process.wait(timeout=self.timeout)
                            return exit_code
                        except subprocess.TimeoutExpired:
                            process.kill()
                            raise TimeoutError(f"Script timed out after {self.timeout}s")

                loop = asyncio.get_running_loop()
                try:
                    # 在线程池中运行同步阻塞的子进程调用
                    exit_code = await loop.run_in_executor(None, _run_sync)
                    
                    # 读取日志文件内容
                    log_content = ""
                    try:
                        with open(log_file_path, "r", encoding="utf-8") as f:
                            log_content = f.read().strip()
                    except Exception:
                        log_content = "[Failed to read log file]"

                    if exit_code != 0:
                        logger.error(f"Script {script_name} failed (code {exit_code}). Log: {log_content}")
                        err_msg = log_content if log_content else f"Unknown error (code {exit_code})"
                        raise Exception(f"Script execution failed: {err_msg}")
                    
                    logger.info(f"Script finished. Log: {log_content[:200]}...")
                    
                    # 6. 读取结果文件
                    output_file = work_dir / "output.json"
                    if output_file.exists():
                        with open(output_file, "r", encoding="utf-8") as f:
                            return json.load(f)
                    return {"status": "success", "msg": "No output data returned"}

                except TimeoutError as e:
                    logger.error(str(e))
                    raise Exception(str(e))


            finally:
                # 7. 清理工作空间
                if work_dir.exists():
                    try:
                        shutil.rmtree(work_dir)
                        logger.info(f"Cleaned up work dir: {work_dir}")
                    except Exception as e:
                        logger.error(f"Failed to clean work dir: {e}")

# 导出便捷函数
import sys
async def execute_script(data: dict):
    runner = ScriptRunner.get_instance()
    script_name = data.get("script_name")
    args = data.get("args", {})
    
    if not script_name:
        raise ValueError("script_name is required")
        
    return await runner.execute(script_name, args)
