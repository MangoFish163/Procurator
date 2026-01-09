from sqlalchemy import Column, String, DateTime, Integer, Text, JSON
from sqlalchemy.sql import func
from app.core.database import Base
import uuid

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    queue = Column(String(50), index=True, nullable=False)
    task_name = Column(String(100), index=True, nullable=False)
    status = Column(String(20), index=True, default="pending")
    
    # 任务参数和结果 (使用 JSON 类型，PG 下会自动映射为 JSONB)
    payload = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    
    error = Column(Text, nullable=True)
    retries = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 时间分析
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    # 可选：记录哪个 Worker 处理的
    worker_id = Column(String(100), nullable=True)
