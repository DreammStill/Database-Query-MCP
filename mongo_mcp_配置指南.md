# MongoDB MCP 配置指南

## 概述

`mongo_legacy_mcp.exe` 是一个独立的 MongoDB MCP 服务器，基于 `pymongo 3.13.0` 驱动，已打包为单文件 exe，**无需目标机器安装 Python 环境即可运行**。

特别说明：`pymongo 3.x` 系列同时兼容 **MongoDB 3.2（wire version 4）等老旧版本**与高版本（4.x/5.x/6.x），可解决 Node.js 版 `mcp-mongo-server` 因驱动要求 wire version ≥ 8 而无法连接老库的问题。

适用于 Trae / Cursor 等 MCP 客户端。

---

## 一、文件清单

| 文件 | 说明 |
|------|------|
| `mongo_legacy_mcp.exe` | 主程序（Windows 64位），已内嵌 Python 运行时与所有依赖 |
| `mongo_legacy_mcp.py` | 源代码（仅供维护参考，运行时不需要） |

---

## 二、可用工具

共 9 个工具：

| 工具名 | 功能 | 说明 |
|--------|------|------|
| `list_databases` | 列出所有数据库 | |
| `list_collections` | 列出指定库的集合 | 需传 `db` 参数 |
| `find` | 查询文档 | 支持 filter / projection / sort / limit / skip，_id 自动转换 |
| `aggregate` | 聚合管道 | 执行 pipeline 阶段列表 |
| `count` | 统计文档数 | 按条件统计 |
| `insert` | 插入文档 | 支持单条/多条 |
| `update` | 更新文档 | 支持 multi / upsert |
| `delete` | 删除文档 | 支持单条/多条 |
| `server_info` | 服务器信息 | 版本、连接信息，可用于连通性测试 |

> 便利特性：`_id` 为 24 位 hex 字符串时，`find`/`count`/`update`/`delete` 会自动转为 ObjectId，无需手动构造。

---

## 三、环境变量配置

通过环境变量传递连接信息（**配置时写在 mcp.json 的 `env` 字段中**）：

| 环境变量 | 必填 | 默认值 | 说明 |
|----------|------|--------|------|
| `MONGO_HOST` | 是 | 127.0.0.1 | 主机地址 |
| `MONGO_PORT` | 否 | 27017 | 端口 |
| `MONGO_USER` | 否 | - | 用户名（填写即启用认证） |
| `MONGO_PASSWORD` | 否 | 空 | 密码 |
| `MONGO_AUTH_SOURCE` | 否 | admin | 认证库 |
| `MONGO_AUTH_MECHANISM` | 否 | SCRAM-SHA-1 | 认证机制（老版本建议默认） |
| `MONGO_DB` | 否 | - | 默认数据库（工具调用时也可单独指定） |
| `MONGO_REPLICA_SET` | 否 | - | 副本集名称（可选） |
| `PYTHONIOENCODING` | 建议填 | utf-8 | 强制 UTF-8 输出，避免 Windows 终端编码问题 |

> **回退机制**：若环境变量缺失，程序会自动读取同目录下的 `mongo_mcp_config.json`（格式见文末）。

---

## 四、Trae MCP 配置示例

打开 Trae 的 MCP 配置文件（路径通常为 `C:\Users\<用户名>\AppData\Roaming\Trae\User\mcp.json`），在 `mcpServers` 中添加一个条目。

### 示例 1：连接老旧 MongoDB 3.2（228 服务器，需认证）

```json
"MongoDB 228": {
    "command": "C:\\path\\to\\mongo_legacy_mcp.exe",
    "args": [],
    "env": {
        "MONGO_HOST": "192.168.1.228",
        "MONGO_PORT": "27017",
        "MONGO_USER": "root",
        "MONGO_PASSWORD": "your_password",
        "MONGO_AUTH_SOURCE": "admin",
        "PYTHONIOENCODING": "utf-8"
    }
}
```

### 示例 2：连接高版本 MongoDB（251 服务器）

```json
"MongoDB 251": {
    "command": "C:\\path\\to\\mongo_legacy_mcp.exe",
    "args": [],
    "env": {
        "MONGO_HOST": "192.168.1.251",
        "MONGO_PORT": "27017",
        "MONGO_USER": "dev_yf_rw",
        "MONGO_PASSWORD": "your_password",
        "MONGO_AUTH_SOURCE": "admin",
        "PYTHONIOENCODING": "utf-8"
    }
}
```

### 示例 3：连接 120 服务器（crawler 账号）

