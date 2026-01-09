# 使用官方轻量级 Python 镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CONTAINER_ENV=true
# 设置默认端口环境变量，可在 docker run 时覆盖
ENV SERVER_PORT=50002

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 创建数据和日志目录
RUN mkdir -p /app/data /app/logs

# 声明端口 (仅作为文档说明，实际监听端口由 CMD 决定)
EXPOSE $SERVER_PORT

# 启动命令改为 Shell 模式以支持变量替换
# 使用 sh -c 显式解析环境变量
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${SERVER_PORT:-50002} --workers 4"]
