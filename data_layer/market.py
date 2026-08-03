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


def _minute_eastmoney(symbol: str, start: str, end: str, period: str, adjust: str) -> pd.DataFrame:
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
    keep = [c for c in ["datetime", "open", "high", "low", "close", "volume", "amount", "pct_change"] if c in df.columns]
    return df[keep].sort_values("datetime").reset_index(drop=True)


def _minute_sina(symbol: str, start: str, end: str, period: str, adjust: str) -> pd.DataFrame:
    """新浪只提供近段分钟数据，作为兜底源。"""
    import akshare as ak
    raw = ak.stock_zh_a_minute(symbol=_sina_symbol(symbol), period=period, adjust=adjust or "")
    df = raw.rename(columns={"day": "datetime"})
    df["datetime"] = pd.to_datetime(df["datetime"])
    # 过滤到 [start, end]
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end) + pd.Timedelta(days=1)
    df = df[(df["datetime"] >= start_dt) & (df["datetime"] < end_dt)].copy()
    # 新浪数值列都是 str，强转
    for c in ("open", "high", "low", "close", "volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    keep = [c for c in ["datetime", "open", "high", "low", "close", "volume"] if c in df.columns]
    return df[keep].sort_values("datetime").reset_index(drop=True)


_minute_last_source: str | None = None


def minute_last_source() -> str | None:
    """返回上次 minute() 成功用的数据源标签。"""
    return _minute_last_source


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

    多源回退：东财 → 新浪。任何一路成功就返回。
    """
    global _minute_last_source
    errors = []
    for name, fn in [("eastmoney", _minute_eastmoney), ("sina", _minute_sina)]:
        try:
            df = fn(symbol, start, end, period, adjust)
            if df is not None and not df.empty:
                _minute_last_source = name
                return df
            errors.append(f"{name}: empty")
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:60]}")
    _minute_last_source = None
    raise RuntimeError(f"所有分钟线源都失败 [{symbol}]: {'; '.join(errors)}")


# 记录快照最近一次实际用了哪个源，供健康检查/前端展示
_snapshot_last_source: str | None = None


def snapshot_last_source() -> str | None:
    """返回上次 snapshot() 成功用的数据源标签。可能是 None（尚未调用或全部失败）。"""
    return _snapshot_last_source


@cached("market", max_age_hours=0.1)  # 6 分钟缓存
def snapshot() -> pd.DataFrame:
    """
    全 A 实时快照（收盘价、涨跌幅、成交量、市值等）。

    多源回退顺序：
      1. eastmoney 一把拉全 A（最全，含总市值）
      2. sina 一把拉全 A（列名不同，做映射）
      3. 分交易所 eastmoney（sh + sz + kc + cy + bj）拼接
    每个源尝试到 empty/异常都算失败，进入下一个。全失败才抛 RuntimeError。
    """
    global _snapshot_last_source
    import akshare as ak
    errors = []

    # 1) 东财一把拉
    try:
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            _snapshot_last_source = "eastmoney"
            return df
        errors.append("eastmoney: empty")
    except Exception as e:
        errors.append(f"eastmoney: {type(e).__name__}: {str(e)[:60]}")

    # 2) 新浪一把拉（列名不同，需要映射到东财风格）
    try:
        df = ak.stock_zh_a_spot()
        if df is not None and not df.empty:
            # 新浪列：代码/symbol、名称/name、trade/最新价、marketcapital/总市值...
            rename_map = {
                "symbol": "代码", "code": "代码",
                "name": "名称",
                "trade": "最新价",
                "changepercent": "涨跌幅",
                "volume": "成交量",
                "amount": "成交额",
                "turnoverratio": "换手率",
                "pe": "市盈率-动态",
                "pb": "市净率",
                "mktcap": "总市值",
                "nmc": "流通市值",
            }
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
            # 新浪 symbol 是 sh600519，剥出 6 位
            if "代码" in df.columns:
                df["代码"] = df["代码"].astype(str).str.extract(r"(\d{6})", expand=False).fillna(df["代码"])
            _snapshot_last_source = "sina"
            return df
        errors.append("sina: empty")
    except Exception as e:
        errors.append(f"sina: {type(e).__name__}: {str(e)[:60]}")

    # 3) 分交易所拼接
    try:
        parts = []
        for name, fn in [
            ("sh", ak.stock_sh_a_spot_em),
            ("sz", ak.stock_sz_a_spot_em),
            ("kc", ak.stock_kc_a_spot_em),
            ("cy", ak.stock_cy_a_spot_em),
            ("bj", ak.stock_bj_a_spot_em),
        ]:
            try:
                sub = fn()
                if sub is not None and not sub.empty:
                    parts.append(sub)
            except Exception as e:
                errors.append(f"per_exchange:{name}: {type(e).__name__}")
        if parts:
            df = pd.concat(parts, ignore_index=True, sort=False)
            _snapshot_last_source = f"per_exchange({len(parts)}/5)"
            return df
        errors.append("per_exchange: all empty")
    except Exception as e:
        errors.append(f"per_exchange: {type(e).__name__}: {str(e)[:60]}")

    _snapshot_last_source = None
    raise RuntimeError(f"所有全 A 快照源都失败: {'; '.join(errors)}")
