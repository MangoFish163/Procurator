import pytest
import asyncio
import os
import sys

# 确保项目根目录在 sys.path 中
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture(scope="session")
def event_loop():
    """创建全局事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """为测试环境 Mock 必要的环境变量"""
    monkeypatch.setenv("FEISHU_APP_ID", "cli_mock_id")
    monkeypatch.setenv("FEISHU_APP_SECRET", "mock_secret")
    monkeypatch.setenv("TRACK_API_KEY", "mock_track_key")
    monkeypatch.setenv("SERVER_LOG_LEVEL", "error")
