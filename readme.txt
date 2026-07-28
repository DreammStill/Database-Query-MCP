# 1. 构建镜像
chmod +x docker/build.sh
./docker/build.sh

# 2. 运行（MCP 客户端 mcp.json 配置示例）
# Metabase
docker run -i --rm \
  -e METABASE_USERNAME=xxx \
  -e METABASE_PASSWORD=xxx \
  db-mcp:latest metabase_mcp.py

# MySQL（访问宿主机数据库需用 host.docker.internal）
docker run -i --rm \
  -e MYSQL_HOST=host.docker.internal \
  -e MYSQL_USER=root \
  -e MYSQL_PASSWORD=xxx \
  --add-host=host.docker.internal:host-gateway \
  db-mcp:latest mysql_mcp.py

# MongoDB
docker run -i --rm \
  -e MONGO_HOST=host.docker.internal \
  -e MONGO_USER=root \
  -e MONGO_PASSWORD=xxx \
  --add-host=host.docker.internal:host-gateway \
  db-mcp:latest mongo_legacy_mcp.py