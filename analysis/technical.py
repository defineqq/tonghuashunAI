"""
技术面评分
==========

综合以下子项，加权得到 0-100 分：
    - 趋势：5/20/60 日均线多头排列
    - 动量：近 20 日涨幅相对全市场分位
    - 强弱：RSI(14) 处于健康区间（40-70）
    - 量能：近 5 日均量 / 近 20 日均量 > 1.0（放量）
    - 波动率：ATR / 收盘价 处于中位（不太死也不太疯）

设计原则：不做绝对判定，都做**相对分位**打分，避免因子失效。
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from data_layer import market


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat(
        [(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def _sub_scores(df: pd.DataFrame) -> dict[str, float]:
    """针对单只股票的日线数据，输出 5 个子项分数（0-100）。"""
    if len(df) < 60:
        return {"trend": 50, "momentum": 50, "rsi": 50, "volume": 50, "volatility": 50}

    close = df["close"]
    volume = df["volume"]

    ma5 = _sma(close, 5).iloc[-1]
    ma20 = _sma(close, 20).iloc[-1]
    ma60 = _sma(close, 60).iloc[-1]
    price = close.iloc[-1]

    # 1. 趋势：多头排列（价 > ma5 > ma20 > ma60）满分 100，全反向 0
    trend_flags = [price > ma5, ma5 > ma20, ma20 > ma60]
    trend = 20 + 80 * (sum(trend_flags) / 3)

    # 2. 动量：近 20 日累计涨幅，映射到 0-100
    ret_20 = close.pct_change(20).iloc[-1]
    momentum = float(np.clip(50 + ret_20 * 200, 0, 100))  # +25% → 100, -25% → 0

    # 3. RSI：40-70 是理想区间
    rsi = _rsi(close, 14).iloc[-1]
    if 40 <= rsi <= 70:
        rsi_score = 100 - abs(rsi - 55) * 2  # 55 附近最高
    else:
        rsi_score = max(0, 100 - abs(rsi - 55) * 3)

    # 4. 量能：近 5 日均量 / 近 20 日均量
    vol_ratio = volume.tail(5).mean() / (volume.tail(20).mean() + 1e-9)
    volume_score = float(np.clip(50 + (vol_ratio - 1) * 100, 0, 100))

    # 5. 波动率：ATR / close 应在合理区间（1%-5%）
    atr = _atr(df, 14).iloc[-1]
    atr_pct = atr / price
    if 0.01 <= atr_pct <= 0.05:
        vol_std_score = 100 - abs(atr_pct - 0.025) * 2000
    else:
        vol_std_score = max(0, 100 - abs(atr_pct - 0.025) * 3000)

    return {
        "trend": round(trend, 1),
        "momentum": round(momentum, 1),
        "rsi": round(rsi_score, 1),
        "volume": round(volume_score, 1),
        "volatility": round(vol_std_score, 1),
    }


def score(
    symbol: str,
    as_of: str | None = None,
    lookback_days: int = 250,
    with_detail: bool = False,
) -> float | dict:
    """
    技术面综合评分（0-100）。

    Args:
        symbol: 6 位代码
        as_of:  截止日期 YYYY-MM-DD，默认今天
        lookback_days: 回看天数（够计算 60 日均线即可）
        with_detail: 返回子项明细
    """
    as_of = as_of or datetime.now().strftime("%Y-%m-%d")
    start = (datetime.strptime(as_of, "%Y-%m-%d") - pd.Timedelta(days=lookback_days * 2)).strftime("%Y-%m-%d")
    df = market.daily(symbol, start=start, end=as_of)
    if df.empty:
        return {"total": 0.0, "sub": {}} if with_detail else 0.0

    subs = _sub_scores(df)
    # 等权平均
    total = round(sum(subs.values()) / len(subs), 2)
    if with_detail:
        return {"total": total, "sub": subs}
    return total
