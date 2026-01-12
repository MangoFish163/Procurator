# Procurator (代理人)

[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![Redis](https://img.shields.io/badge/Redis-Stream-DC382D.svg?style=flat&logo=redis&logoColor=white)](https://redis.io)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Procurator** 是一个基于 FastAPI 构建的轻量级、高性能分布式任务队列与 API 网关系统。
它的核心设计目标是解耦**任务分发**与**任务执行**，在提供高吞吐量的同时，通过持久化存储和故障恢复机制确保任务的可靠性。

适用于微服务架构下的异步任务处理、定时任务调度以及作为统一的 API 入口网关。

---

## ✨ 核心特性

*   **🚀 极致性能**: 基于 FastAPI 和 Python `asyncio` 构建，充分利用异步 I/O 处理高并发请求。
*   **队列管理**:
    *   **生产模式**: 使用 **Redis Stream** (Consumer Group)，支持多 Worker 负载均衡与消息确认 (ACK)。
    *   **开发模式**: 内置 **Memory Backend**，无需 Redis 即可快速启动开发。
*   **🛡️ 高可靠性**:
    *   **双重存储**: "Flow in Redis, State in DB"。任务流转依赖 Redis，状态与审计日志持久化至 PostgreSQL/SQLite。
    *   **崩溃恢复 (Crash Recovery)**: Worker 启动时自动通过 Redis `XCLAIM` 机制抢占并恢复未完成的 Pending 任务，确保服务重启不丢单。
    *   **死信队列 (DLQ)**: 多次重试失败的任务自动移入死信队列，支持保存原始 Payload 供后续排查与重放。
*   **🔐 安全体系**:
    *   **RBAC 鉴权**: 基于数据库的角色访问控制 (Admin/Ops/Dev)，支持动态 Token 管理。
    *   **IP 白名单**: 中间件级别的 IP 访问控制。
*   **📊 可观测性**:
    *   **日志监控**: 集成 **Loki + Promtail + Grafana**，实现日志的集中采集与可视化检索。
    *   **指标监控**: 内置 `/metrics` 端点，暴露 Prometheus 格式的业务指标（吞吐量、队列长度、耗时等）。
*   **🔌 易扩展**: 支持动态注册任务处理逻辑与 Webhook 回调。

## �️ 快速开始

### 前置要求
*   Python 3.10+
*   Redis (生产环境必须，开发环境可选)
*   Docker & Docker Compose (用于部署监控栈)

### 1. 本地开发环境搭建

**Step 1: 克隆代码与环境配置**
```bash
git clone https://github.com/MangoFish163/Procurator.git
cd procurator

# 创建并激活虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

**Step 2: 配置文件**
复制示例配置并按需修改（默认配置即可运行于 SQLite + Memory 模式）：
```bash
cp .env.example .env
```
*如需启用 Redis 队列，请在 `.env` 中设置 `QUEUE_BACKEND=redis` 并配置 `REDIS_URL`。*

**Step 3: 初始化系统**
```bash
# 执行数据库迁移 (创建表结构)
alembic upgrade head

# 创建管理员账号 (获取 API Key)
python tools/create_admin.py
```
*> 记下生成的 API Key，后续请求需携带此 Key。*

**Step 4: 启动服务**
```bash
python serve.py
```
服务启动后，访问接口文档：[http://localhost:50002/docs](http://localhost:50002/docs)

### 2. Docker 生产部署

```bash
docker-compose up -d --build
```

### 3. 部署监控栈 (Loki + Grafana)

Procurator 提供了开箱即用的 PLG (Promtail-Loki-Grafana) 监控配置：

```bash
cd deploy/monitoring
docker-compose up -d
```
*   **Grafana**: [http://localhost:3000](http://localhost:3000) (默认账号: `admin`/`admin`)
*   **数据源**: 已自动配置 Loki，直接在 Explore 中查询 `{job="procurator"}` 即可查看日志。

## � 使用指南

### 发送任务 (Dispatch)

```bash
curl -X POST "http://localhost:50002/dispatch" \
     -H "Content-Type: application/json" \
     -H "X-API-Token: <YOUR_API_KEY>" \
     -d '{
           "task": "system.ping",
           "taskData": {"msg": "hello"},
           "async": true
         }'
```

### 查看任务状态

```bash
curl -X GET "http://localhost:50002/task/<TASK_ID>" \
     -H "X-API-Token: <YOUR_API_KEY>"
```

## 📂 项目结构

```
Procurator/
├── app/
│   ├── core/           # 核心配置、数据库、安全组件
│   ├── infra/          # 基础设施 (RateLimiter, Feishu)
│   ├── models/         # SQLAlchemy 数据模型
│   ├── queues/         # 队列与后端实现 (Redis/Memory)
│   ├── routers/        # API 路由定义
│   ├── services/       # 业务逻辑实现
│   ├── worker.py       # 异步 Worker 入口
│   └── main.py         # FastAPI 应用入口
├── deploy/             # 部署相关配置 (Monitoring, Docker)
├── tools/              # 运维工具脚本
├── logs/               # 应用日志目录
├── serve.py            # 开发服务器启动脚本
└── ...
```

## 📚 详细文档

更多细节请参阅以下文档：

*   **[项目说明书](./项目说明.md)**: 深度解析架构设计、模块划分与技术细节。
*   **[接口对接文档](./对接文档.md)**: 完整的 API 接口定义、参数说明与错误码字典。
*   **[改进与演进规划](./改进意见.md)**: 项目技术债治理进度与未来功能规划。

## ⚖️ 许可证

MIT License
