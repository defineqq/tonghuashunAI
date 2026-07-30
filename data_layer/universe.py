"""
股票池：成分股 + 过滤规则
========================

用途：从"全 A 五千多只"缩小到"策略实际盯的候选池"。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from data_layer.cache import cached


@cached("universe", max_age_hours=24)
def hs300_constituents() -> pd.DataFrame:
    """沪深 300 成分股。columns: 代码, 名称, 纳入日期, 权重（如可用）。"""
    import akshare as ak
    return ak.index_stock_cons_csindex(symbol="000300")


@cached("universe", max_age_hours=24)
def csi500_constituents() -> pd.DataFrame:
    """中证 500 成分股。"""
    import akshare as ak
    return ak.index_stock_cons_csindex(symbol="000905")


@cached("universe", max_age_hours=24)
def csi1000_constituents() -> pd.DataFrame:
    """中证 1000 成分股。"""
    import akshare as ak
    return ak.index_stock_cons_csindex(symbol="000852")


_INDEX_FN = {
    "000300": hs300_constituents,
    "000905": csi500_constituents,
    "000852": csi1000_constituents,
}


def load_pool(config_path: str | Path = "configs/stock_pool.yaml") -> list[str]:
    """
    根据 configs/stock_pool.yaml 加载股票池。

    返回 6 位股票代码列表（不含 sh/sz 前缀）。
    """
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if cfg["use"] == "custom":
        return [str(s).zfill(6) for s in (cfg.get("custom") or [])]

    idx = cfg.get("index", "000300")
    if idx not in _INDEX_FN:
        raise ValueError(f"unsupported index: {idx}")
    df = _INDEX_FN[idx]()
    # AkShare 返回列名可能是 '成分券代码' 或 '代码'
    col = next((c for c in df.columns if "代码" in c and "指数" not in c), None)
    if col is None:
        raise RuntimeError(f"未在成分股 DataFrame 中找到代码列，列: {list(df.columns)}")
    return [str(x).zfill(6) for x in df[col].tolist()]
