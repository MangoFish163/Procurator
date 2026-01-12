import sys
import os
import json
import pytest

# 确保项目根目录在 sys.path 中
sys.path.append(os.getcwd())

from app.queues.backends.redis_stream import RedisStreamBackend

@pytest.mark.asyncio
async def test_dlq_generation():
    """
    Integration test to verify DLQ message generation and format.
    """
    print("--- Generating Replayable DLQ Message ---")
    
    # 检查是否配置了 Redis
    if os.getenv("QUEUE_BACKEND", "").lower() != "redis":
        pytest.skip("Skipping DLQ test: Redis backend not enabled")

    backend = RedisStreamBackend()
    queue_name = "test_queue_dlq"
    
    # 1. 入队
    payload = {"task": "replay_test_task", "data": "I_CAN_BE_REPLAYED"}
    tid = backend.enqueue(queue_name, payload)
    print(f"Enqueued Task: {tid}")
    
    # 2. 出队 & 失败
    item = backend.dequeue(queue_name)
    
    assert item is not None, "Failed to dequeue task"
    
    if item:
        tid_out, payload_out = item
        assert tid_out == tid
        assert payload_out.get("task") == "replay_test_task"
        
        # 标记失败，触发 DLQ 写入
        backend.mark_failed(tid, "Modern Error with Payload", payload)
        print(f"Marked failed. Please check DLQ for queue: {queue_name}")
        
        # 3. 验证 DLQ 内容 (可选)
        dlq_key = f"procurator:queue:{queue_name}:dlq"
        # 注意：这里假设 RedisClient 是同步的或者我们在同步上下文中
        # 如果 RedisStreamBackend 内部使用的是同步 redis 客户端，这没问题
        # 如果是异步的，需要相应调整。当前代码看起来是同步的。
        
        client = backend.client
        dlq_items = client.xrange(dlq_key, count=1)
        assert len(dlq_items) > 0, "DLQ should not be empty"
        
        _, msg_body = dlq_items[-1]
        assert "original_payload" in msg_body
        
        # 验证 payload 是否被正确序列化为字符串 (修复后的行为)
        payload_str = msg_body["original_payload"]
        assert isinstance(payload_str, str)
        assert json.loads(payload_str) == payload

if __name__ == "__main__":
    # 允许直接运行脚本
    import asyncio
    try:
        asyncio.run(test_dlq_generation())
    except Exception as e:
        print(f"Test failed: {e}")
