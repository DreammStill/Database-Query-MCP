#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MongoDB MCP 服务器（兼容低版本 MongoDB 3.2 / wire version 4 及高版本）。

基于 pymongo 3.13.0 编写，使用 stdio 传输与 MCP 客户端通信。
配置读取顺序：环境变量优先 -> 同目录 mongo_mcp_config.json 回退。

环境变量说明：
    MONGO_HOST          主机地址（默认 127.0.0.1）
    MONGO_PORT          端口（默认 27017）
    MONGO_USER          用户名（启用认证时必填）
    MONGO_PASSWORD      密码（启用认证时必填）
    MONGO_AUTH_SOURCE   认证库（默认 admin）
    MONGO_AUTH_MECHANISM 认证机制（默认 SCRAM-SHA-1，兼容老版本）
    MONGO_DB            默认数据库
    MONGO_REPLICA_SET   副本集名称（可选）
"""

import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pymongo import MongoClient
from pymongo.errors import PyMongoError
from bson import json_util
from bson.objectid import ObjectId

from mcp.server.fastmcp import FastMCP


# 创建 MCP 服务器实例
mcp = FastMCP("mongo-legacy-mcp")

# 配置文件路径（与脚本/exe 同目录，仅当环境变量缺失时回退使用）
# PyInstaller 打包后 __file__ 指向临时解压目录，需用 sys.executable 定位 exe 所在路径
if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).resolve().parent
else:
    _BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = _BASE_DIR / "mongo_mcp_config.json"

# 默认查询返回上限，防止内存溢出
DEFAULT_LIMIT = 100


def load_config() -> Dict[str, Any]:
    """加载连接配置：环境变量优先，缺失时回退到同目录配置文件。"""
    env_keys = {
        "host": "MONGO_HOST",
        "port": "MONGO_PORT",
        "username": "MONGO_USER",
        "password": "MONGO_PASSWORD",
        "authSource": "MONGO_AUTH_SOURCE",
        "authMechanism": "MONGO_AUTH_MECHANISM",
        "database": "MONGO_DB",
        "replicaSet": "MONGO_REPLICA_SET",
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
    config.setdefault("port", "27017")
    config.setdefault("authSource", "admin")
    return config


_CONFIG = load_config()

# MongoDB 客户端单例
_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    """获取 MongoDB 客户端单例，按配置自动启用/禁用认证。"""
    global _client
    if _client is None:
        kwargs: Dict[str, Any] = {
            "host": _CONFIG["host"],
            "port": int(_CONFIG["port"]),
            "serverSelectionTimeoutMS": 10000,
        }
        # 仅在提供了用户名时启用认证
        if _CONFIG.get("username"):
            kwargs["username"] = _CONFIG["username"]
            kwargs["password"] = _CONFIG.get("password", "")
            kwargs["authSource"] = _CONFIG.get("authSource", "admin")
            if _CONFIG.get("authMechanism"):
                kwargs["authMechanism"] = _CONFIG["authMechanism"]
        if _CONFIG.get("replicaSet"):
            kwargs["replicaSet"] = _CONFIG["replicaSet"]
        _client = MongoClient(**kwargs)
    return _client


def get_db(db_name: Optional[str] = None):
    """获取数据库对象，未指定时使用配置中的默认数据库。"""
    name = db_name or _CONFIG.get("database")
    if not name:
        raise ValueError("未指定数据库名称，请通过参数 db 或环境变量 MONGO_DB 指定")
    return get_client()[name]


def to_json(obj: Any) -> str:
    """将 BSON 对象序列化为 JSON 字符串，保留 ObjectId 等扩展类型。"""
    return json_util.dumps(obj, ensure_ascii=False)


def _convert_id(id_val: Any) -> Any:
    """转换 _id 值：24 位 hex 字符串转 ObjectId，$in 列表逐项转换。"""
    if isinstance(id_val, str) and len(id_val) == 24:
        try:
            return ObjectId(id_val)
        except Exception:
            return id_val
    if isinstance(id_val, dict) and "$in" in id_val:
        id_val["$in"] = [_convert_id(x) for x in id_val["$in"]]
    return id_val


def normalize_filter(flt: Optional[Dict]) -> Dict:
    """规范化查询条件，自动将 _id 的 hex 字符串转为 ObjectId。"""
    if not flt:
        return {}
    flt = dict(flt)  # 避免修改入参
    if "_id" in flt:
        flt["_id"] = _convert_id(flt["_id"])
    return flt


# ==================== MCP 工具定义 ====================


@mcp.tool()
def list_databases() -> str:
    """列出 MongoDB 中所有数据库的名称。"""
    try:
        result = get_client().list_database_names()
        return to_json({"databases": result})
    except PyMongoError as e:
        return to_json({"error": str(e)})


@mcp.tool()
def list_collections(db: str) -> str:
    """列出指定数据库中的所有集合名称。

    参数:
        db: 数据库名称
    """
    try:
        result = get_db(db).list_collection_names()
        return to_json({"collections": result})
    except PyMongoError as e:
        return to_json({"error": str(e)})


@mcp.tool()
def find(
    db: str,
    collection: str,
    filter: Optional[Dict] = None,
    projection: Optional[Dict] = None,
    sort: Optional[List] = None,
    limit: int = DEFAULT_LIMIT,
    skip: int = 0,
) -> str:
    """查询集合中的文档。

    参数:
        db: 数据库名称
        collection: 集合名称
        filter: 查询条件（MongoDB 查询表达式），_id 为 24 位字符串时自动转换
        projection: 字段投影，如 {"name": 1, "_id": 0}
        sort: 排序规则，如 [["age", -1], ["name", 1]]
        limit: 返回文档上限，默认 100
        skip: 跳过的文档数
    """
    try:
        cursor = get_db(db)[collection].find(normalize_filter(filter), projection)
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        cursor = cursor.limit(limit)
        return to_json(list(cursor))
    except PyMongoError as e:
        return to_json({"error": str(e)})


@mcp.tool()
def aggregate(db: str, collection: str, pipeline: List[Dict]) -> str:
    """对集合执行聚合管道操作。

    参数:
        db: 数据库名称
        collection: 集合名称
        pipeline: 聚合管道阶段列表，如 [{"$match": {...}}, {"$group": {...}}]
    """
    try:
        result = list(get_db(db)[collection].aggregate(pipeline))
        return to_json(result)
    except PyMongoError as e:
        return to_json({"error": str(e)})


@mcp.tool()
def count(db: str, collection: str, filter: Optional[Dict] = None) -> str:
    """统计集合中匹配条件的文档数量。

    参数:
        db: 数据库名称
        collection: 集合名称
        filter: 查询条件，_id 为 24 位字符串时自动转换
    """
    try:
        n = get_db(db)[collection].count_documents(normalize_filter(filter))
        return to_json({"count": n})
    except PyMongoError as e:
        return to_json({"error": str(e)})


@mcp.tool()
def insert(db: str, collection: str, documents: Union[Dict, List[Dict]]) -> str:
    """向集合中插入文档，支持单条或多条。

    参数:
        db: 数据库名称
        collection: 集合名称
        documents: 单个文档对象或文档列表
    """
    try:
        col = get_db(db)[collection]
        if isinstance(documents, list):
            result = col.insert_many(documents)
            return to_json({
                "inserted_ids": [str(i) for i in result.inserted_ids],
                "inserted_count": len(result.inserted_ids),
            })
        else:
            result = col.insert_one(documents)
            return to_json({"inserted_id": str(result.inserted_id)})
    except PyMongoError as e:
        return to_json({"error": str(e)})


@mcp.tool()
def update(
    db: str,
    collection: str,
    filter: Dict,
    update: Dict,
    multi: bool = False,
    upsert: bool = False,
) -> str:
    """更新集合中的文档。

    参数:
        db: 数据库名称
        collection: 集合名称
        filter: 查询条件，_id 为 24 位字符串时自动转换
        update: 更新表达式，如 {"$set": {"name": "x"}}
        multi: 为 True 时更新所有匹配文档，否则只更新第一条
        upsert: 为 True 时，无匹配则插入
    """
    try:
        col = get_db(db)[collection]
        flt = normalize_filter(filter)
        if multi:
            result = col.update_many(flt, update, upsert=upsert)
        else:
            result = col.update_one(flt, update, upsert=upsert)
        return to_json({
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
            "upserted_id": str(result.upserted_id) if result.upserted_id else None,
        })
    except PyMongoError as e:
        return to_json({"error": str(e)})


@mcp.tool()
def delete(db: str, collection: str, filter: Dict, multi: bool = False) -> str:
    """删除集合中的文档。

    参数:
        db: 数据库名称
        collection: 集合名称
        filter: 查询条件，_id 为 24 位字符串时自动转换
        multi: 为 True 时删除所有匹配文档，否则只删除第一条
    """
    try:
        col = get_db(db)[collection]
        flt = normalize_filter(filter)
        if multi:
            result = col.delete_many(flt)
        else:
            result = col.delete_one(flt)
        return to_json({"deleted_count": result.deleted_count})
    except PyMongoError as e:
        return to_json({"error": str(e)})


@mcp.tool()
def server_info() -> str:
    """获取 MongoDB 服务器信息（版本、wire 版本等），可用于连通性测试。"""
    try:
        info = get_client().server_info()
        return to_json({
            "version": info.get("version"),
            "wireVersion": info.get("wireVersion"),
            "maxWireVersion": info.get("maxWireVersion"),
            "host": _CONFIG["host"],
            "port": _CONFIG["port"],
        })
    except PyMongoError as e:
        return to_json({"error": str(e)})


if __name__ == "__main__":
    mcp.run()
