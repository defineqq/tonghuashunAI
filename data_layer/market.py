"""
市场行情数据
============

统一接口签名 (symbol, start, end)，返回标准化的 pandas DataFrame。

标准列（不同函数可能是子集）：
    date | open | high | low | close | volume | amount | pct_change
"""

from __future__ import annotations

import pandas as pd

from data_layer.cache import cached


_A_HIST_RENAME = {
    "日期": "date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
    "成交额": "amount",
    "涨跌幅": "pct_change",
    "换手率": "turnover_rate",
}


@cached("market", max_age_hours=None)  # 历史日线，永久缓存
def daily(
    symbol: str,
    start: str = "2020-01-01",
    end: str = "2099-12-31",
    adjust: str = "qfq",
) -> pd.DataFrame:
    """
    A 股日线（前复权）。

    Args:
        symbol: 6 位代码，如 "600519"（茅台）、"000858"（五粮液）
        start: "YYYY-MM-DD"
        end:   "YYYY-MM-DD"
        adjust: "qfq"=前复权 / "hfq"=后复权 / ""=不复权

    Returns:
        DataFrame with columns: date, open, high, low, close, volume, amount, pct_change, turnover_rate
        index=RangeIndex, date 是 datetime64[ns] 类型
    """
    import akshare as ak
    raw = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
        adjust=adjust,
    )
    df = raw.rename(columns=_A_HIST_RENAME)
    df["date"] = pd.to_datetime(df["date"])
    keep = [c for c in ["date", "open", "high", "low", "close", "volume", "amount", "pct_change", "turnover_rate"] if c in df.columns]
    return df[keep].sort_values("date").reset_index(drop=True)


@cached("market", max_age_hours=None)
def minute(
    symbol: str,
    start: str,
    end: str,
    period: str = "60",
    adjust: str = "qfq",
) -> pd.DataFrame:
    """
    A 股分钟线。period 可选："1" "5" "15" "30" "60"（分钟）。

    注意：AkShare 分钟线数据 <= 5 年，早期数据可能没有。
    """
    import akshare as ak
    raw = ak.stock_zh_a_hist_min_em(
        symbol=symbol,
        start_date=f"{start} 09:30:00",
        end_date=f"{end} 15:00:00",
        period=period,
        adjust=adjust,
    )
    df = raw.rename(columns={"时间": "datetime", **_A_HIST_RENAME})
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df.sort_values("datetime").reset_index(drop=True)


@cached("market", max_age_hours=0.1)  # 6 分钟缓存，避免频繁请求
def snapshot() -> pd.DataFrame:
    """全 A 实时快照（收盘价、涨跌幅、成交量、市值等）。"""
    import akshare as ak
    return ak.stock_zh_a_spot_em()
