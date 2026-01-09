import sys
import os
import json
import argparse
from datetime import datetime

# 确保项目根目录在 sys.path 中
sys.path.append(os.getcwd())

from app.core.redis import redis_client
from app.queues.backends.redis_stream import RedisStreamBackend

def get_dlq_key(queue_name):
    return f"procurator:queue:{queue_name}:dlq"

# --- 核心逻辑 (返回数据) ---

def _list_dead_letters(queue_name, count=10):
    client = redis_client.get_client()
    key = get_dlq_key(queue_name)
    result = []
    
    try:
        # XREVRANGE: 倒序读取，最新的在前面
        messages = client.xrevrange(key, count=count)
        for msg_id, body in messages:
            ts = float(body.get("died_at", 0))
            time_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            result.append({
                "msg_id": msg_id,
                "time": time_str,
                "timestamp": ts,
                "task": body.get("task", "unknown"),
                "error": body.get("error", "unknown")
            })
        return result
    except Exception as e:
        return {"error": str(e)}

def _inspect_dead_letter(queue_name, msg_id):
    client = redis_client.get_client()
    key = get_dlq_key(queue_name)
    try:
        messages = client.xrange(key, min=msg_id, max=msg_id)
        if not messages:
            return {"error": f"Message {msg_id} not found"}
            
        _, body = messages[0]
        result = {"meta": body, "payload": None}
        
        if "original_payload" in body:
            try:
                result["payload"] = json.loads(body["original_payload"])
            except:
                result["payload"] = body["original_payload"]
        return result
    except Exception as e:
        return {"error": str(e)}

def _replay_dead_letter(queue_name, msg_id):
    client = redis_client.get_client()
    key = get_dlq_key(queue_name)
    backend = RedisStreamBackend()
    
    try:
        messages = client.xrange(key, min=msg_id, max=msg_id)
        if not messages:
            return {"error": f"Message {msg_id} not found"}
            
        _, body = messages[0]
        if "original_payload" not in body:
            return {"error": "Cannot replay: missing 'original_payload'"}
            
        payload = json.loads(body["original_payload"])
        new_tid = backend.enqueue(queue_name, payload)
        return {"status": "replayed", "new_tid": new_tid}
    except Exception as e:
        return {"error": str(e)}

def _purge_dlq(queue_name):
    client = redis_client.get_client()
    key = get_dlq_key(queue_name)
    try:
        client.xtrim(key, maxlen=0)
        return {"status": "purged", "queue": key}
    except Exception as e:
        return {"error": str(e)}

# --- CLI 封装 (打印输出) ---

def list_dead_letters(queue_name, count=10):
    res = _list_dead_letters(queue_name, count)
    if isinstance(res, dict) and "error" in res:
        print(f"Error listing DLQ: {res['error']}")
        return
        
    print(f"--- DLQ: {get_dlq_key(queue_name)} (Last {len(res)}) ---")
    if not res:
        print("(Empty)")
        return

    print(f"{'MSG_ID':<20} | {'TIME':<20} | {'TASK':<15} | {'ERROR'}")
    print("-" * 80)
    for item in res:
        print(f"{item['msg_id']:<20} | {item['time']:<20} | {item['task']:<15} | {item['error'][:30]}")

def inspect_dead_letter(queue_name, msg_id):
    res = _inspect_dead_letter(queue_name, msg_id)
    if "error" in res:
        print(f"Error: {res['error']}")
        return
        
    print(json.dumps(res["meta"], indent=2, ensure_ascii=False))
    if res["payload"]:
        print("\n--- Original Payload ---")
        print(json.dumps(res["payload"], indent=2, ensure_ascii=False))

def replay_dead_letter(queue_name, msg_id):
    res = _replay_dead_letter(queue_name, msg_id)
    if "error" in res:
        print(f"Error replaying message: {res['error']}")
    else:
        print(f"[OK] Re-enqueued as TID: {res['new_tid']}")

def purge_dlq(queue_name):
    res = _purge_dlq(queue_name)
    if "error" in res:
        print(f"Error purging DLQ: {res['error']}")
    else:
        print(f"[OK] Purged DLQ: {res['queue']}")

# --- API 适配 (Script Runner) ---

def run(context):
    """
    支持通过 script.execute 调用
    参数结构: context.args = {"args": {"action": "list", "queue": "api", ...}}
    """
    print(f"DLQ Manager invoked via ScriptRunner. Args: {context.args}")
    
    raw_args = context.args.get("args", {})
    if isinstance(raw_args, list):
        print("Error: Please provide args as a dictionary, e.g., {'action': 'list'}")
        return
        
    action = raw_args.get("action", "list")
    queue = raw_args.get("queue", "api")
    msg_id = raw_args.get("id")
    
    if action == "list":
        return _list_dead_letters(queue)
    elif action == "inspect":
        if not msg_id:
            return {"error": "'id' is required for inspect"}
        return _inspect_dead_letter(queue, msg_id)
    elif action == "replay":
        if not msg_id:
            return {"error": "'id' is required for replay"}
        return _replay_dead_letter(queue, msg_id)
    elif action == "purge":
        if raw_args.get("force"):
            return _purge_dlq(queue)
        else:
            return {"error": "'force': true is required for purge via API"}
    else:
        return {"error": f"Unknown action: {action}"}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Procurator DLQ Manager")
    parser.add_argument("action", choices=["list", "inspect", "replay", "purge"])
    parser.add_argument("--queue", default="api", help="Queue name (default: api)")
    parser.add_argument("--id", help="Message ID (required for inspect/replay)")
    
    args = parser.parse_args()
    
    if args.action == "list":
        list_dead_letters(args.queue)
    elif args.action == "inspect":
        if not args.id:
            print("Error: --id is required for inspect")
        else:
            inspect_dead_letter(args.queue, args.id)
    elif args.action == "replay":
        if not args.id:
            print("Error: --id is required for replay")
        else:
            replay_dead_letter(args.queue, args.id)
    elif args.action == "purge":
        confirm = input(f"Are you sure you want to PURGE {args.queue} DLQ? (y/N): ")
        if confirm.lower() == "y":
            purge_dlq(args.queue)
