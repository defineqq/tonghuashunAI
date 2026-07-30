"""
基本面数据
==========

估值、财务、行业。都从 AkShare 拉取。
"""

from __future__ import annotations

import pandas as pd

from data_layer.cache import cached


@cached("fundamental", max_age_hours=12)  # 估值日更即可，12h 缓存
def valuation(symbol: str) -> pd.DataFrame:
    """
    个股估值指标（PE/PB/PS/股息率），历史序列。

    Returns:
        columns: trade_date, pe, pb, ps, dv_ratio, total_mv (亿元)
    """
    import akshare as ak
    df = ak.stock_a_indicator_lg(symbol=symbol)
    # AkShare 列名会随版本变，做兼容
    rename = {
        "trade_date": "trade_date",
        "pe": "pe",
        "pb": "pb",
        "ps": "ps",
        "dv_ratio": "dv_ratio",
        "total_mv": "total_mv",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


@cached("fundamental", max_age_hours=None)  # 财报是历史数据，永久缓存
def financial_abstract(symbol: str) -> pd.DataFrame:
    """
    财务摘要（营收、净利润、ROE 等主要指标的时间序列）。

    Args:
        symbol: 6 位代码
    """
    import akshare as ak
    return ak.stock_financial_abstract(symbol=symbol)


@cached("fundamental", max_age_hours=24)
def industry_of(symbol: str) -> dict[str, str]:
    """
    获取个股所属申万行业。

    Returns:
        {"industry_l1": "...", "industry_l2": "...", "industry_l3": "..."}
    """
    import akshare as ak
    df = ak.stock_individual_info_em(symbol=symbol)
    kv = dict(zip(df["item"], df["value"]))
    return {
        "industry_l1": kv.get("行业", ""),
        "total_share": kv.get("总股本", ""),
        "float_share": kv.get("流通股", ""),
        "total_mv": kv.get("总市值", ""),
        "float_mv": kv.get("流通市值", ""),
    }
