import os
import logging
import sys
import shutil
import time
from pathlib import Path
from logging import FileHandler
from app.core.config import config
from pythonjsonlogger import jsonlogger

# 环境变量控制
LOG_FORMAT = os.getenv("LOG_FORMAT", "text").lower() # text 或 json
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "true").lower() == "true"

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    自定义 JSON Formatter，统一字段名称
    """
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        
        # 统一时间字段为 timestamp
        if not log_record.get('timestamp'):
            log_record['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
        
        # 统一日志级别字段
        if log_record.get('level'):
            log_record['level'] = log_record['level'].upper()
        else:
            log_record['level'] = record.levelname

# 定义 Formatter
if LOG_FORMAT == "json":
    FORMATTER = CustomJsonFormatter(
        "%(timestamp)s %(level)s %(name)s %(message)s"
    )
else:
    # 保持原有的文本格式，增加一点颜色（如果在控制台）
    FORMATTER = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

# 基础配置
from app.core.config import LOG_DIR
if LOG_TO_FILE:
    LOG_DIR.mkdir(exist_ok=True)
    BACKUP_DIR = LOG_DIR / "backup"
    BACKUP_DIR.mkdir(exist_ok=True)

class ArchiveRotatingFileHandler(FileHandler):
    """
    自定义日志轮转 Handler
    当文件超过指定大小时，将其移动到 backup 目录并按时间戳重命名
    """
    def __init__(self, filename, mode='a', encoding='utf-8', delay=False):
        super().__init__(filename, mode, encoding, delay)
        self.filename = filename
        # 动态读取配置，默认 5MB
        config_mb = int(config.get("LOG_MAX_BYTES", 5))
        self.max_bytes = config_mb * 1024 * 1024

    def emit(self, record):
        try:
            super().emit(record)
            if self.shouldRollover(record):
                self.doRollover()
        except Exception:
            self.handleError(record)

    def shouldRollover(self, record):
        if self.stream is None:
            return False
        try:
            self.stream.seek(0, 2)
            if self.stream.tell() >= self.max_bytes:
                return True
        except Exception:
            pass
        return False

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        
        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        log_path = Path(self.baseFilename)
        backup_name = f"{log_path.stem}-{timestamp}{log_path.suffix}"
        backup_path = BACKUP_DIR / backup_name
        
        try:
            if log_path.exists():
                shutil.move(str(log_path), str(backup_path))
        except Exception as e:
            sys.stderr.write(f"Log rotation failed: {e}\n")

        if not self.delay:
            self.stream = self._open()

def get_logger(name: str):
    logger = logging.getLogger(name)
    
    # 设置日志级别
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    if not logger.handlers:
        # 1. 控制台输出 (Stdout) - 容器环境的核心
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(FORMATTER)
        logger.addHandler(console_handler)
        
        # 2. 文件输出 (可选)
        if LOG_TO_FILE:
            file_path = LOG_DIR / f"{name}.log"
            file_handler = ArchiveRotatingFileHandler(str(file_path))
            file_handler.setFormatter(FORMATTER)
            logger.addHandler(file_handler)
            
    return logger
