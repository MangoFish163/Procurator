import redis
from app.core.config import config
from app.core.log_utils import get_logger

logger = get_logger("redis")

class RedisClient:
    _pool = None

    @classmethod
    def get_client(cls):
        if cls._pool is None:
            redis_url = config.get("REDIS_URL", "redis://localhost:6379/0")
            try:
                cls._pool = redis.ConnectionPool.from_url(
                    redis_url, 
                    decode_responses=True,
                    socket_connect_timeout=3,
                    socket_timeout=3
                )
                logger.info(f"Redis pool initialized: {redis_url}")
            except Exception as e:
                logger.error(f"Failed to initialize Redis pool: {e}")
                raise
        return redis.Redis(connection_pool=cls._pool)

    @classmethod
    def get(cls, key):
        try:
            r = cls.get_client()
            return r.get(key)
        except Exception as e:
            logger.error(f"Redis get failed: {e}")
            return None

    @classmethod
    def set(cls, key, value, ex=None):
        try:
            r = cls.get_client()
            return r.set(key, value, ex=ex)
        except Exception as e:
            logger.error(f"Redis set failed: {e}")
            return False

# 全局单例
redis_client = RedisClient
