#!/bin/bash
# ============================================================
# 数据库 MCP Docker 镜像构建脚本
#
# 用途：在 Linux / Mac 上构建包含三个 MCP 的 Docker 镜像
# 使用方法：
#   chmod +x docker/build.sh
#   ./docker/build.sh
#
# 构建完成后会生成镜像 db-mcp:latest（三合一）
# 运行时通过参数指定启动哪个 MCP：
#   docker run -i --rm -e METABASE_USERNAME=xxx -e METABASE_PASSWORD=xxx db-mcp:latest metabase_mcp.py
#   docker run -i --rm -e MYSQL_USER=xxx -e MYSQL_PASSWORD=xxx db-mcp:latest mysql_mcp.py
#   docker run -i --rm -e MONGO_HOST=xxx -e MONGO_USER=xxx -e MONGO_PASSWORD=xxx db-mcp:latest mongo_legacy_mcp.py
# ============================================================

set -e

# 镜像名称与标签
IMAGE_NAME="db-mcp"
IMAGE_TAG="latest"

# 构建上下文为项目根目录（脚本所在目录的上一级）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo " 构建数据库 MCP Docker 镜像"
echo " 镜像: ${IMAGE_NAME}:${IMAGE_TAG}"
echo " 上下文: ${PROJECT_ROOT}"
echo "=========================================="

cd "$PROJECT_ROOT"

docker build \
    -f docker/Dockerfile \
    -t "${IMAGE_NAME}:${IMAGE_TAG}" \
    .

echo ""
echo "=========================================="
echo " 构建完成！"
echo "=========================================="
echo ""
echo "镜像列表："
docker images "${IMAGE_NAME}:${IMAGE_TAG}"
echo ""
echo "使用方式（Trae / Claude 等 MCP 客户端配置 mcp.json）："
echo ""
echo "--- Metabase MCP ---"
echo '{'
echo '  "mcpServers": {'
echo '    "Metabase": {'
echo '      "command": "docker",'
echo '      "args": ["run", "-i", "--rm", "-e", "METABASE_USERNAME=your_username", "-e", "METABASE_PASSWORD=your_password", "db-mcp:latest", "metabase_mcp.py"]'
echo '    }'
echo '  }'
echo '}'
echo ""
echo "--- MySQL MCP ---"
echo '{'
echo '  "mcpServers": {'
echo '    "MySQL": {'
echo '      "command": "docker",'
echo '      "args": ["run", "-i", "--rm", "-e", "MYSQL_HOST=127.0.0.1", "-e", "MYSQL_USER=root", "-e", "MYSQL_PASSWORD=your_password", "--add-host=host.docker.internal:host-gateway", "db-mcp:latest", "mysql_mcp.py"]'
echo '    }'
echo '  }'
echo '}'
echo ""
echo "--- MongoDB MCP ---"
echo '{'
echo '  "mcpServers": {'
echo '    "MongoDB": {'
echo '      "command": "docker",'
echo '      "args": ["run", "-i", "--rm", "-e", "MONGO_HOST=127.0.0.1", "-e", "MONGO_USER=root", "-e", "MONGO_PASSWORD=your_password", "--add-host=host.docker.internal:host-gateway", "db-mcp:latest", "mongo_legacy_mcp.py"]'
echo '    }'
echo '  }'
echo '}'
echo ""
echo "注意："
echo "  1. 容器内无法直接访问宿主机 127.0.0.1，需使用 host.docker.internal 访问宿主机服务"
echo "  2. Linux 上需要添加 --add-host=host.docker.internal:host-gateway 参数"
echo "  3. 如数据库在远程服务器，直接使用远程 IP 即可"
echo "  4. 也可使用 docker network 连接到同一网络中的数据库容器"
