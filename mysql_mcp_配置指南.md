# MySQL MCP 配置指南

## 概述

`mysql_mcp.exe` 是一个独立的 MySQL MCP 服务器，基于纯 Python 的 `pymysql` 驱动，已打包为单文件 exe，**无需目标机器安装 Python 环境即可运行**。

适用于 Trae / Cursor 等 MCP 客户端，支持连接 MySQL / MariaDB / Doris(MySQL协议) 等兼容 MySQL 协议的数据库。

---

## 一、文件清单

| 文件 | 说明 |
|------|------|
| `mysql_mcp.exe` | 主程序（Windows 64位），已内嵌 Python 运行时与所有依赖 |
| `mysql_mcp.py` | 源代码（仅供维护参考，运行时不需要） |

---

## 二、可用工具

共 7 个工具：

| 工具名 | 功能 | 说明 |
|--------|------|------|
| `execute_sql` | 执行任意 SQL | 支持 SELECT/INSERT/UPDATE/DELETE/DDL，通用入口 |
| `list_databases` | 列出所有数据库 | |
| `list_tables` | 列出指定库的表 | 需传 `db` 参数 |
| `describe_table` | 查看表结构 | 返回字段名、类型、是否NULL、键、默认值 |
| `query` | 便捷查询 | 按列/条件/排序/分页构造 SELECT，无需手写SQL |
| `execute` | 便捷写操作 | insert/update/delete，自动参数化防注入 |
| `server_info` | 服务器信息 | 版本、当前库、当前用户，可用于连通性测试 |

---

## 三、环境变量配置

通过环境变量传递连接信息（**配置时写在 mcp.json 的 `env` 字段中**）：

| 环境变量 | 必填 | 默认值 | 说明 |
|----------|------|--------|------|
| `MYSQL_HOST` | 是 | 127.0.0.1 | 数据库主机地址 |
| `MYSQL_PORT` | 否 | 3306 | 端口 |
| `MYSQL_USER` | 是 | - | 用户名 |
| `MYSQL_PASSWORD` | 否 | 空 | 密码 |
| `MYSQL_DATABASE` | 否 | - | 默认数据库（工具调用时也可单独指定） |
| `MYSQL_CHARSET` | 否 | utf8mb4 | 字符集 |
| `MYSQL_SSL` | 否 | false | 是否启用 SSL（true/false） |
| `PYTHONIOENCODING` | 建议填 | utf-8 | 强制 UTF-8 输出，避免 Windows 终端编码问题 |

> **回退机制**：若环境变量缺失，程序会自动读取同目录下的 `mysql_mcp_config.json`（格式见文末）。

---

## 四、Trae MCP 配置示例

打开 Trae 的 MCP 配置文件（路径通常为 `C:\Users\<用户名>\AppData\Roaming\Trae\User\mcp.json`），在 `mcpServers` 中添加一个条目。

### 示例 1：连接 ssc 库（MySQL）

```json
"MySQL Server": {
    "command": "C:\\path\\to\\mysql_mcp.exe",
    "args": [],
    "env": {
        "MYSQL_HOST": "192.168.1.19",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "star",
        "MYSQL_PASSWORD": "your_password",
        "MYSQL_DATABASE": "ssc",
        "PYTHONIOENCODING": "utf-8"
    }
}
```

### 示例 2：连接 starpro 库（MariaDB）

```json
"MariaDB Server": {
    "command": "C:\\path\\to\\mysql_mcp.exe",
    "args": [],
    "env": {
        "MYSQL_HOST": "192.168.1.133",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "oms",
        "MYSQL_PASSWORD": "your_password",
        "MYSQL_DATABASE": "starpro",
        "PYTHONIOENCODING": "utf-8"
    }
}
```

### 示例 3：连接 Doris（MySQL 协议）

```json
"Doris Server": {
    "command": "C:\\path\\to\\mysql_mcp.exe",
    "args": [],
    "env": {
        "MYSQL_HOST": "192.168.1.74",
        "MYSQL_PORT": "9030",
        "MYSQL_USER": "dev_ops",
        "MYSQL_PASSWORD": "your_password",
        "MYSQL_DATABASE": "data_center",
        "PYTHONIOENCODING": "utf-8"
    }
}
```

> **注意**：
> 1. 把 `command` 中的路径替换为 exe 在你机器上的**实际绝对路径**（反斜杠需转义为 `\\`）。
> 2. 多个数据库可同时配置多个条目，key 名（如 "MySQL Server"）不可重复。
> 3. 配置完成后需**重启 Trae** 使其生效。

---

## 五、配置文件回退方式（可选）

如果不想把密码写在 mcp.json 的 env 里，可将连接信息放入与 exe 同目录的 `mysql_mcp_config.json`：

```json
{
    "host": "192.168.1.19",
    "port": "3306",
    "user": "star",
    "password": "your_password",
    "database": "ssc",
    "charset": "utf8mb4"
}
```

此时 mcp.json 可简化为：

```json
"MySQL Server": {
    "command": "C:\\path\\to\\mysql_mcp.exe",
    "args": [],
    "env": {
        "PYTHONIOENCODING": "utf-8"
    }
}
```

> 优先级：环境变量 > 配置文件 > 默认值。

---

## 六、跨机器分发

1. 复制 `mysql_mcp.exe` 到目标 Windows 机器（任意路径）。
2. 按上文示例配置目标机器的 `mcp.json`，将 `command` 指向 exe 实际路径。
3. 重启 Trae。

无需安装 Python、pymysql 或任何其他依赖。

---

## 七、工具调用示例（MCP 客户端视角）

| 操作 | 工具 | 参数示例 |
|------|------|----------|
| 测试连通性 | `server_info` | `{}` |
| 列出数据库 | `list_databases` | `{}` |
| 列出表 | `list_tables` | `{"db": "ssc"}` |
| 查看表结构 | `describe_table` | `{"db": "ssc", "table": "aliexpress_listing"}` |
| 便捷查询 | `query` | `{"db": "ssc", "table": "aliexpress_category", "columns": ["id","category_id"], "where": "id > 1000", "limit": 10}` |
| 插入数据 | `execute` | `{"db": "ssc", "table": "test", "operation": "insert", "data": {"name": "test", "age": 20}}` |
| 更新数据 | `execute` | `{"db": "ssc", "table": "test", "operation": "update", "data": {"age": 21}, "where": "name = 'test'"}` |
| 删除数据 | `execute` | `{"db": "ssc", "table": "test", "operation": "delete", "where": "name = 'test'"}` |
| 执行任意SQL | `execute_sql` | `{"sql": "SELECT COUNT(*) FROM aliexpress_category", "db": "ssc"}` |
