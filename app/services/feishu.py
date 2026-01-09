from app.infra.feishu_client import get_tenant_access_token, redis_client, REDIS_KEY_TOKEN
from app.core.config import config
import time
import hashlib
import json

async def get_token(data: dict):
    # 支持两种模式：
    # 1. 直接传入 app_id / app_secret
    # 2. 传入 app_hash (通过 set_token 注册返回的)
    
    app_id = data.get("app_id")
    app_secret = data.get("app_secret")
    app_hash = data.get("app_hash")
    
    # 如果传入了 hash，先解析出凭证
    if app_hash and not (app_id and app_secret):
        cred_key = f"feishu:credentials:{app_hash}"
        cred_json = redis_client.get(cred_key)
        if cred_json:
            try:
                creds = json.loads(cred_json)
                app_id = creds.get("app_id")
                app_secret = creds.get("app_secret")
            except Exception:
                pass
        
        if not app_id or not app_secret:
            raise ValueError(f"Invalid or expired app_hash: {app_hash}")

    token, expire = get_tenant_access_token(app_id, app_secret)
    return {"tenant_access_token": token, "expire": expire}

async def set_token(data: dict):
    """
    应用注册/凭证更新接口
    输入: app_id, app_secret
    输出: app_hash (用于后续接口调用)
    """
    app_id = data.get("app_id")
    app_secret = data.get("app_secret")
    
    # 兼容旧的手动 token 模式
    manual_token = data.get("token")
    if manual_token:
        if not app_id:
             raise ValueError("app_id is required for manual token setting")
        expire = data.get("expire", 3600)
        cache_key = f"{REDIS_KEY_TOKEN}:{app_id}"
        redis_client.set(cache_key, manual_token, ex=expire)
        return {"status": "ok", "msg": "Token manually updated"}

    if not app_id or not app_secret:
        raise ValueError("app_id and app_secret are required")

    # 1. 验证凭证有效性 (通过尝试获取 Token)
    # 这也会自动将 Token 缓存到 Redis
    try:
        token, expire = get_tenant_access_token(app_id, app_secret)
    except Exception as e:
        raise ValueError(f"Invalid Feishu credentials: {str(e)}")

    # 2. 生成 Hash (MD5)
    # 使用 app_id + app_secret 生成唯一标识
    raw_str = f"{app_id}:{app_secret}"
    app_hash = hashlib.md5(raw_str.encode("utf-8")).hexdigest()

    # 3. 持久化凭证到 Redis
    # Key: feishu:credentials:{hash}
    # Value: {"app_id": "...", "app_secret": "..."}
    cred_key = f"feishu:credentials:{app_hash}"
    cred_data = json.dumps({
        "app_id": app_id,
        "app_secret": app_secret,
        "updated_at": time.time()
    })
    
    # 存储凭证，设置较长的过期时间 (例如 30 天)，或者不设置过期
    redis_client.set(cred_key, cred_data)

    return {
        "status": "registered", 
        "msg": "Application registered successfully",
        "app_hash": app_hash,
        "app_id": app_id
    }

