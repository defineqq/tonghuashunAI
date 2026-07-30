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
    """
    针对单只股票的日线数据，输出 5 个子项分数（0-100）。

    分档标定的目标：让实际数据分布尽可能撑满 0-100 区间，避免大家都在 40-60 附近扎堆。
    每个子项都设计成：中性档 50，明显好 70+，非常好 85+，理想状态 95+。
    """
    if len(df) < 60:
        return {"trend": 50, "momentum": 50, "rsi": 50, "volume": 50, "volatility": 50}

    close = df["close"]
    volume = df["volume"]

    ma5 = _sma(close, 5).iloc[-1]
    ma20 = _sma(close, 20).iloc[-1]
    ma60 = _sma(close, 60).iloc[-1]
    price = close.iloc[-1]

    # 1) 趋势：多头排列 (价>ma5>ma20>ma60) 100；三条件满足 2 个 75；1 个 50；0 个 25
    trend_flags = [price > ma5, ma5 > ma20, ma20 > ma60]
    trend = {0: 25, 1: 50, 2: 75, 3: 100}[sum(trend_flags)]

    # 2) 动量：近 20 日涨幅
    # 映射：-15% → 20，-5% → 40，0% → 55，+5% → 70，+15% → 90，+25% → 100
    ret_20 = float(close.pct_change(20).iloc[-1])
    momentum = float(np.clip(55 + ret_20 * 300, 10, 100))

    # 3) RSI(14)：健康区间 40-65
    rsi = _rsi(close, 14).iloc[-1]
    if 45 <= rsi <= 65:
        rsi_score = 85 + (65 - abs(rsi - 55)) * 0.75  # 55 附近 100，边缘 85
    elif 35 <= rsi < 45 or 65 < rsi <= 75:
        rsi_score = 60 + (10 - abs(rsi - 55) + 10) * 1.5  # 60-75
    elif rsi > 75:
        rsi_score = max(15, 60 - (rsi - 75) * 2)  # 超买
    else:  # rsi < 35
        rsi_score = max(20, 55 - (35 - rsi) * 2)  # 超卖但也可能是反弹机会
    rsi_score = float(np.clip(rsi_score, 0, 100))

    # 4) 量能：近 5 日均量 / 近 20 日均量
    # 1.0 = 中性 55；>1.5 放量 = 80+；<0.5 缩量 = 30-
    vol_ratio = float(volume.tail(5).mean() / (volume.tail(20).mean() + 1e-9))
    volume_score = float(np.clip(55 + (vol_ratio - 1) * 60, 15, 100))

    # 5) 波动率：ATR/收盘价
    # 1.5%-3.5% = 健康区间 85；<1% 呆滞 30；>6% 剧烈 30
    atr = _atr(df, 14).iloc[-1]
    atr_pct = float(atr / price)
    if 0.015 <= atr_pct <= 0.035:
        vol_std_score = 85 + (0.01 - abs(atr_pct - 0.025)) * 1500
    elif atr_pct < 0.015:
        vol_std_score = 30 + atr_pct * 3000  # 0% → 30, 1.5% → 75
    else:  # > 3.5%
        vol_std_score = max(20, 85 - (atr_pct - 0.035) * 1200)
    vol_std_score = float(np.clip(vol_std_score, 0, 100))

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
    try:
        df = market.daily(symbol, start=start, end=as_of)
    except Exception:
        return {"total": 50.0, "sub": {}, "error": "数据源不可用"} if with_detail else 50.0
    if df.empty:
        return {"total": 50.0, "sub": {}} if with_detail else 50.0

    subs = _sub_scores(df)
    # 等权平均
    total = round(sum(subs.values()) / len(subs), 2)
    if with_detail:
        return {"total": total, "sub": subs}
    return total
