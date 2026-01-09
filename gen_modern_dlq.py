import sys
import os
import json

# 确保项目根目录在 sys.path 中
sys.path.append(os.getcwd())

from app.queues.backends.redis_stream import RedisStreamBackend

print("--- Generating Replayable DLQ Message ---")
backend = RedisStreamBackend()
queue_name = "test_queue_dlq"

# 1. 入队
payload = {"task": "replay_test_task", "data": "I_CAN_BE_REPLAYED"}
tid = backend.enqueue(queue_name, payload)
print(f"Enqueued Task: {tid}")

# 2. 出队 & 失败
item = backend.dequeue(queue_name)
if item:
    tid, payload = item
    backend.mark_failed(tid, "Modern Error with Payload", payload)
    print(f"Marked failed. Please check DLQ for queue: {queue_name}")
else:
    print("Failed to dequeue (maybe queue is empty?)")
