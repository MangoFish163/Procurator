# 📊 Loki 日志监控系统部署指南

本文档指导您如何使用 **PLG Stack** (Promtail + Loki + Grafana) 为 Procurator 项目搭建轻量级的日志监控系统。

## 1. 架构原理

该方案采用**无侵入式**设计，不需要修改 Procurator 的任何 Python 代码。

- **Promtail (采集)**: 作为 Agent 运行，挂载项目根目录的 `logs/` 文件夹，实时监听 `*.log` 文件变化，并将新日志推送到 Loki。
- **Loki (存储)**: 负责存储日志数据和索引（类似 Prometheus，但针对日志）。
- **Grafana (展示)**: 提供可视化的 Web 界面，用于查询、过滤日志和设置告警。

## 2. 目录结构说明

配置文件位于 `deploy/monitoring/` 目录下：

| 文件名 | 作用 |
| :--- | :--- |
| `docker-compose.yml` | 定义三个服务的容器编排配置。 |
| `loki-config.yaml` | Loki 的服务端配置（保留策略、存储路径等）。 |
| `promtail-config.yaml` | Promtail 的采集规则（定义要抓取的日志路径和标签）。 |
| `grafana-datasources.yml` | (可选) 自动预配 Grafana 数据源，实现开箱即用。 |

## 3. 快速启动 (Quick Start)

### 前置要求
- Windows/Mac/Linux 系统
- 已安装 **Docker Desktop** 或 Docker Engine

### 启动命令
在项目根目录下打开终端：

```powershell
# 1. 进入监控部署目录
cd deploy/monitoring

# 2. 启动服务 (后台运行)
docker-compose up -d

# 3. 查看容器状态
docker-compose ps
```

确保 `monitoring-loki-1`, `monitoring-promtail-1`, `monitoring-grafana-1` 状态均为 `Up`。

## 4. Grafana 配置指南

### 步骤 1: 登录系统
- **地址**: [http://localhost:3000](http://localhost:3000)
- **默认账号**: `admin`
- **默认密码**: `admin` (首次登录会提示修改密码，可选择 Skip)

### 步骤 2: 配置数据源 (Data Source)
*如果您使用了 `grafana-datasources.yml`，这一步通常会自动完成。如果需要手动配置：*

1. 点击左侧菜单 **Connections** -> **Data sources**。
2. 点击 **Add new data source**，选择 **Loki**。
3. 在 **Connection** -> **URL** 中填写：
   ```
   http://loki:3100
   ```
   > **注意**: 这里必须填写 Docker 容器内部的服务名 `loki`，**不能**填 `localhost` 或 `127.0.0.1`。
4. 点击底部的 **Save & test**，应显示绿色的 "Data source connected and labels found."。

## 5. 日志查询实战 (LogQL)

点击左侧菜单 **Explore**，在顶部下拉框选择 **Loki**，即可开始查询。

### 基础查询
查看所有 Procurator 相关的日志：
```logql
{job="procurator"}
```

### 关键词过滤
查找包含 "Error" 关键字的日志：
```logql
{job="procurator"} |= "Error"
```
查找**不包含** "DEBUG" 的日志：
```logql
{job="procurator"} != "DEBUG"
```

### 格式化显示 (JSON)
如果您的日志是 JSON 格式（Procurator 支持配置为 JSON 日志），可以自动解析字段：
```logql
{job="procurator"} | json
```
解析后过滤特定字段（例如过滤 status=failed）：
```logql
{job="procurator"} | json | status="failed"
```

## 6. 常见问题排查

**Q: Grafana 里查不到日志？**
1. 检查 Procurator 是否正在生成日志文件（查看 `logs/` 目录是否有更新）。
2. 检查 Promtail 容器日志，看是否成功挂载了路径：
   ```bash
   docker logs monitoring-promtail-1
   ```
3. 确保时间范围（Explore 右上角）选择正确，例如 "Last 1 hour"。

**Q: 如何停止监控服务？**
```bash
cd deploy/monitoring
docker-compose down
```
