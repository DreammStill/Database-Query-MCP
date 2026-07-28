#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MySQL MCP 服务器（跨版本兼容，基于纯 Python 的 pymysql 驱动）。

使用 stdio 传输与 MCP 客户端通信。
配置读取顺序：环境变量优先 -> 同目录 mysql_mcp_config.json 回退。

环境变量说明：
    MYSQL_HOST      主机地址（默认 127.0.0.1）
    MYSQL_PORT      端口（默认 3306）
    MYSQL_USER      用户名（必填）
    MYSQL_PASSWORD  密码（可为空）
    MYSQL_DATABASE  默认数据库（可选，工具调用时也可指定）
    MYSQL_CHARSET   字符集（默认 utf8mb4）
    MYSQL_SSL       是否启用 SSL（true/false，默认 false）
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymysql
from pymysql.cursors import DictCursor
from pymysql.err import MySQLError

from mcp.server.fastmcp import FastMCP


# 创建 MCP 服务器实例
mcp = FastMCP("mysql-mcp")

# 配置文件路径（与脚本/exe 同目录，仅当环境变量缺失时回退使用）
# PyInstaller 打包后 __file__ 指向临时解压目录，需用 sys.executable 定位 exe 所在路径
if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).resolve().parent
else:
    _BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = _BASE_DIR / "mysql_mcp_config.json"

# 默认查询返回上限，防止内存溢出
DEFAULT_LIMIT = 100


def load_config() -> Dict[str, Any]:
    """加载连接配置：环境变量优先，缺失时回退到同目录配置文件。"""
    env_keys = {
        "host": "MYSQL_HOST",
        "port": "MYSQL_PORT",
        "user": "MYSQL_USER",
        "password": "MYSQL_PASSWORD",
        "database": "MYSQL_DATABASE",
        "charset": "MYSQL_CHARSET",
        "ssl": "MYSQL_SSL",
    }
    config: Dict[str, Any] = {}
    for field, env_key in env_keys.items():
        val = os.environ.get(env_key)
        if val is not None:
            config[field] = val

    # 环境变量中缺少 host 时，回退到配置文件
    if not config.get("host") and CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            file_config = json.load(f)
        for k, v in file_config.items():
            if k not in config:
                config[k] = v

    config.setdefault("host", "127.0.0.1")
    config.setdefault("port", "3306")
    config.setdefault("charset", "utf8mb4")
    config.setdefault("ssl", "false")
    return config


_CONFIG = load_config()


def get_connection(db_name: Optional[str] = None):
    """创建并返回一个新的 MySQL 连接（DictCursor，结果以字典形式返回）。

    参数:
        db_name: 数据库名称，未指定时使用配置中的默认数据库
    """
    kwargs: Dict[str, Any] = {
        "host": _CONFIG["host"],
        "port": int(_CONFIG["port"]),
        "user": _CONFIG["user"],
        "password": _CONFIG.get("password", ""),
        "charset": _CONFIG["charset"],
        "cursorclass": DictCursor,
        "connect_timeout": 10,
    }
    db = db_name or _CONFIG.get("database")
    if db:
        kwargs["database"] = db
    if str(_CONFIG.get("ssl")).lower() == "true":
        kwargs["ssl"] = {"ssl": {}}
    return pymysql.connect(**kwargs)


def to_json(obj: Any) -> str:
    """将 Python 对象序列化为 JSON 字符串（兼容 datetime/Decimal 等）。"""
    return json.dumps(obj, ensure_ascii=False, default=str)


def safe_str(sql: str) -> str:
    """去除 SQL 末尾分号，避免 pymysql 多语句报错。"""
    return sql.strip().rstrip(";")


# ==================== MCP 工具定义 ====================


@mcp.tool()
def execute_sql(sql: str, db: Optional[str] = None) -> str:
    """执行任意 SQL 语句（SELECT / INSERT / UPDATE / DELETE / DDL 均可）。

    参数:
        sql: SQL 语句（支持单条，末尾分号会被自动去除）
        db: 数据库名称，未指定时使用默认数据库
    """
    try:
        conn = get_connection(db)
        try:
            with conn.cursor() as cur:
                cur.execute(safe_str(sql))
                # SELECT / SHOW / DESCRIBE 等有结果集
                if cur.description:
                    rows = cur.fetchmany(DEFAULT_LIMIT)
                    return to_json({
                        "columns": [d[0] for d in cur.description],
                        "rows": rows,
                        "truncated": cur.rowcount > len(rows),
                        "rowcount": cur.rowcount,
                    })
                # INSERT/UPDATE/DELETE/DDL 无结果集
                conn.commit()
                return to_json({"affected_rows": cur.rowcount})
        finally:
            conn.close()
    except MySQLError as e:
        return to_json({"error": f"MySQL Error {e.args[0]}: {e.args[1]}"})
    except Exception as e:
        return to_json({"error": str(e)})


@mcp.tool()
def list_databases() -> str:
    """列出 MySQL 中所有数据库。"""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SHOW DATABASES")
                rows = cur.fetchall()
                return to_json({"databases": [r[list(r.keys())[0]] for r in rows]})
        finally:
            conn.close()
    except MySQLError as e:
        return to_json({"error": f"MySQL Error {e.args[0]}: {e.args[1]}"})
    except Exception as e:
        return to_json({"error": str(e)})


