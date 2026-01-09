from prometheus_client import Counter, Gauge, Histogram, REGISTRY
from prometheus_client.openmetrics.exposition import generate_latest

# 定义指标

# 1. 任务队列指标
TASK_ENQUEUED_TOTAL = Counter(
    "procurator_task_enqueued_total", 
    "Total number of tasks enqueued",
    ["queue", "task_name"]
)

TASK_QUEUE_SIZE = Gauge(
    "procurator_task_queue_size",
    "Current number of tasks in queue",
    ["queue"]
)

# 2. 任务执行指标
TASK_STARTED_TOTAL = Counter(
    "procurator_task_started_total",
    "Total number of tasks started by worker",
    ["queue", "task_name"]
)

TASK_FINISHED_TOTAL = Counter(
    "procurator_task_finished_total",
    "Total number of tasks successfully finished",
    ["queue", "task_name"]
)

TASK_FAILED_TOTAL = Counter(
    "procurator_task_failed_total",
    "Total number of tasks failed",
    ["queue", "task_name", "error_type"]
)

TASK_EXECUTION_SECONDS = Histogram(
    "procurator_task_execution_seconds",
    "Time spent executing task scripts",
    ["queue", "task_name"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, float("inf"))
)

# 3. HTTP 指标 (可选，FastAPI 通常有中间件，这里先只做业务指标)

def get_metrics_data():
    """
    获取 OpenMetrics 格式的监控数据
    """
    return generate_latest(REGISTRY)
