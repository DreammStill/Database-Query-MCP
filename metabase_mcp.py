#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Metabase MCP 服务器（只读查询，支持原生 SQL 与 MongoDB 聚合管道）。

基于 Metabase REST API，使用 stdio 传输与 MCP 客户端通信。
配置读取顺序：环境变量优先 -> 同目录 metabase_mcp_config.json 回退。

核心特性：
1. 自动登录：首次调用或 session 失效时自动调用 /api/session 获取新 token
2. 失效重试：API 返回 401 时自动重新登录并重试一次
3. 双查询模式：SQL（SELECT ...）与 Mongo 管道（[{"$match": {...}}]）统一入口
4. 结果过滤：summarize=True 时只返回关键信息，去除冗余元数据

环境变量说明：
    METABASE_URL       服务器地址（默认 https://metabase.starmerx.com）
    METABASE_USERNAME  登录用户名
    METABASE_PASSWORD  登录密码
    METABASE_SESSION   可选，直接传入现成 session token（跳过登录）
"""

import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests.exceptions import RequestException

from mcp.server.fastmcp import FastMCP


# 创建 MCP 服务器实例
mcp = FastMCP("metabase-mcp")

# 配置文件路径（与脚本/exe 同目录，仅当环境变量缺失时回退使用）
# PyInstaller 打包后 __file__ 指向临时解压目录，需用 sys.executable 定位 exe 所在路径
if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).resolve().parent
else:
    _BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = _BASE_DIR / "metabase_mcp_config.json"

# 默认查询返回上限，防止响应过大
DEFAULT_LIMIT = 100


def load_config() -> Dict[str, Any]:
    """加载连接配置：环境变量优先，缺失时回退到同目录配置文件。"""
    env_keys = {
        "url": "METABASE_URL",
        "username": "METABASE_USERNAME",
        "password": "METABASE_PASSWORD",
        "session": "METABASE_SESSION",
    }
    config: Dict[str, Any] = {}
    for field, env_key in env_keys.items():
        val = os.environ.get(env_key)
        if val is not None:
            config[field] = val

    # 环境变量中缺少 url 时，回退到配置文件
    if not config.get("url") and CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            file_config = json.load(f)
        for k, v in file_config.items():
            if k not in config:
                config[k] = v

    config.setdefault("url", "https://metabase.starmerx.com")
    # 规范化 URL：去除末尾斜杠
    config["url"] = config["url"].rstrip("/")
    return config


_CONFIG = load_config()

# Session token 缓存（内存）
_session: Optional[str] = _CONFIG.get("session")


def _login() -> str:
    """调用 /api/session 登录获取 session token。"""
    username = _CONFIG.get("username")
    password = _CONFIG.get("password")
    if not username or not password:
        raise ValueError(
            "缺少 Metabase 登录凭据，请通过环境变量 METABASE_USERNAME/METABASE_PASSWORD "
            "或配置文件 metabase_mcp_config.json 提供"
        )
    resp = requests.post(
        f"{_CONFIG['url']}/api/session",
        json={"username": username, "password": password},
        timeout=30,
        headers={"Content-Type": "application/json"},
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("id")
    if not token:
        raise ValueError(f"登录响应中未包含 session id: {data}")
    return token


def get_session() -> str:
    """获取当前有效的 session token，不存在则自动登录。"""
    global _session
    if not _session:
        _session = _login()
    return _session


def _request(
    method: str,
    path: str,
    *,
    json_body: Optional[Dict] = None,
    params: Optional[Dict] = None,
    _retried: bool = False,
) -> Any:
    """发送带认证的 HTTP 请求，session 失效时自动重新登录并重试一次。

    参数:
        method: HTTP 方法（GET/POST）
        path: 接口路径（以 /api 开头）
        json_body: 请求体（POST 时使用）
        params: 查询参数
        _retried: 内部标记，防止无限重试
    """
    headers = {"X-Metabase-Session": get_session(), "Content-Type": "application/json"}
    url = f"{_CONFIG['url']}{path}"
    try:
        resp = requests.request(
            method, url, headers=headers, json=json_body, params=params, timeout=60
        )
        # 401 表示 session 失效，自动重新登录并重试一次
        # 注意：403 是权限不足（如 premium 接口），不应触发重新登录
        if resp.status_code == 401 and not _retried:
            global _session
            _session = None  # 清空失效的 session
            _session = _login()
            return _request(method, path, json_body=json_body, params=params, _retried=True)
        resp.raise_for_status()
        return resp.json()
    except RequestException as e:
        raise RuntimeError(f"请求 {path} 失败: {e}") from e


def to_json(obj: Any) -> str:
    """将 Python 对象序列化为 JSON 字符串。"""
    return json.dumps(obj, ensure_ascii=False, default=str)


# ==================== 结果过滤函数 ====================


def _summarize_query_result(data: Dict) -> Dict:
    """精简查询结果：只保留列名与行数据；查询失败时提取错误信息供 AI 参考。"""
    status = data.get("status")

    # 查询失败时，提取 Metabase 返回的错误信息
    if status == "failed":
        # via 数组中最后一个元素的 error 通常是最清晰的错误描述
        via_list = data.get("via", [])
        error_msg = None
        error_class = None
        if via_list and isinstance(via_list, list):
            last_via = via_list[-1]
            error_msg = last_via.get("error")
            error_class = last_via.get("class")
        # 回退到顶层 error 字段
        if not error_msg:
            error_msg = data.get("error", "未知错误（Metabase 未提供 error 字段）")

        result = {
            "status": "failed",
            "error": error_msg,
            "error_type": data.get("error_type"),
        }
        if error_class:
            result["error_class"] = error_class
        return result

    # 正常查询结果
    inner = data.get("data", data)
    cols = inner.get("cols", [])
    col_names = [c.get("name") or c.get("display_name") for c in cols]
    return {
        "columns": col_names,
        "rows": inner.get("rows", []),
        "row_count": data.get("row_count", len(inner.get("rows", []))),
        "status": status,
    }


def _summarize_databases(data: Dict) -> List[Dict]:
    """精简数据库列表：只保留 id/name/engine。"""
    items = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(items, dict):
        items = items.get("data", [])
    return [
        {"id": d.get("id"), "name": d.get("name"), "engine": d.get("engine")}
        for d in items
    ]


def _summarize_database_detail(data: Dict) -> Dict:
    """精简数据库详情：只保留关键信息。"""
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "engine": data.get("engine"),
        "dbms_version": data.get("dbms_version", {}),
        "description": data.get("description"),
    }


def _summarize_metadata(data: Any) -> Dict:
    """精简数据库元数据：只保留表名与字段列表。"""
    tables = data.get("tables", []) if isinstance(data, dict) else []
    result = []
    for t in tables:
        fields = [
            {
                "name": f.get("name"),
                "base_type": f.get("base_type"),
                "database_type": f.get("database_type"),
                "semantic_type": f.get("semantic_type"),
                "pk": f.get("semantic_type") == "type/PK",
            }
            for f in t.get("fields", [])
        ]
        result.append({
            "id": t.get("id"),
            "name": t.get("name"),
            "schema": t.get("schema"),
            "fields": fields,
        })
    return {"tables": result, "table_count": len(result)}


def _summarize_fields(data: Any) -> List[Dict]:
    """精简字段列表。"""
    items = data if isinstance(data, list) else data.get("data", [])
    return [
        {
            "id": f.get("id"),
            "name": f.get("name"),
            "table_id": f.get("table_id"),
            "base_type": f.get("base_type"),
            "database_type": f.get("database_type"),
            "semantic_type": f.get("semantic_type"),
        }
        for f in items
    ]


def _summarize_cards(data: Any) -> List[Dict]:
    """精简已保存查询列表：只保留 id/name/database_id。"""
    items = data if isinstance(data, list) else data.get("data", [])
    return [
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "database_id": c.get("database_id"),
            "display": c.get("display"),
        }
        for c in items
    ]


# ==================== MCP 工具定义 ====================


@mcp.tool()
def list_databases(summarize: bool = True) -> str:
    """获取 Metabase 中所有可用的数据库（名称、ID、引擎类型）。

    参数:
        summarize: 为 True 时只返回关键信息（id/name/engine），False 返回完整响应
    """
    try:
        data = _request("GET", "/api/database/")
        if summarize:
            return to_json(_summarize_databases(data))
        return to_json(data)
    except Exception as e:
        return to_json({"error": str(e)})


@mcp.tool()
def get_database(database_id: int, summarize: bool = True) -> str:
    """获取单个数据库的详情（引擎、版本、描述等）。

    参数:
        database_id: 数据库 ID
        summarize: 为 True 时只返回关键信息，False 返回完整响应
    """
    try:
        data = _request("GET", f"/api/database/{database_id}")
        if summarize:
            return to_json(_summarize_database_detail(data))
        return to_json(data)
    except Exception as e:
        return to_json({"error": str(e)})


@mcp.tool()
def get_database_metadata(database_id: int, summarize: bool = True) -> str:
    """获取数据库的全部元数据（包含表名、字段名、字段类型）。

    参数:
        database_id: 数据库 ID
        summarize: 为 True 时只返回表名与字段精简信息，False 返回完整响应
    """
    try:
        data = _request("GET", f"/api/database/{database_id}/metadata")
        if summarize:
            return to_json(_summarize_metadata(data))
        return to_json(data)
    except Exception as e:
        return to_json({"error": str(e)})


@mcp.tool()
def get_table_metadata(database_id: int, table_name: str, summarize: bool = True) -> str:
    """获取数据库中指定表的元数据（字段名、字段类型、是否主键等）。

    相比 get_database_metadata 只返回单张表的信息，避免返回大量无关表数据。

    参数:
        database_id: 数据库 ID
        table_name: 表名称（精确匹配）
        summarize: 为 True 时只返回字段精简信息，False 返回完整响应
    """
    try:
        data = _request("GET", f"/api/database/{database_id}/metadata")
        tables = data.get("tables", []) if isinstance(data, dict) else []
        # 按表名精确匹配
        target = None
        for t in tables:
            if t.get("name") == table_name:
                target = t
                break
        if not target:
            available = [t.get("name") for t in tables]
            return to_json({"error": f"未找到表 '{table_name}'", "available_tables": available[:50]})
        if summarize:
            fields = [
                {
                    "name": f.get("name"),
                    "base_type": f.get("base_type"),
                    "database_type": f.get("database_type"),
                    "semantic_type": f.get("semantic_type"),
                    "pk": f.get("semantic_type") == "type/PK",
                }
                for f in target.get("fields", [])
            ]
            return to_json({
                "id": target.get("id"),
                "name": target.get("name"),
                "schema": target.get("schema"),
                "fields": fields,
                "field_count": len(fields),
            })
        return to_json(target)
    except Exception as e:
        return to_json({"error": str(e)})


@mcp.tool()
def get_database_fields(database_id: int, summarize: bool = True) -> str:
    """获取数据库的全部字段信息（跨表）。

    参数:
        database_id: 数据库 ID
        summarize: 为 True 时只返回字段精简信息，False 返回完整响应
    """
    try:
        data = _request("GET", f"/api/database/{database_id}/fields")
        if summarize:
            return to_json(_summarize_fields(data))
        return to_json(data)
    except Exception as e:
        return to_json({"error": str(e)})


@mcp.tool()
def list_cards(summarize: bool = True) -> str:
    """获取 Metabase 中所有已保存的查询（Card）。

    参数:
        summarize: 为 True 时只返回关键信息（id/name/database_id），False 返回完整响应
    """
    try:
        data = _request("GET", "/api/card")
        if summarize:
            return to_json(_summarize_cards(data))
        return to_json(data)
    except Exception as e:
        return to_json({"error": str(e)})


@mcp.tool()
def execute_card(card_id: int, summarize: bool = True) -> str:
    """执行一个已保存的查询（Card）并返回结果。

    参数:
        card_id: Card（已保存查询）的 ID
        summarize: 为 True 时只返回列名与行数据，False 返回完整响应
    """
    try:
        data = _request("POST", f"/api/card/{card_id}/query/json")
        if summarize:
            return to_json(_summarize_query_result(data))
        return to_json(data)
    except Exception as e:
        return to_json({"error": str(e)})


@mcp.tool()
def execute_query(
    database_id: int,
    query: str,
    collection: Optional[str] = None,
    summarize: bool = True,
    limit: int = DEFAULT_LIMIT,
) -> str:
    """执行原生查询（支持 SQL 与 MongoDB 聚合管道）。

    自动识别查询类型：
    - query 以 '[' 开头且能解析为 JSON 数组 -> MongoDB 聚合管道（需提供 collection）
    - 否则 -> SQL 查询（如 SELECT ...）

    参数:
        database_id: 目标数据库 ID（可通过 list_databases 获取）
        query: 查询语句。SQL 为字符串；Mongo 为聚合管道 JSON 字符串，
               如 [{"$match": {"uni_code": "abc"}}]
        collection: MongoDB 集合名称（仅 Mongo 管道查询需要，SQL 查询忽略此参数）。
                    可通过 get_database_metadata 获取可用集合列表。
        summarize: 为 True 时只返回列名与行数据，False 返回完整响应
        limit: 返回行数上限（默认 100），仅对 SQL 有效（Mongo 管道请在 $limit 阶段控制）
    """
    try:
        # 判断是否为 MongoDB 聚合管道
        query_body = query
        is_mongo = False
        stripped = query.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    is_mongo = True
                    query_body = stripped  # 原样传入
            except json.JSONDecodeError:
                pass  # 不是合法 JSON，按 SQL 处理

        # Mongo 管道查询必须指定 collection
        if is_mongo and not collection:
            return to_json({
                "error": "MongoDB 聚合管道查询必须提供 collection 参数，"
                         "可通过 get_database_metadata 获取可用集合列表"
            })

        # 对 SQL 追加 LIMIT（若用户未指定且未包含 limit）
        if not is_mongo and "limit" not in stripped.lower():
            query_body = stripped.rstrip(";") + f" LIMIT {int(limit)}"

        native_body: Dict[str, Any] = {"query": query_body}
        if is_mongo:
            native_body["collection"] = collection

        payload = {
            "database": database_id,
            "native": native_body,
            "type": "native",
        }
        data = _request("POST", "/api/dataset", json_body=payload)
        # 查询失败时，无论 summarize 与否都提取错误信息（避免返回巨量 stacktrace）
        if data.get("status") == "failed":
            return to_json(_summarize_query_result(data))
        if summarize:
            return to_json(_summarize_query_result(data))
        return to_json(data)
    except Exception as e:
        return to_json({"error": str(e)})


@mcp.tool()
def server_status() -> str:
    """获取 Metabase 服务器状态（可用于连通性测试，返回当前用户与数据库总数）。"""
    try:
        # 用 /api/user/current 获取当前用户信息，作为连通性验证
        data = _request("GET", "/api/user/current")
        # 同时获取数据库总数
        dbs = _request("GET", "/api/database/")
        return to_json({
            "current_user": data.get("common_name") or data.get("email"),
            "user_id": data.get("id"),
            "is_superuser": data.get("is_superuser"),
            "database_count": dbs.get("total"),
            "metabase_url": _CONFIG["url"],
        })
    except Exception as e:
        return to_json({"error": str(e)})


@mcp.tool()
def describe_table(database_id: int, table_name: str, table_schema: str) -> str:
    """查询表的字段结构及注释（仅支持 MySQL/MariaDB/Doris 等关系型数据库）。

    通过查询 INFORMATION_SCHEMA.COLUMNS 获取指定表的字段名、字段类型和字段注释，
    供 AI 了解表结构后编写正确的 SQL。

    参数:
        database_id: Metabase 中的数据库 ID（可通过 list_databases 获取）
        table_name: 表名称（精确匹配，如 'listing_sku'）
        table_schema: 数据库名称/Schema 名称（如 'data_center'）
    """
    try:
        sql = (
            "SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_COMMENT "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            f"WHERE TABLE_NAME = '{table_name}' "
            f"AND TABLE_SCHEMA = '{table_schema}'"
        )
        payload = {
            "database": database_id,
            "native": {"query": sql},
            "type": "native",
        }
        data = _request("POST", "/api/dataset", json_body=payload)

        # 查询失败时提取错误信息
        if data.get("status") == "failed":
            return to_json(_summarize_query_result(data))

        inner = data.get("data", data)
        rows = inner.get("rows", [])
        # 整理为字段列表，方便 AI 阅读
        fields = []
        for row in rows:
            fields.append({
                "column_name": row[0] if len(row) > 0 else None,
                "column_type": row[1] if len(row) > 1 else None,
                "column_comment": row[2] if len(row) > 2 else None,
            })
        return to_json({
            "table_name": table_name,
            "table_schema": table_schema,
            "fields": fields,
            "field_count": len(fields),
        })
    except Exception as e:
        return to_json({"error": str(e)})


if __name__ == "__main__":
    mcp.run()
