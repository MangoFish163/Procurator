import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import config

# 创建测试客户端
client = TestClient(app)

# 模拟一个有效的 Token
TEST_TOKEN = "test-secret-token"

@pytest.fixture(autouse=True)
def mock_config(mocker):
    """
    自动 Mock 配置，确保测试使用固定的 Token
    """
    mock_conf = {
        "API_TOKEN": TEST_TOKEN,
        "API_ROLE": "admin"
    }
    mocker.patch.object(config, "get", side_effect=lambda k, default=None: mock_conf.get(k, default))

def test_health_check():
    """
    验证服务存活 (/ping)
    """
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_auth_rejection():
    """
    验证无 Token 访问会被拒绝 (401)
    """
    # 不带 Header
    response = client.post("/dispatch", json={"task": "demo"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"

    # 带错误 Header
    response = client.post("/dispatch", json={"task": "demo"}, headers={"X-API-Token": "wrong-token"})
    assert response.status_code == 401

def test_sync_dispatch_success():
    """
    验证同步任务分发流程 (Sync Dispatch)
    使用内置的 _doc_example 任务
    """
    payload = {
        "task": "_doc_example",
        "taskData": {"msg": "hi"},
        "async": False  # 强制同步
    }
    headers = {"X-API-Token": TEST_TOKEN}
    
    response = client.post("/dispatch", json=payload, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    
    # 验证响应结构
    # main.py 中 _doc_example 直接返回 {"code": 200, "data": "Hello World"}
    # 但 dispatch 接口可能会包装它，或者直接返回。
    # 根据 main.py 源码: 
    # if req.task == "_doc_example": return {"code": 200, "data": "Hello World"}
    assert data["code"] == 200
    assert data["data"] == "Hello World"

def test_async_dispatch_flow(mocker):
    """
    验证异步任务分发流程 (Async Dispatch)
    1. 提交任务 -> 获得 Task ID
    2. 查询任务状态 -> 确认在队列中
    """
    # 1. 提交任务
    payload = {
        "task": "demo_script", # 假设存在这个脚本，或者任意脚本名只要不报错
        "taskData": {"key": "val"},
        "async": True
    }
    headers = {"X-API-Token": TEST_TOKEN}
    
    # Mock is_allowed 总是返回 True，避免权限拦截
    # 注意：is_allowed 在 app.queues.tasks 中
    mocker.patch("app.main.is_allowed", return_value=True)
    
    response = client.post("/dispatch", json=payload, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["accepted"] is True
    task_id = data.get("task_id")
    assert task_id is not None
    
    # 2. 查询任务状态
    status_resp = client.get(f"/task/{task_id}", headers=headers)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    
    # 刚提交的任务应该是 pending 或 queued
    assert status_data["status"] in ["pending", "queued", "unknown"] # unknown 是因为 MemoryBackend 可能没持久化？
    # 根据 QueueManager 逻辑，save_task 后 status 是 pending。
    assert status_data["status"] == "pending"

def test_invalid_task_validation():
    """
    验证参数校验逻辑 (422)
    """
    # 缺少必填字段 taskData
    payload = {"task": "demo"} 
    headers = {"X-API-Token": TEST_TOKEN}
    
    response = client.post("/dispatch", json=payload, headers=headers)
    
    # Pydantic 会拦截缺失字段
    assert response.status_code == 422

def test_metrics_endpoint():
    """
    验证 /metrics 接口是否暴露 Prometheus 数据
    """
    # 先触发一些任务，产生指标
    client.get("/ping")
    
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    
    content = response.text
    # 验证核心指标是否存在
    assert "procurator_task_enqueued_total" in content
    assert "procurator_task_queue_size" in content
    assert "procurator_task_started_total" in content
    assert "procurator_task_execution_seconds" in content
