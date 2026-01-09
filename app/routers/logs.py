from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Dict
import os
from pathlib import Path
from datetime import datetime
from app.core.security import require_auth

router = APIRouter(
    prefix="/logs",
    tags=["Logs"],
    dependencies=[Depends(require_auth)]
)

LOG_DIR = Path(__file__).parent.parent.parent / "logs"

def _format_size(size_bytes: int) -> str:
    """
    将字节大小转换为人类可读格式
    """
    if size_bytes == 0:
        return "0 B"
    
    units = ("B", "KB", "MB", "GB", "TB")
    i = 0
    size = float(size_bytes)
    
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
        
    return f"{size:.2f} {units[i]}"

def _get_file_info(path: Path) -> Dict:
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path.relative_to(LOG_DIR)).replace("\\", "/"),
        "size": _format_size(stat.st_size),
        "size_bytes": stat.st_size,  # 保留原始字节数以便排序或精确计算
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "type": "file"
    }

@router.get("/list", response_model=List[Dict])
async def list_logs(backup: bool = False):
    """
    列出日志文件
    :param backup: 是否包含备份目录下的归档日志
    """
    files = []
    
    if not LOG_DIR.exists():
        return []

    # 当前活跃日志
    for p in LOG_DIR.glob("*.log"):
        files.append(_get_file_info(p))
        
    # 归档日志
    if backup:
        backup_dir = LOG_DIR / "backup"
        if backup_dir.exists():
            for p in backup_dir.glob("*.log"):
                info = _get_file_info(p)
                info["type"] = "backup"
                files.append(info)
                
    # 按修改时间倒序排列
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files

@router.get("/read")
async def read_log(filename: str, lines: int = 100):
    """
    读取日志内容
    :param filename: 文件名 (相对于 logs 目录，例如 'api.log' 或 'backup/api-2023...log')
    :param lines: 读取最后 N 行 (默认 100，最大 2000)
    """
    # 安全检查：防止目录遍历攻击
    if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
        raise HTTPException(status_code=400, detail="Invalid filename")
        
    file_path = LOG_DIR / filename
    
    # 再次确认文件确实在 LOG_DIR 下
    try:
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(LOG_DIR.resolve())):
             raise HTTPException(status_code=403, detail="Access denied")
    except Exception:
         raise HTTPException(status_code=400, detail="Invalid path")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")

    lines = min(lines, 2000) # 限制最大读取行数
    
    content = []
    try:
        # 使用 deque 实现高效 tail
        from collections import deque
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = list(deque(f, lines))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read log: {str(e)}")
        
    return {
        "filename": filename,
        "lines": len(content),
        "content": "".join(content)
    }
