# Metabase MCP 配置指南

## 概述

`metabase_mcp.exe` 是一个独立的 Metabase MCP 服务器，基于 Metabase REST API，已打包为单文件 exe，**无需目标机器安装 Python 环境即可运行**。

核心特性：
1. **自动登录**：首次调用或 session 失效时自动调用 `/api/session` 获取新 token
2. **失效重试**：API 返回 401 时自动重新登录并重试一次
3. **双查询模式**：SQL（`SELECT ...`）与 Mongo 管道（`[{"$match": {...}}]`）统一入口
4. **结果过滤**：`summarize=True` 时只返回关键信息（列名+行数据），去除冗余元数据
5. **只读查询**：仅支持查询类操作，不提供任何修改/删除接口

---

## 一、文件清单

| 文件 | 说明 |
|------|------|
| `metabase_mcp.exe` | 主程序（Windows 64位），已内嵌 Python 运行时与所有依赖 |
| `metabase_mcp_config.json` | 配置文件（可选，与 exe 同目录，用于回退读取凭据） |
| `metabase_mcp.py` | 源代码（仅供维护参考，运行时不需要） |

---

## 二、可用工具

共 10 个工具（均为只读查询）：

| 工具名 | 功能 | 说明 |
|--------|------|------|
| `server_status` | 服务器状态 | 返回当前用户、数据库总数，可用于连通性测试 |
| `list_databases` | 列出所有数据库 | 返回 id/name/engine |
| `get_database` | 数据库详情 | 返回引擎、版本、描述 |
| `get_database_metadata` | 数据库元数据 | 返回**所有**表名、字段名、字段类型（数据量大） |
| `get_table_metadata` | 单表元数据 | 返回**指定表**的字段名、类型、是否主键等（推荐使用，避免返回全库元数据） |
| `describe_table` | 表结构及注释 | 查询 INFORMATION_SCHEMA.COLUMNS，返回字段名、类型、**字段注释**（仅关系型数据库） |
| `get_database_fields` | 数据库字段 | 跨表返回所有字段信息 |
| `list_cards` | 已保存查询列表 | 返回 id/name/database_id |
| `execute_card` | 执行已保存查询 | 按 card_id 执行并返回结果 |
| `execute_query` | 原生查询 | **核心工具**，支持 SQL 与 Mongo 管道 |

---

## 三、环境变量配置

通过环境变量传递连接信息（**配置时写在 mcp.json 的 `env` 字段中**）：

| 环境变量 | 必填 | 默认值 | 说明 |
|----------|------|--------|------|
| `METABASE_URL` | 否 | - | 服务器地址 |
| `METABASE_USERNAME` | 二选一 | - | 登录用户名（账号密码方式） |
| `METABASE_PASSWORD` | 二选一 | - | 登录密码（账号密码方式） |
| `METABASE_SESSION` | 二选一 | - | 现成 session token（跳过登录） |

> **认证方式**：
> - **账号密码方式（推荐）**：设置 `METABASE_USERNAME` + `METABASE_PASSWORD`，MCP 自动登录并管理 session，失效自动重登
> - **Session 方式**：设置 `METABASE_SESSION`，直接使用现成 token，失效后需手动更换
> - 两者都配置时，优先使用 Session；Session 失效后自动回退到账号密码登录

> **回退机制**：若环境变量缺失，程序会自动读取与 exe 同目录的 `metabase_mcp_config.json`。

---

## 四、Trae MCP 配置示例

打开 Trae 的 MCP 配置文件（路径通常为 `C:\Users\<用户名>\AppData\Roaming\Trae\User\mcp.json`），在 `mcpServers` 中添加一个条目。

### 示例 1：账号密码方式（推荐）

```json
"Metabase": {
    "command": "C:\\path\\to\\metabase_mcp.exe",
    "args": [],
    "env": {
        "METABASE_URL": "https://metabase.yoururl.com",
        "METABASE_USERNAME": "your_username",
        "METABASE_PASSWORD": "your_password",
        "PYTHONIOENCODING": "utf-8"
    }
}
```

### 示例 2：Session 方式

```json
"Metabase": {
    "command": "C:\\path\\to\\metabase_mcp.exe",
    "args": [],
    "env": {
        "METABASE_URL": "https://metabase.yoururl.com",
        "METABASE_SESSION": "your_session_token",
        "PYTHONIOENCODING": "utf-8"
    }
}
```

### 示例 3：配置文件方式（密码不写在 mcp.json 中）

