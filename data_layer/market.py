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


def _sina_symbol(symbol: str) -> str:
    """把 6 位代码转成新浪的 shXXXXXX/szXXXXXX 格式。"""
    if symbol.startswith(("6", "9")):
        return "sh" + symbol
    return "sz" + symbol


def _try_eastmoney(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    import akshare as ak
    raw = ak.stock_zh_a_hist(
        symbol=symbol, period="daily",
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
        adjust=adjust,
    )
    df = raw.rename(columns=_A_HIST_RENAME)
    df["date"] = pd.to_datetime(df["date"])
    keep = [c for c in ["date", "open", "high", "low", "close", "volume", "amount", "pct_change", "turnover_rate"] if c in df.columns]
    return df[keep].sort_values("date").reset_index(drop=True)


def _try_sina(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    import akshare as ak
    raw = ak.stock_zh_a_daily(
        symbol=_sina_symbol(symbol),
        adjust=adjust or "",
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
    )
    # 新浪返回列：date, open, high, low, close, volume, amount, outstanding_share, turnover
    df = raw.copy()
    df["date"] = pd.to_datetime(df["date"])
    # 补齐可能缺失的列
    if "pct_change" not in df.columns:
        df["pct_change"] = df["close"].pct_change() * 100
    if "turnover_rate" not in df.columns and "turnover" in df.columns:
        df["turnover_rate"] = df["turnover"] * 100  # 新浪 turnover 是比例 → 百分比
    keep = [c for c in ["date", "open", "high", "low", "close", "volume", "amount", "pct_change", "turnover_rate"] if c in df.columns]
    return df[keep].sort_values("date").reset_index(drop=True)


def _try_tencent(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    import akshare as ak
    raw = ak.stock_zh_a_hist_tx(
        symbol=_sina_symbol(symbol),
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
        adjust=adjust or "qfq",
    )
    df = raw.copy()
    df["date"] = pd.to_datetime(df["date"])
    if "pct_change" not in df.columns:
        df["pct_change"] = df["close"].pct_change() * 100
    if "turnover_rate" not in df.columns and "turnover" in df.columns:
        df["turnover_rate"] = df["turnover"] * 100
    keep = [c for c in ["date", "open", "high", "low", "close", "volume", "amount", "pct_change", "turnover_rate"] if c in df.columns]
    return df[keep].sort_values("date").reset_index(drop=True)


@cached("market", max_age_hours=None)  # 历史日线，永久缓存
def daily(
    symbol: str,
    start: str = "2020-01-01",
    end: str = "2099-12-31",
    adjust: str = "qfq",
) -> pd.DataFrame:
    """
    A 股日线（前复权）。

    多源自动回退：东方财富（首选，速度快数据全）→ 新浪 → 腾讯。
    某些内网环境东财接口可能被封，新浪/腾讯是应急备份。

    Args:
        symbol: 6 位代码，如 "600519"（茅台）
        start: "YYYY-MM-DD"
        end:   "YYYY-MM-DD"
        adjust: "qfq"=前复权 / "hfq"=后复权 / ""=不复权

    Returns:
        DataFrame with columns: date, open, high, low, close, volume, amount, pct_change, turnover_rate
    """
    errors = []
    for source_name, fn in [
        ("eastmoney", _try_eastmoney),
        ("sina", _try_sina),
        ("tencent", _try_tencent),
    ]:
        try:
            df = fn(symbol, start, end, adjust)
            if not df.empty:
                return df
        except Exception as e:
            errors.append(f"{source_name}: {type(e).__name__}")
            continue
    raise RuntimeError(f"所有日线数据源都失败 [{symbol}]: {'; '.join(errors)}")


@cached("market", max_age_hours=None)
def minute(
    symbol: str,
    start: str,
    end: str,
    period: str = "60",
    adjust: str = "qfq",
) -> pd.DataFrame:
    """A 股分钟线。period 可选："1" "5" "15" "30" "60"（分钟）。"""
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


@cached("market", max_age_hours=0.1)  # 6 分钟缓存
def snapshot() -> pd.DataFrame:
    """全 A 实时快照（收盘价、涨跌幅、成交量、市值等）。"""
    import akshare as ak
    return ak.stock_zh_a_spot_em()
