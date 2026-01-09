import os
import sys
import time
import psutil
import subprocess
import signal
from app.core.config import config

def test_singleton_restart():
    prefix = "test_singleton"
    # 获取绝对路径，与 main.py 保持一致
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pid_file = os.path.join(base_dir, f".{prefix}.pid")
    
    # 清理旧环境
    if os.path.exists(pid_file):
        os.remove(pid_file)
    
    # 模拟启动第一个实例
    # 由于 main.py 会执行逻辑，我们直接在当前进程模拟这个逻辑，
    # 或者启动一个子进程
    
    print(f"--- 模拟启动第一个实例 (Prefix: {prefix}) ---")
    # 这里我们手动创建一个 '假' 的旧 PID 文件，指向一个还在运行的进程（比如当前进程的一个子进程）
    # 这样可以测试 terminate 逻辑
    dummy_proc = subprocess.Popen(["python", "-c", "import time; time.sleep(60)"])
    with open(pid_file, "w") as f:
        f.write(str(dummy_proc.pid))
    
    print(f"创建了假实例 PID: {dummy_proc.pid}")
    assert psutil.pid_exists(dummy_proc.pid)
    
    # 模拟启动第二个实例（通过子进程启动真正的 main.py）
    print("--- 启动第二个实例 (通过子进程运行 main.py) ---")
    
    # 确保环境变量传递给子进程
    env = os.environ.copy()
    env["PROJECT_PREFIX"] = prefix
    env["PYTHONPATH"] = base_dir
    
    # 使用 sys.executable 确保使用相同的 python 解释器
    print(f"--- 启动第二个实例 (PID: {os.getpid()}) ---")
    new_proc = subprocess.Popen([sys.executable, "main.py"], env=env, cwd=base_dir)
    
    # 给一点时间让新进程执行 ensure_unique_instance
    print("等待新进程执行单例检查...")
    time.sleep(5)
    
    # 验证第一个实例是否被终止
    exists = psutil.pid_exists(dummy_proc.pid)
    print(f"第一个实例 PID {dummy_proc.pid} 是否还存在: {exists}")
    
    # 停止新进程
    new_proc.terminate()
    
    # 验证 PID 文件是否更新（不再是旧的 PID 即可，因为 Windows 下 Popen 的 PID 可能与实际进程 PID 不一致）
    with open(pid_file, "r") as f:
        recorded_pid = int(f.read().strip())
    print(f"旧 PID: {dummy_proc.pid}, 新记录的 PID: {recorded_pid}")
    
    # 停止新进程
    new_proc.terminate()
    dummy_proc.terminate() # 以防万一
    
    assert not exists, "旧进程应该被终止了"
    assert recorded_pid != dummy_proc.pid, "PID 文件应该已更新"
    assert recorded_pid > 0, "记录的 PID 应该大于 0"
    
    print("\n[✓] Singleton Restart Logic Verified via Subprocess!")
    
    # 清理
    if os.path.exists(pid_file):
        os.remove(pid_file)

if __name__ == "__main__":
    try:
        test_singleton_restart()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[✗] Singleton Verification Failed: {e}")
