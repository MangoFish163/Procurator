import os
import sys
# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
import uvicorn
from dotenv import load_dotenv
import psutil
import socket
import time

# 加载环境变量
load_dotenv()


def free_port(port: int):
    """
    释放指定端口 (仅在非容器环境下执行)
    """
    # 如果是在 Docker 容器中（通常没有 psutil 或者不应该杀进程），跳过
    if os.getenv("CONTAINER_ENV") == "true":
        return

    try:
        for conn in psutil.net_connections():
            if conn.laddr.port == port:
                if conn.pid == 0:
                    continue
                try:
                    p = psutil.Process(conn.pid)
                    print(f"⚠️  [DevTools] 端口 {port} 被进程 {p.name()} (PID: {conn.pid}) 占用，正在终止...")
                    p.terminate()
                    p.wait(timeout=3)
                    print(f"✅ [DevTools] 已释放端口 {port}")
                except Exception as e:
                    print(f"❌ [DevTools] 释放端口 {port} 失败: {e}")
    except Exception as e:
        # psutil 在某些环境可能权限不足，忽略
        pass


def _reload_excludes():
    # 排除日志、数据文件夹以及所有任务配置文件夹，防止循环重载
    # 在 Windows 下, uvicorn 的 reload_excludes 建议使用相对于 cwd 的路径
    excludes = [
        "logs/*", 
        "data/*", 
        "queues/*.py",
        "*.log",
        "__pycache__/*",
        ".git/*",
        ".venv/*"
    ] 
    if os.getenv("SERVER_RELOAD_EXCLUDE_SCRIPTS", "0") == "1":
        excludes.append("scripts/*")
    return excludes


def main():
    host = os.getenv("SERVER_HOST", "127.0.0.1")
    # 优先读取环境变量，默认回退到 50002
    port = int(os.getenv("SERVER_PORT", "50002"))
    
    # 打印开发环境提示
    print("\n" + "="*60)
    print("🚀 Procurator Local Development Server")
    print(f"📍 Address: http://{host}:{port}")
    print("💡 Tip: Use 'serve.py' for local dev, 'Docker' for production.")
    print("="*60 + "\n")

    # 启动前释放端口 (仅限开发环境)
    free_port(port)
    
    # 开发环境默认开启 reload，方便调试
    # 生产环境通常设置 SERVER_RELOAD=0
    reload_enabled = os.getenv("SERVER_RELOAD", "1") == "1"
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        reload_delay=0.3,
        reload_excludes=_reload_excludes(),
        log_level=os.getenv("SERVER_LOG_LEVEL", "info"),
        access_log=os.getenv("SERVER_ACCESS_LOG", "1") == "1",
        workers=1,
    )


if __name__ == "__main__":
    main()
