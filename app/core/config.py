import os
import json
import threading
import time
from pathlib import Path


class Config:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.env_file = self.root / ".env"
        self._lock = threading.Lock()
        self._env = {}
        self._json = {}
        # 记录所有已加载配置文件的修改时间
        self._mtimes = {}
        self._load()
        if (os.getenv("CONFIG_HOT_RELOAD", "1") == "1"):
            t = threading.Thread(target=self._watcher, daemon=True)
            t.start()

    def _load_env(self):
        data = {}
        if self.env_file.exists():
            try:
                for raw in self.env_file.read_text(encoding="utf-8").splitlines():
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        data[k.strip()] = v.strip()
            except Exception:
                pass
        return data

    def _load_all_json(self):
        """扫描根目录下所有 .json 文件并合并"""
        combined = {}
        mtimes = {}
        for json_path in self.root.glob("*.json"):
            # 排除 package.json 等非业务配置文件（可选）
            if json_path.name in ["package.json", "package-lock.json"]:
                continue
            try:
                content = json.loads(json_path.read_text(encoding="utf-8"))
                if isinstance(content, dict):
                    combined.update(content)
                mtimes[str(json_path)] = json_path.stat().st_mtime
            except Exception:
                pass
        return combined, mtimes

    def _load(self):
        with self._lock:
            self._env = self._load_env()
            json_data, json_mtimes = self._load_all_json()
            self._json = json_data
            self._mtimes = {
                "env": self.env_file.stat().st_mtime if self.env_file.exists() else 0.0,
                **json_mtimes
            }

    def reload(self):
        self._load()

    def get(self, key: str, default=None):
        # 优先级: .env > os.environ > 默认值
        val = self._env.get(key)
        if val is None:
            val = os.getenv(key)
        return val if val is not None else default

    def get_json(self, *keys, default=None):
        """支持多级 Key 获取，例如 get_json('section', 'subsection', 'key')"""
        obj = self._json
        for k in keys:
            if isinstance(obj, dict) and k in obj:
                obj = obj[k]
            else:
                return default
        return obj

    def _watcher(self):
        while True:
            time.sleep(5) # 稍微增加轮询间隔减少 IO
            try:
                env_m = self.env_file.stat().st_mtime if self.env_file.exists() else 0.0
                # 检查环境变量文件是否更新
                needs_reload = (env_m != self._mtimes.get("env"))
                
                # 检查所有已知的 JSON 文件
                if not needs_reload:
                    for json_path_str, last_mtime in self._mtimes.items():
                        if json_path_str == "env": continue
                        p = Path(json_path_str)
                        if not p.exists() or p.stat().st_mtime != last_mtime:
                            needs_reload = True
                            break
                
                if needs_reload:
                    self.reload()
            except Exception:
                pass

# 初始化配置单例
# 项目根目录: app/core/config.py -> app/core -> app -> root
PROJECT_ROOT = Path(__file__).parent.parent.parent
config = Config(PROJECT_ROOT)

# --- 核心路径配置 (Path Configuration) ---
# 优先从环境变量读取，默认为项目根目录下的 data/logs
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
LOG_DIR = Path(os.getenv("LOG_DIR", PROJECT_ROOT / "logs"))

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 衍生路径
DB_PATH = DATA_DIR / "app.db"
