from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import config
from app.core.log_utils import get_logger

logger = get_logger("database")

# 获取数据库连接串
# 默认使用 sqlite 内存数据库以便测试，但推荐配置 PostgreSQL
DATABASE_URL = config.get("DATABASE_URL", "sqlite+aiosqlite:///./app.db")

if DATABASE_URL.startswith("sqlite"):
    # SQLite 特殊配置
    engine = create_async_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False
    )
else:
    # PostgreSQL 配置
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=20,
        max_overflow=10
    )

# 创建异步 Session 工厂
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# 声明式基类
Base = declarative_base()

async def init_db():
    """
    初始化数据库表结构 (用于开发环境快速建表，生产环境推荐使用 Alembic)
    """
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # 慎用！
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")

async def get_db():
    """
    FastAPI 依赖注入：获取数据库会话
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
