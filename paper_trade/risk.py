"""
风控规则
========

对当前持仓生成"必须卖出"的信号列表，供 broker 在每日执行前先触发。

规则（可通过 configs/strategy.yaml 调整）：
- 止损：单只跌 > stop_loss_pct 强制平仓
- 止盈：单只涨 > take_profit_pct 减半（或全平，看策略）
- 最长持有天数：> max_hold_days 强制平仓（避免长期套牢）
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from paper_trade.portfolio import Portfolio, Position


@dataclass
class RiskConfig:
    stop_loss_pct: float = 0.05      # 5% 止损
    take_profit_pct: float = 0.15    # 15% 止盈
    max_hold_days: int = 10          # 最长持有 10 天
    take_profit_action: str = "half" # "half" 减半 / "all" 全平


@dataclass
class SellSignal:
    symbol: str
    reason: str
    ratio: float = 1.0              # 卖出比例（1.0 = 全平, 0.5 = 减半）


def check(portfolio: Portfolio, today: str, cfg: RiskConfig) -> list[SellSignal]:
    """
    扫描所有持仓，输出需要卖出的信号。
    调用方：broker.execute_day() 在处理策略信号前先跑一遍风控。
    """
    signals = []
    for sym, pos in portfolio.positions.items():
        pnl_pct = pos.unrealized_pnl_pct
        hold_days = _days_between(pos.open_date, today)

        if pnl_pct <= -cfg.stop_loss_pct:
            signals.append(SellSignal(sym, f"止损（{pnl_pct*100:.1f}%）", 1.0))
        elif pnl_pct >= cfg.take_profit_pct:
            ratio = 0.5 if cfg.take_profit_action == "half" else 1.0
            signals.append(SellSignal(sym, f"止盈{'减半' if ratio<1 else '全平'}（+{pnl_pct*100:.1f}%）", ratio))
        elif hold_days >= cfg.max_hold_days:
            signals.append(SellSignal(sym, f"持有到期（{hold_days}天）", 1.0))
    return signals


def _days_between(start: str, end: str) -> int:
    return (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days