将凭据放入与 exe 同目录的 `metabase_mcp_config.json`：

```json
{
    "url": "https://metabase.yoururl.com",
    "username": "your_username",
    "password": "your_password"
}
```

此时 mcp.json 可简化为：

```json
"Metabase": {
    "command": "C:\\path\\to\\metabase_mcp.exe",
    "args": [],
    "env": {
        "PYTHONIOENCODING": "utf-8"
    }
}
```

> 优先级：环境变量 > 配置文件 > 默认值。

> **注意**：
> 1. 把 `command` 中的路径替换为 exe 在你机器上的**实际绝对路径**（反斜杠需转义为 `\\`）。
> 2. 配置完成后需**重启 Trae** 使其生效。

---

## 五、跨机器分发

1. 复制 `metabase_mcp.exe` 到目标 Windows 机器（任意路径）。
2. 如使用配置文件方式，将 `metabase_mcp_config.json` 复制到与 exe **同目录**。
3. 按上文示例配置目标机器的 `mcp.json`，将 `command` 指向 exe 实际路径。
4. 重启 Trae。

无需安装 Python、requests 或任何其他依赖。

---

## 六、工具调用示例（MCP 客户端视角）

### 连通性测试

| 操作 | 工具 | 参数示例 |
|------|------|----------|
| 测试连通性 | `server_status` | `{}` |

### 数据库探索

| 操作 | 工具 | 参数示例 |
|------|------|----------|
| 列出数据库 | `list_databases` | `{"summarize": true}` |
| 数据库详情 | `get_database` | `{"database_id": 51, "summarize": true}` |
| 数据库元数据（表/字段） | `get_database_metadata` | `{"database_id": 51, "summarize": true}` |
| 单表元数据（推荐） | `get_table_metadata` | `{"database_id": 51, "table_name": "listing_sku", "summarize": true}` |
| 表结构及注释 | `describe_table` | `{"database_id": 51, "table_name": "listing_sku", "table_schema": "data_center"}` |
| 数据库字段列表 | `get_database_fields` | `{"database_id": 51, "summarize": true}` |

### 查询执行

| 操作 | 工具 | 参数示例 |
|------|------|----------|
| SQL 查询（精简） | `execute_query` | `{"database_id": 51, "query": "SELECT COUNT(*) AS cnt FROM ac_amazon_products", "summarize": true}` |
| SQL 查询（完整） | `execute_query` | `{"database_id": 51, "query": "SELECT * FROM ac_amazon_products LIMIT 10", "summarize": false}` |
| Mongo 管道查询 | `execute_query` | `{"database_id": 44, "query": "[{\"$match\": {\"status\": 1}}, {\"$limit\": 10}]", "collection": "amazon_acc_daily_stats"}` |

### 已保存查询

| 操作 | 工具 | 参数示例 |
|------|------|----------|
| 列出已保存查询 | `list_cards` | `{"summarize": true}` |
| 执行已保存查询 | `execute_card` | `{"card_id": 661, "summarize": true}` |

---

## 七、查询类型自动识别

`execute_query` 工具根据 `query` 参数的内容自动判断查询类型：

| 格式 | 识别为 | 示例 | 需要 collection |
|------|--------|------|----------------|
| 以 `[` 开头且为合法 JSON 数组 | MongoDB 聚合管道 | `[{"$match": {"uni_code": "abc"}}]` | 是 |
| 其他 | SQL | `SELECT * FROM table WHERE id > 100` | 否 |

> **Mongo 管道查询必须提供 `collection` 参数**，可通过 `get_database_metadata` 获取可用集合列表。
>
> **SQL 查询自动追加 LIMIT**：若未包含 `limit` 关键字，会自动追加 `LIMIT 100`（可通过 `limit` 参数调整）。

---

## 八、summarize 参数说明

所有工具均支持 `summarize` 参数（默认 `true`）：

| summarize | 效果 |
|-----------|------|
| `true`（默认） | 只返回关键信息（列名 + 行数据），响应简洁 |
| `false` | 返回 Metabase 完整响应（含 cols/field_ref/fingerprint 等元数据） |

**SQL 查询对比示例**：

`summarize=true`：
```json
{"columns": ["cnt"], "rows": [[0]], "row_count": 1, "status": "completed"}
```

`summarize=false`（截断）：
```json
{"data": {"rows": [[0]], "cols": [{"display_name": "cnt", "field_ref": ["field", "cnt", {"base-type": "type/BigInteger"}], ...}], ...}}
```
