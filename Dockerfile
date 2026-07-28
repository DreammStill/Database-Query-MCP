# ============================================================
# 数据库 MCP 服务器 Docker 镜像（Metabase / MySQL / MongoDB 三合一）
#
# 三个 MCP 共用一个镜像，运行时通过 CMD 参数指定启动哪个：
#   docker run -i --rm <image> metabase_mcp.py
#   docker run -i --rm <image> mysql_mcp.py
#   docker run -i --rm <image> mongo_legacy_mcp.py
# ============================================================

FROM python:3.13-slim

# 设置工作目录
WORKDIR /app

# 设置时区与编码
ENV PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

# 安装系统依赖（tzdata 用于时区设置）
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY docker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 复制三个 MCP 源码
COPY metabase_mcp.py mysql_mcp.py mongo_legacy_mcp.py /app/

# 默认入口：python 运行指定脚本
ENTRYPOINT ["python"]
CMD ["metabase_mcp.py"]
