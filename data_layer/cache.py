"""
本地缓存：pandas DataFrame → parquet 文件
=======================================

设计原则：
- key = (数据源函数名, 参数指纹)，参数指纹用 md5(sorted kwargs) 生成
- 存储位置：${DATA_DIR}/{namespace}/{key}.parquet，默认 ./data
- 时效控制：max_age_hours 内视为有效，过期或不存在则回源
- "历史数据"（例如 2020-01-01 到 2023-12-31 的行情）→ 永久缓存
- "近期数据"（例如今天的实时快照、龙虎榜）→ 短时缓存或不缓存
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Callable

import pandas as pd


def _data_dir() -> Path:
    """缓存根目录，可通过 DATA_DIR 环境变量覆盖。"""
    return Path(os.environ.get("DATA_DIR", "./data")).resolve()


def _fingerprint(**kwargs) -> str:
    """把关键字参数序列化后取 md5，用作缓存文件名。"""
    payload = json.dumps(kwargs, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:16]


def _cache_path(namespace: str, name: str, fp: str) -> Path:
    return _data_dir() / namespace / f"{name}__{fp}.parquet"


def _is_fresh(path: Path, max_age_hours: float | None) -> bool:
    if not path.exists():
        return False
    if max_age_hours is None:  # 永久缓存
        return True
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return datetime.now() - mtime < timedelta(hours=max_age_hours)


def cached(
    namespace: str,
    max_age_hours: float | None = None,
) -> Callable:
    """
    装饰器：把返回 DataFrame 的函数结果缓存到 parquet 文件。

    参数：
        namespace: 一级目录，通常按数据类型分组，如 "market" "fundamental"
        max_age_hours: 缓存有效期。None = 永久（适合历史数据）；
                       小时数 = 过期后回源（适合当天数据）

    用法：
        @cached("market", max_age_hours=None)
        def daily(symbol, start, end):
            return ak.stock_zh_a_hist(...)
    """
    def deco(fn: Callable[..., pd.DataFrame]) -> Callable[..., pd.DataFrame]:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> pd.DataFrame:
            # 把 positional 也纳入指纹
            bound = {"__args__": list(args), **kwargs}
            fp = _fingerprint(**bound)
            path = _cache_path(namespace, fn.__name__, fp)

            if _is_fresh(path, max_age_hours):
                return pd.read_parquet(path)

            df = fn(*args, **kwargs)
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path)
            return df

        wrapper.__wrapped_uncached__ = fn  # type: ignore[attr-defined]
        return wrapper

    return deco


def clear_cache(namespace: str | None = None) -> int:
    """清缓存。指定 namespace 只清该目录；不指定则清全部。返回删除文件数。"""
    root = _data_dir() if namespace is None else _data_dir() / namespace
    if not root.exists():
        return 0
    n = 0
    for p in root.rglob("*.parquet"):
        p.unlink()
        n += 1
    return n
