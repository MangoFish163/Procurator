import time
import requests
import json
from app.core.config import config
from app.core.log_utils import get_logger
from app.core.redis import redis_client

logger = get_logger("feishu_client")

# Redis Key 前缀
REDIS_KEY_TOKEN = "feishu:tenant_access_token"

def get_tenant_access_token(app_id=None, app_secret=None):
    """
    获取飞书 tenant_access_token (优先查 Redis)
    支持传入特定的 app_id/secret，否则使用全局配置
    """
    # 1. 确定使用的 AppID（用于生成 Redis Key，支持多租户）
    global_app_id = config.get("FEISHU_APP_ID")
    global_app_secret = config.get("FEISHU_APP_SECRET")
    
    target_app_id = app_id or global_app_id
    target_app_secret = app_secret or global_app_secret
    
    if not target_app_id or not target_app_secret:
        logger.warning("Feishu App ID/Secret not configured")
        return "mock_token", 7200

    # Redis Key 区分不同 AppID
    cache_key = f"{REDIS_KEY_TOKEN}:{target_app_id}"

    # 2. 尝试从 Redis 获取
    try:
        cached_token = redis_client.get(cache_key)
        if cached_token:
            # 获取剩余过期时间 (TTL)
            ttl = redis_client.get_client().ttl(cache_key)
            if ttl > 60: # 预留 60s 缓冲
                return cached_token, ttl
    except Exception as e:
        logger.warning(f"Redis read failed, fallback to direct fetch: {e}")

    # 3. Redis 无缓存或已过期，请求飞书接口
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {
        "app_id": target_app_id,
        "app_secret": target_app_secret
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == 0:
            token = data.get("tenant_access_token")
            expire = data.get("expire", 7200)
            
            # 4. 写入 Redis
            try:
                # 扣除一点过期时间，确保 Redis 里的比飞书服务端的先过期，避免边界效应
                redis_client.set(cache_key, token, ex=expire - 60)
                logger.info(f"Refreshed Feishu token for {target_app_id}, expire={expire}")
            except Exception as e:
                logger.error(f"Redis write failed: {e}")
                
            return token, expire
        else:
            logger.error(f"Get tenant_access_token failed: {data}")
            raise Exception(f"Feishu API Error: {data.get('msg')}")
    except Exception as e:
        logger.error(f"Get tenant_access_token exception: {e}")
        raise
