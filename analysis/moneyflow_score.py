"""
资金面评分
==========

子项：
    - 北向持仓变化：近 5 日陆股通持股比例增加加分
    - 主力净流入：近 5 日主力净流入天数
    - 换手率：适中（1%-8%）加分，过低（滞涨）或过高（异动风险）减分
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from data_layer import moneyflow, market


def _northbound_delta(symbol: str, days: int = 5) -> float:
    """近 N 日陆股通持股比例变化（百分点）。"""
    try:
        df = moneyflow.northbound_holdings(symbol)
        if df.empty:
            return 0.0
        col = next((c for c in df.columns if "持股比例" in c), None)
        if col is None or len(df) < days + 1:
            return 0.0
        # AkShare 该表按日期升序或降序不定，需要按日期列排序
        date_col = next((c for c in df.columns if "日期" in c or "date" in c.lower()), None)
        if date_col:
            df = df.sort_values(date_col)
        latest = float(df[col].iloc[-1])
        past = float(df[col].iloc[-1 - days])
        return latest - past
    except Exception:
        return 0.0


def _main_net_inflow_days(symbol: str, days: int = 5) -> int:
    """近 N 日主力净流入为正的天数。"""
    try:
        df = moneyflow.stock_moneyflow(symbol)
        if df.empty:
            return 0
        col = next((c for c in df.columns if "主力净流入" in c and "净额" in c), None) or \
              next((c for c in df.columns if "主力净流入" in c), None)
        if col is None:
            return 0
        recent = pd.to_numeric(df[col].tail(days), errors="coerce").fillna(0)
        return int((recent > 0).sum())
    except Exception:
        return 0


def _turnover_score(symbol: str, as_of: str | None = None) -> float:
    """换手率评分：近 5 日均值处于 1%-8% 加分。"""
    try:
        as_of = as_of or datetime.now().strftime("%Y-%m-%d")
        start = (datetime.strptime(as_of, "%Y-%m-%d") - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
        df = market.daily(symbol, start=start, end=as_of)
        if df.empty or "turnover_rate" not in df.columns:
            return 50.0
        recent = df["turnover_rate"].tail(5).mean()
        if 1.0 <= recent <= 8.0:
            return float(100 - abs(recent - 4) * 10)  # 4% 附近最高分
        return float(max(0, 100 - abs(recent - 4) * 15))
    except Exception:
        return 50.0


def score(symbol: str, as_of: str | None = None, with_detail: bool = False) -> float | dict:
    """资金面综合评分（0-100）。"""
    nb_delta = _northbound_delta(symbol, days=5)
    main_days = _main_net_inflow_days(symbol, days=5)
    turnover = _turnover_score(symbol, as_of)

    # 北向增持 0.5% → 100 分，减持 0.5% → 0 分
    nb_score = float(np.clip(50 + nb_delta * 100, 0, 100))
    # 5 天里 3 天以上主力净流入 → 高分
    main_score = float(np.clip(main_days / 5 * 100, 0, 100))

    subs = {
        "northbound": round(nb_score, 1),
        "main_inflow": round(main_score, 1),
        "turnover": round(turnover, 1),
    }
    total = round(sum(subs.values()) / len(subs), 2)
    if with_detail:
        return {"total": total, "sub": subs}
    return total
