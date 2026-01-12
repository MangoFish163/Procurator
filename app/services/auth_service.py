import hashlib
import secrets
from typing import Optional, Tuple
from sqlalchemy.future import select
from app.core.database import AsyncSessionLocal
from app.models.system import User
from app.core.log_utils import get_logger

logger = get_logger("auth")

def hash_api_key(key: str) -> str:
    """
    使用 SHA256 对 API Key 进行哈希 (生产环境建议加盐或使用 argon2)
    这里为了性能和简单性，且 Token 本身足够长，暂时使用 SHA256
    """
    return hashlib.sha256(key.encode()).hexdigest()

async def get_user_by_key(api_key: str) -> Optional[User]:
    """
    通过 API Key 获取用户信息
    """
    key_hash = hash_api_key(api_key)
    async with AsyncSessionLocal() as session:
        try:
            stmt = select(User).where(User.api_key_hash == key_hash, User.is_active == True)
            result = await session.execute(stmt)
            user = result.scalars().first()
            return user
        except Exception as e:
            logger.error(f"Failed to get user by key: {e}")
            return None

async def create_user(username: str, role: str = "dev", description: str = None) -> Tuple[User, str]:
    """
    创建新用户并返回 (User对象, 明文APIKey)
    """
    # 生成 32 字节的随机 Token (64 字符 hex)
    raw_key = secrets.token_hex(32)
    key_hash = hash_api_key(raw_key)
    
    async with AsyncSessionLocal() as session:
        user = User(
            username=username,
            api_key_hash=key_hash,
            role=role,
            description=description
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user, raw_key
