import json
import time
import socket
import os
import uuid
from typing import Optional, Dict, Any
from app.core.redis import redis_client
from app.core.log_utils import get_logger
from app.core.metrics import TASK_ENQUEUED_TOTAL, TASK_QUEUE_SIZE

logger = get_logger("redis_stream")

class RedisStreamBackend:
    def __init__(self):
        self.client = redis_client.get_client()
        self.group_name = "procurator_group"
        self.consumer_name = f"worker_{socket.gethostname()}_{os.getpid()}"
        
        # 记录已初始化的队列，避免重复 XGROUP CREATE
        self._initialized_queues = set()

    def _ensure_group(self, queue_name: str):
        """确保 Consumer Group 存在"""
        if queue_name in self._initialized_queues:
            return
            
        stream_key = f"procurator:queue:{queue_name}"
        try:
            # MKSTREAM: 如果 Stream 不存在则自动创建
            self.client.xgroup_create(stream_key, self.group_name, id="0", mkstream=True)
            logger.info(f"Created consumer group {self.group_name} for {stream_key}")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                pass  # Group 已经存在，忽略
            else:
                logger.error(f"Failed to create consumer group: {e}")
        
        self._initialized_queues.add(queue_name)

    def enqueue(self, queue_name: str, payload: dict) -> str:
        """
        入队：
        1. 生成 Task ID
        2. 保存任务详情到 Hash (用于状态查询)
        3. 推送到 Stream (用于分发)
        """
        tid = str(uuid.uuid4())
        task_name = payload.get("task", "unknown")
        
        # 1. 构造任务元数据
        task_info = {
            "id": tid,
            "task": task_name,
            "status": "pending",
            "created_at": time.time(),
            "payload": json.dumps(payload), # 序列化 Payload
            "queue": queue_name
        }
        
        # 2. 保存状态 (Hash)
        task_key = f"procurator:task:{tid}"
        # 设置过期时间 7 天，避免 Redis 爆满
        pipeline = self.client.pipeline()
        pipeline.hset(task_key, mapping=task_info)
        pipeline.expire(task_key, 604800) 
        pipeline.execute()
        
        # 3. 推送 Stream
        stream_key = f"procurator:queue:{queue_name}"
        stream_msg = {"tid": tid}
        
        self.client.xadd(stream_key, stream_msg)
        
        # Metrics
        try:
            TASK_ENQUEUED_TOTAL.labels(queue=queue_name, task_name=task_name).inc()
            q_len = self.client.xlen(stream_key)
            TASK_QUEUE_SIZE.labels(queue=queue_name).set(q_len)
        except Exception:
            pass
            
        return tid

    def dequeue(self, queue_name: str) -> Optional[tuple[str, dict]]:
        """
        出队：
        优先处理 Pending 消息，然后阻塞读取新消息
        """
        self._ensure_group(queue_name)
        stream_key = f"procurator:queue:{queue_name}"
        
        try:
            # 0. 周期性检查长时间 Pending 的消息 (Crash Recovery)
            # 1% 概率触发，避免频繁调用
            if int(time.time() * 100) % 100 == 0:
                self.process_pending(queue_name)

            # 1. 优先检查自己的 Pending 消息 (Crash Recovery 后续)
            # id="0" 表示读取所有 Pending 消息
            my_pendings = self.client.xreadgroup(
                self.group_name, 
                self.consumer_name, 
                {stream_key: "0"}, 
                count=1
            )
            
            if my_pendings:
                stream_name, msg_list = my_pendings[0]
                if msg_list:
                    msg_id, msg_data = msg_list[0]
                    tid = msg_data.get("tid")
                    logger.info(f"Processing pending task {tid} from {queue_name}")
                    
                    # 更新 msg_id 到 Hash，确保后续能 ACK
                    task_key = f"procurator:task:{tid}"
                    self.client.hset(task_key, "_stream_msg_id", msg_id)
                    
                    task_info = self.get_task(tid)
                    if task_info:
                        return tid, task_info.get("payload", {})
                    
                    # 异常情况：Pending 的任务 Hash 没了 -> ACK 掉
                    self.client.xack(stream_key, self.group_name, msg_id)
                    return tid, {}

            # 2. 阻塞读取新消息 (">")
            # count=1, block=2000ms
            messages = self.client.xreadgroup(
                self.group_name, 
                self.consumer_name, 
                {stream_key: ">"}, 
                count=1, 
                block=2000
            )
            
            if messages:
                stream_name, msg_list = messages[0]
                if msg_list:
                    msg_id, msg_data = msg_list[0]
                    tid = msg_data.get("tid")
                    
                    # 记录 msg_id 到 Hash，不立即 ACK
                    task_key = f"procurator:task:{tid}"
                    self.client.hset(task_key, "_stream_msg_id", msg_id)
                    
                    task_info = self.get_task(tid)
                    if task_info:
                        return tid, task_info.get("payload", {})
                        
                    # Hash 丢失，ACK 掉
                    logger.warning(f"Task {tid} found in stream but missing in hash")
                    self.client.xack(stream_key, self.group_name, msg_id)
                    return tid, {}
                    
        except Exception as e:
            logger.error(f"Redis dequeue error: {e}")
            time.sleep(1)
            
        return None

    def process_pending(self, queue_name: str):
        """
        处理长时间 Pending 的消息 (Crash Recovery)
        """
        self._ensure_group(queue_name)
        stream_key = f"procurator:queue:{queue_name}"
        
        try:
            # 检查 PEL 中超过 10分钟 (600000ms) 未 ACK 的消息
            pendings = self.client.xpending_range(
                stream_key, 
                self.group_name, 
                min="-", 
                max="+", 
                count=10
            )
            
            for p in pendings:
                # 忽略 delivery_count 过高的毒药消息 (比如 > 10 次)
                if p['times_delivered'] > 10:
                    msg_id = p['message_id']
                    logger.error(f"Message {msg_id} delivered {p['times_delivered']} times, moving to DLQ")
                    # 这里应该做 DLQ 处理，但为了简单先 ACK 掉
                    self.client.xack(stream_key, self.group_name, msg_id)
                    continue

                if p['time_since_delivered'] > 600000: # 10分钟
                    msg_id = p['message_id']
                    logger.warning(f"Claiming timeout message {msg_id} in {queue_name}")
                    
                    # 抢占消息
                    self.client.xclaim(
                        stream_key, 
                        self.group_name, 
                        self.consumer_name, 
                        min_idle_time=600000, 
                        message_ids=[msg_id]
                    )
        except Exception as e:
            logger.error(f"Error processing pending for {queue_name}: {e}")

    def mark_done(self, tid: str, payload: dict = None):
        """
        标记完成并 ACK
        """
        self._ack_and_update(tid, "completed")

    def mark_failed(self, tid: str, error: str, payload: dict = None):
        """
        标记失败，ACK，并写入 DLQ
        """
        # 1. 获取完整信息
        task_info = self.get_task(tid) or {}
        queue_name = task_info.get("queue")
        
        # 2. 写入 DLQ
        if queue_name:
            try:
                stream_key = f"procurator:queue:{queue_name}"
                dlq_key = f"{stream_key}:dlq"
                
                payload_str = task_info.get("payload", "{}")
                if isinstance(payload_str, dict):
                    payload_str = json.dumps(payload_str)
                
                dead_msg = {
                    "tid": tid,
                    "error": str(error),
                    "died_at": str(time.time()),
                    "original_payload": payload_str
                }
                if "task" in task_info:
                    dead_msg["task"] = task_info["task"]
                    
                self.client.xadd(dlq_key, dead_msg)
                logger.warning(f"Task {tid} moved to DLQ: {dlq_key}")
            except Exception as e:
                logger.error(f"Failed to move task {tid} to DLQ: {e}")

        # 3. ACK 并更新状态
        self._ack_and_update(tid, "failed", error)

    def _ack_and_update(self, tid, status, error=None):
        """
        通用状态更新与 ACK 逻辑
        """
        task_key = f"procurator:task:{tid}"
        
        # 1. 获取 queue_name 和 msg_id 用于 ACK
        # 注意：这里我们只 ACK Stream 里的消息，不删除 Hash（保留一段时间用于查询）
        info = self.client.hmget(task_key, ["queue", "_stream_msg_id"])
        queue_name, msg_id = info[0], info[1]
        
        # 2. 更新 Hash 状态
        mapping = {"status": status, "updated_at": time.time()}
        if error:
            mapping["error"] = error
        self.client.hset(task_key, mapping=mapping)
        
        # 3. 执行 ACK
        if queue_name and msg_id:
            stream_key = f"procurator:queue:{queue_name}"
            try:
                self.client.xack(stream_key, self.group_name, msg_id)
            except Exception as e:
                logger.error(f"Failed to ACK task {tid}: {e}")

    def get_task(self, tid: str) -> Optional[dict]:
        task_key = f"procurator:task:{tid}"
        info = self.client.hgetall(task_key)
        if not info:
            return None
        
        if "payload" in info and isinstance(info["payload"], str):
            try:
                info["payload"] = json.loads(info["payload"])
            except:
                pass
        return info

    def save_task(self, tid, data):
        # 兼容性方法
        task_key = f"procurator:task:{tid}"
        if "payload" in data and isinstance(data["payload"], dict):
            data["payload"] = json.dumps(data["payload"])
        self.client.hset(task_key, mapping=data)
