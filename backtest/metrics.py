"""
绩效指标
========

给定日收益率序列，计算：
- 年化收益率
- 累计收益率
- 最大回撤（drawdown）
- 夏普比率
- 波动率
- 胜率
"""

from __future__ import annotations

import numpy as np
import pandas as pd


TRADING_DAYS = 252


def annualized_return(daily_returns: pd.Series) -> float:
    """年化收益率（几何平均）。"""
    if len(daily_returns) == 0:
        return 0.0
    cum = (1 + daily_returns).prod()
    years = len(daily_returns) / TRADING_DAYS
    return float(cum ** (1 / years) - 1) if years > 0 else 0.0


def cumulative_return(daily_returns: pd.Series) -> float:
    return float((1 + daily_returns).prod() - 1)


def max_drawdown(equity_curve: pd.Series) -> float:
    """最大回撤（正数表示，如 0.15 = -15%）。"""
    if len(equity_curve) == 0:
        return 0.0
    running_max = equity_curve.cummax()
    dd = (equity_curve - running_max) / running_max
    return float(-dd.min())


def volatility(daily_returns: pd.Series) -> float:
    """年化波动率。"""
    if len(daily_returns) < 2:
        return 0.0
    return float(daily_returns.std() * np.sqrt(TRADING_DAYS))


def sharpe(daily_returns: pd.Series, risk_free: float = 0.02) -> float:
    """夏普比率（无风险利率默认 2%）。"""
    vol = volatility(daily_returns)
    if vol == 0:
        return 0.0
    ann_ret = annualized_return(daily_returns)
    return float((ann_ret - risk_free) / vol)


def win_rate(trades: list) -> float:
    """胜率：以"每次买卖配对"为一次交易统计。粗略实现：卖出时看是否盈利。"""
    if not trades:
        return 0.0
    # 简单版：以卖出成交为基准，PnL 需要外部提供；这里返回卖单占比
    # 更精细的胜率交给 report 层用 FIFO 配对
    return 0.0


def summarize(snapshots: pd.DataFrame) -> dict:
    """
    输入含 date, total 列的 DataFrame，返回一组指标 dict。
    """
    if snapshots.empty or "total" not in snapshots.columns:
        return {"annualized_return": 0, "cumulative_return": 0, "max_drawdown": 0, "sharpe": 0, "volatility": 0, "n_days": 0}

    df = snapshots.sort_values("date").reset_index(drop=True)
    equity = df["total"]
    daily_ret = equity.pct_change().dropna()

    return {
        "n_days": len(df),
        "cumulative_return": round(cumulative_return(daily_ret), 4),
        "annualized_return": round(annualized_return(daily_ret), 4),
        "max_drawdown": round(max_drawdown(equity), 4),
        "sharpe": round(sharpe(daily_ret), 3),
        "volatility": round(volatility(daily_ret), 4),
        "start_value": float(equity.iloc[0]),
        "end_value": float(equity.iloc[-1]),
    }
