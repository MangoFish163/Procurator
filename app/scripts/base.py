import os
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class ScriptContext:
    """
    脚本执行上下文
    提供脚本运行所需的环境信息和工具
    """
    # 任务 ID
    task_id: str
    # 传入参数
    args: Dict[str, Any]
    # 临时工作目录 (绝对路径)
    work_dir: str
    
    def get_arg(self, key: str, default: Any = None) -> Any:
        return self.args.get(key, default)

    def log(self, message: str):
        """
        标准输出日志，会被主进程捕获
        """
        print(f"[SCRIPT_LOG] {message}", flush=True)

    @property
    def output_file(self) -> str:
        """
        脚本结果输出文件路径
        """
        return os.path.join(self.work_dir, "output.json")

    def save_result(self, result: Dict[str, Any]):
        """
        保存脚本执行结果
        """
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
