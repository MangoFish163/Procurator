import time
import threading

class RateLimiter:
    def __init__(self):
        self.windows = {}
        self.lock = threading.Lock()

    def allow(self, key: str, max_req: int, window: int) -> bool:
        with self.lock:
            now = time.time()
            if key not in self.windows:
                self.windows[key] = []
            
            # 清理过期的请求时间戳
            self.windows[key] = [t for t in self.windows[key] if now - t < window]
            
            if len(self.windows[key]) < max_req:
                self.windows[key].append(now)
                return True
            return False

rate_limiter = RateLimiter()