@mcp.tool()
def list_tables(db: str) -> str:
    """列出指定数据库中的所有表。

    参数:
        db: 数据库名称
    """
    try:
        conn = get_connection(db)
        try:
            with conn.cursor() as cur:
                cur.execute("SHOW TABLES")
                rows = cur.fetchall()
                return to_json({"tables": [r[list(r.keys())[0]] for r in rows]})
        finally:
            conn.close()
    except MySQLError as e:
        return to_json({"error": f"MySQL Error {e.args[0]}: {e.args[1]}"})
    except Exception as e:
        return to_json({"error": str(e)})


@mcp.tool()
def describe_table(db: str, table: str) -> str:
    """查看表结构（字段名、类型、是否允许 NULL、键、默认值、额外信息）。

    参数:
        db: 数据库名称
        table: 表名称
    """
    try:
        conn = get_connection(db)
        try:
            with conn.cursor() as cur:
                cur.execute(f"DESCRIBE `{table}`")
                rows = cur.fetchall()
                return to_json(rows)
        finally:
            conn.close()
    except MySQLError as e:
        return to_json({"error": f"MySQL Error {e.args[0]}: {e.args[1]}"})
    except Exception as e:
        return to_json({"error": str(e)})


@mcp.tool()
def query(
    db: str,
    table: str,
    columns: Optional[List[str]] = None,
    where: Optional[str] = None,
    order_by: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> str:
    """便捷查询表数据（构造 SELECT 语句）。

    参数:
        db: 数据库名称
        table: 表名称
        columns: 查询列列表，如 ["id", "name"]；为空时查询所有列
        where: WHERE 条件（不含 WHERE 关键字），如 "age > 18 AND status = 1"
        order_by: 排序（不含 ORDER BY 关键字），如 "id DESC"
        limit: 返回上限，默认 100
        offset: 跳过的行数
    """
    try:
        col_part = ", ".join(f"`{c}`" for c in columns) if columns else "*"
        sql = f"SELECT {col_part} FROM `{table}`"
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"

        conn = get_connection(db)
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
                return to_json({
                    "sql": sql,
                    "columns": [d[0] for d in cur.description],
                    "rows": rows,
                    "rowcount": len(rows),
                })
        finally:
            conn.close()
    except MySQLError as e:
        return to_json({"error": f"MySQL Error {e.args[0]}: {e.args[1]}"})
    except Exception as e:
        return to_json({"error": str(e)})


@mcp.tool()
def execute(
    db: str,
    table: str,
    operation: str,
    data: Dict[str, Any],
    where: Optional[str] = None,
) -> str:
    """便捷写操作（构造 INSERT / UPDATE / DELETE 语句）。

    参数:
        db: 数据库名称
        table: 表名称
        operation: 操作类型，取值 insert / update / delete
        data: 写入字段与值，如 {"name": "test", "age": 20}（insert/update 使用）
        where: 更新/删除条件（不含 WHERE 关键字），update/delete 必填
    """
    try:
        op = operation.strip().lower()
        conn = get_connection(db)
        try:
            with conn.cursor() as cur:
                if op == "insert":
                    cols = list(data.keys())
                    placeholders = ", ".join(["%s"] * len(cols))
                    col_str = ", ".join(f"`{c}`" for c in cols)
                    sql = f"INSERT INTO `{table}` ({col_str}) VALUES ({placeholders})"
                    cur.execute(sql, [data[c] for c in cols])
                    conn.commit()
                    return to_json({
                        "affected_rows": cur.rowcount,
                        "lastrowid": cur.lastrowid,
                        "sql": sql,
                    })
                elif op == "update":
                    if not where:
                        return to_json({"error": "update 操作必须提供 where 条件"})
                    set_part = ", ".join(f"`{k}` = %s" for k in data.keys())
                    sql = f"UPDATE `{table}` SET {set_part} WHERE {where}"
                    cur.execute(sql, list(data.values()))
                    conn.commit()
                    return to_json({"affected_rows": cur.rowcount, "sql": sql})
                elif op == "delete":
                    if not where:
                        return to_json({"error": "delete 操作必须提供 where 条件"})
                    sql = f"DELETE FROM `{table}` WHERE {where}"
                    cur.execute(sql)
                    conn.commit()
                    return to_json({"affected_rows": cur.rowcount, "sql": sql})
                else:
                    return to_json({"error": f"不支持的操作类型: {operation}，可选: insert/update/delete"})
        finally:
            conn.close()
    except MySQLError as e:
        return to_json({"error": f"MySQL Error {e.args[0]}: {e.args[1]}"})
    except Exception as e:
        return to_json({"error": str(e)})


@mcp.tool()
def server_info() -> str:
    """获取 MySQL 服务器信息（版本、连接信息），可用于连通性测试。

    兼容 MySQL / MariaDB / Doris（Doris 不支持 @@hostname 等系统变量，自动降级）。
    """
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                # 使用兼容性更好的查询，@@hostname 在 Doris 中不存在，用 try 降级
                try:
                    cur.execute("SELECT VERSION() AS version, DATABASE() AS db, CURRENT_USER() AS user, @@hostname AS host, @@port AS port")
                except MySQLError:
                    # Doris 等不支持的系统变量时降级查询
                    cur.execute("SELECT VERSION() AS version, DATABASE() AS db, CURRENT_USER() AS user")
                info = cur.fetchone()
                return to_json(info)
        finally:
            conn.close()
    except MySQLError as e:
        return to_json({"error": f"MySQL Error {e.args[0]}: {e.args[1]}"})
    except Exception as e:
        return to_json({"error": str(e)})


if __name__ == "__main__":
    mcp.run()
