from sqlalchemy import Column, String, DateTime, Integer, Boolean, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base
import uuid

class RegisteredTask(Base):
    """
    任务注册表：用于动态控制任务配置
    """
    __tablename__ = "registered_tasks"

    task_name = Column(String(100), primary_key=True, index=True)
    default_queue = Column(String(50), default="api")
    max_retries = Column(Integer, default=3)
    timeout_seconds = Column(Integer, default=60)
    is_active = Column(Boolean, default=True)
    description = Column(String(255), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Webhook(Base):
    """
    回调配置表
    """
    __tablename__ = "webhooks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_name = Column(String(100), index=True, nullable=False) # 关联 registered_tasks
    url = Column(String(500), nullable=False)
    secret = Column(String(100), nullable=True) # 签名密钥
    headers = Column(JSON, nullable=True) # 自定义 Header
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class User(Base):
    """
    用户/API Key 表
    """
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, index=True, nullable=False)
    api_key_hash = Column(String(128), nullable=False) # 存储 Hash 后的 Key
    role = Column(String(20), default="dev") # admin, ops, dev
    description = Column(String(200), nullable=True)
    
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    """
    操作审计日志
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), index=True, nullable=True)
    action = Column(String(50), nullable=False) # e.g., "dispatch", "replay_dlq"
    target_id = Column(String(100), nullable=True) # e.g., task_id or config_id
    details = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