```json
"MongoDB 120": {
    "command": "C:\\path\\to\\mongo_legacy_mcp.exe",
    "args": [],
    "env": {
        "MONGO_HOST": "192.168.1.120",
        "MONGO_PORT": "27017",
        "MONGO_USER": "crawer",
        "MONGO_PASSWORD": "your_password",
        "MONGO_AUTH_SOURCE": "admin",
        "PYTHONIOENCODING": "utf-8"
    }
}
```

### 示例 4：无认证连接（本地开发库）

```json
"MongoDB Local": {
    "command": "C:\\path\\to\\mongo_legacy_mcp.exe",
    "args": [],
    "env": {
        "MONGO_HOST": "127.0.0.1",
        "MONGO_PORT": "27017",
        "PYTHONIOENCODING": "utf-8"
    }
}
```

> **注意**：
> 1. 把 `command` 中的路径替换为 exe 在你机器上的**实际绝对路径**（反斜杠需转义为 `\\`）。
> 2. 多个 MongoDB 实例可同时配置多个条目，key 名（如 "MongoDB 228"）不可重复。
> 3. 配置完成后需**重启 Trae** 使其生效。
> 4. **密码无需 URL 编码**（旧版 Node 驱动连接串里的 `%40`、`%3B` 等 URL 编码在本工具中不需要）。

---

## 五、配置文件回退方式（可选）

如果不想把密码写在 mcp.json 的 env 里，可将连接信息放入与 exe 同目录的 `mongo_mcp_config.json`：

```json
{
    "host": "192.168.1.228",
    "port": "27017",
    "username": "root",
    "password": "your_password",
    "authSource": "admin",
    "database": "vspider"
}
```

此时 mcp.json 可简化为：

```json
"MongoDB 228": {
    "command": "C:\\path\\to\\mongo_legacy_mcp.exe",
    "args": [],
    "env": {
        "PYTHONIOENCODING": "utf-8"
    }
}
```

> 优先级：环境变量 > 配置文件 > 默认值。

---

## 六、跨机器分发

1. 复制 `mongo_legacy_mcp.exe` 到目标 Windows 机器（任意路径）。
2. 按上文示例配置目标机器的 `mcp.json`，将 `command` 指向 exe 实际路径。
3. 重启 Trae。

无需安装 Python、pymongo 或任何其他依赖。

---

## 七、工具调用示例（MCP 客户端视角）

| 操作 | 工具 | 参数示例 |
|------|------|----------|
| 测试连通性 | `server_info` | `{}` |
| 列出数据库 | `list_databases` | `{}` |
| 列出集合 | `list_collections` | `{"db": "vspider"}` |
| 查询文档 | `find` | `{"db": "vspider", "collection": "vspider_task_record", "filter": {"status": 1}, "limit": 10}` |
| 按 _id 查询 | `find` | `{"db": "vspider", "collection": "xxx", "filter": {"_id": "693afec75ca6e15551ff9877"}}` |
| 聚合查询 | `aggregate` | `{"db": "vspider", "collection": "vspider_task_record", "pipeline": [{"$match": {"status": 1}}, {"$group": {"_id": "$source_system", "count": {"$sum": 1}}}]}` |
| 统计数量 | `count` | `{"db": "vspider", "collection": "vspider_task_record", "filter": {"status": 1}}` |
| 插入单条 | `insert` | `{"db": "test", "collection": "demo", "documents": {"name": "test", "age": 20}}` |
| 插入多条 | `insert` | `{"db": "test", "collection": "demo", "documents": [{"name": "a"}, {"name": "b"}]}` |
| 更新单条 | `update` | `{"db": "test", "collection": "demo", "filter": {"name": "test"}, "update": {"$set": {"age": 21}}}` |
| 更新多条 | `update` | `{"db": "test", "collection": "demo", "filter": {"status": 0}, "update": {"$set": {"status": 1}}, "multi": true}` |
| 删除单条 | `delete` | `{"db": "test", "collection": "demo", "filter": {"name": "test"}}` |
| 删除多条 | `delete` | `{"db": "test", "collection": "demo", "filter": {"status": 0}, "multi": true}` |

---

## 八、与旧版 Node.js MCP 的对比

| 对比项 | 旧版 `mcp-mongo-server` (Node.js) | 本工具 `mongo_legacy_mcp.exe` (pymongo) |
|--------|-----------------------------------|------------------------------------------|
| 最低支持版本 | MongoDB 4.2（wire version 8） | MongoDB 3.2（wire version 4） |
| 连接 228 (3.2.9) | 报错：requires at least 8 | 正常连接 |
| 连接高版本 | 支持 | 支持 |
| 密码格式 | 需 URL 编码（`%40` 等） | 明文即可 |
| 运行时依赖 | 需要 Node.js / npx | 无（exe 自包含） |
