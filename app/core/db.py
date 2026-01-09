import sqlite3
from pathlib import Path
from typing import Optional


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(exist_ok=True)
        # 启用 check_same_thread=False 允许在多线程 Worker 中复用连接
        self.conn = sqlite3.connect(
            self.path, 
            check_same_thread=False, 
            isolation_level=None  # 自动提交模式，配合 WAL 性能更佳
        )
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")

    def cursor(self):
        return self.conn.cursor()

    def execute(self, sql: str, params: tuple = ()):
        return self.conn.execute(sql, params)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        from app.core.config import DB_PATH
        _db = Database(DB_PATH)
    return _db
