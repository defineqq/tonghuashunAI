"""
模拟撮合器
==========

工作流：
    每日盘后调用 execute_day(portfolio, date, signals) 一次：
    1. 用当日收盘价 mark_to_market（更新持仓最新价 + PnL）
    2. 风控扫描：止损 / 止盈 / 到期 → 强制卖出
    3. 处理策略卖出信号（可能与风控重叠，去重）
    4. 处理策略买入信号（按仓位配置分配现金）
    5. 保存快照到 portfolio.daily_snapshots
    6. 持久化到 JSON

费用模型（A 股默认）：
    - 佣金：万分之三（双向），最低 5 元
    - 印花税：千分之一（仅卖方）
    - 过户费：万分之 0.2（沪市双向）
    - 滑点：千分之一（保守估计）
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import pandas as pd

from paper_trade.portfolio import Portfolio, Position, Trade
from paper_trade.risk import RiskConfig, SellSignal, check as risk_check


# ---- 信号类型 --------------------------------------------------------


@dataclass
class BuySignal:
    symbol: str
    target_pct: float             # 目标仓位（占总资金比例，如 0.18 = 18%）
    reason: str = "strategy"


@dataclass
class FeeConfig:
    commission_rate: float = 0.0003    # 万分之三
    commission_min: float = 5.0        # 每笔最低 5 元
    stamp_tax: float = 0.001           # 印花税 0.1%（仅卖方）
    transfer_fee: float = 0.00002      # 过户费 0.002%（沪市双向，深市不收）
    slippage: float = 0.001            # 滑点 0.1%


# ---- 撮合 -----------------------------------------------------------


def _round_lot(shares: int) -> int:
    """A 股买入按 100 股为单位。卖出可零售。"""
    return (shares // 100) * 100


def _buy_fees(amount: float, is_sh: bool, cfg: FeeConfig) -> float:
    commission = max(amount * cfg.commission_rate, cfg.commission_min)
    transfer = amount * cfg.transfer_fee if is_sh else 0.0
    return commission + transfer


def _sell_fees(amount: float, is_sh: bool, cfg: FeeConfig) -> float:
    commission = max(amount * cfg.commission_rate, cfg.commission_min)
    stamp = amount * cfg.stamp_tax
    transfer = amount * cfg.transfer_fee if is_sh else 0.0
    return commission + stamp + transfer


def _is_sh(symbol: str) -> bool:
    return symbol.startswith(("6", "9"))


def _fill_price(close: float, side: str, cfg: FeeConfig) -> float:
    """加上滑点：买单成交价略高，卖单成交价略低。"""
    return close * (1 + cfg.slippage) if side == "buy" else close * (1 - cfg.slippage)


def sell(
    portfolio: Portfolio,
    symbol: str,
    ratio: float,
    close_price: float,
    date: str,
    reason: str,
    fee_cfg: FeeConfig,
) -> Trade | None:
    """卖出持仓的 ratio 比例（0-1）。返回成交记录，若无持仓返回 None。"""
    if symbol not in portfolio.positions:
        return None
    pos = portfolio.positions[symbol]
    sell_shares = int(pos.shares * ratio)
    # 全平的话直接用全部数量，避免 int 截断
    if ratio >= 1.0:
        sell_shares = pos.shares
    if sell_shares <= 0:
        return None

    price = _fill_price(close_price, "sell", fee_cfg)
    amount = sell_shares * price
    fee = _sell_fees(amount, _is_sh(symbol), fee_cfg)
    net = amount - fee

    portfolio.cash += net
    pos.shares -= sell_shares
    if pos.shares == 0:
        del portfolio.positions[symbol]

    trade = Trade(
        date=date, symbol=symbol, side="sell",
        shares=sell_shares, price=round(price, 3),
        amount=round(amount, 2), fee=round(fee, 2), reason=reason,
    )
    portfolio.trades.append(trade)
    return trade


def buy(
    portfolio: Portfolio,
    symbol: str,
    target_amount: float,
    close_price: float,
    date: str,
    reason: str,
    fee_cfg: FeeConfig,
) -> Trade | None:
    """
    用 target_amount 元买入 symbol。会自动按 100 股整手取整，且预留手续费。
    如果现金不足或不够 1 手，返回 None。
    """
    if target_amount <= 0 or target_amount > portfolio.cash:
        target_amount = min(target_amount, portfolio.cash)

    price = _fill_price(close_price, "buy", fee_cfg)
    # 粗算能买多少股（预留 0.5% 给手续费）
    max_shares_raw = int(target_amount * 0.995 / price)
    shares = _round_lot(max_shares_raw)
    if shares < 100:
        return None

    amount = shares * price
    fee = _buy_fees(amount, _is_sh(symbol), fee_cfg)
    total_cost = amount + fee
    if total_cost > portfolio.cash:
        # 一手都买不起了，缩到能买的最大整手
        shares -= 100
        if shares < 100:
            return None
        amount = shares * price
        fee = _buy_fees(amount, _is_sh(symbol), fee_cfg)
        total_cost = amount + fee

    portfolio.cash -= total_cost

    if symbol in portfolio.positions:
        # 加仓：加权平均成本
        old = portfolio.positions[symbol]
        new_shares = old.shares + shares
        new_avg = (old.avg_cost * old.shares + total_cost) / new_shares
        portfolio.positions[symbol] = Position(
            shares=new_shares, avg_cost=new_avg,
            open_date=old.open_date, last_price=price,
        )
    else:
        portfolio.positions[symbol] = Position(
            shares=shares, avg_cost=total_cost / shares,
            open_date=date, last_price=price,
        )

    trade = Trade(
        date=date, symbol=symbol, side="buy",
        shares=shares, price=round(price, 3),
        amount=round(amount, 2), fee=round(fee, 2), reason=reason,
    )
    portfolio.trades.append(trade)
    return trade


def mark_to_market(portfolio: Portfolio, close_prices: dict[str, float]) -> None:
    """用当日收盘价更新所有持仓的 last_price。"""
    for sym, pos in portfolio.positions.items():
        if sym in close_prices:
            pos.last_price = close_prices[sym]


def execute_day(
    portfolio: Portfolio,
    date: str,
    close_prices: dict[str, float],
    buy_signals: Iterable[BuySignal] = (),
    sell_signals: Iterable[SellSignal] = (),
    risk_cfg: RiskConfig | None = None,
    fee_cfg: FeeConfig | None = None,
    max_positions: int = 5,
) -> dict:
    """
    执行一天的所有动作。

    Args:
        portfolio: 账户
        date: 今日 YYYY-MM-DD
        close_prices: {symbol: 收盘价}，需覆盖所有持仓 + 所有买入信号
        buy_signals: 策略买入信号
        sell_signals: 策略卖出信号（一般为空，主要靠风控 + 到期）
        risk_cfg: 风控配置
        fee_cfg: 费用配置
        max_positions: 最多同时持有的股票数

    Returns:
        {"trades": [...], "snapshot": ...}
    """
    risk_cfg = risk_cfg or RiskConfig()
    fee_cfg = fee_cfg or FeeConfig()

    # 1. mark to market
    mark_to_market(portfolio, close_prices)

    # 2. 风控信号
    risk_signals = risk_check(portfolio, date, risk_cfg)

    # 3. 合并所有卖出信号（风控优先，去重）
    all_sells: dict[str, SellSignal] = {s.symbol: s for s in risk_signals}
    for s in sell_signals:
        if s.symbol not in all_sells:
            all_sells[s.symbol] = s

    trades = []
    for sig in all_sells.values():
        if sig.symbol in close_prices:
            t = sell(portfolio, sig.symbol, sig.ratio, close_prices[sig.symbol], date, sig.reason, fee_cfg)
            if t:
                trades.append(t)

    # 4. 处理买入信号（受 max_positions 限制）
    slots = max_positions - len(portfolio.positions)
    buy_list = list(buy_signals)
    for sig in buy_list[:slots]:
        if sig.symbol not in close_prices:
            continue
        if sig.symbol in portfolio.positions:  # 已持仓不加仓（简化）
            continue
        target_amount = portfolio.total_value() * sig.target_pct
        target_amount = min(target_amount, portfolio.cash * 0.99)  # 留 1% 现金缓冲
        t = buy(portfolio, sig.symbol, target_amount, close_prices[sig.symbol], date, sig.reason, fee_cfg)
        if t:
            trades.append(t)

    # 5. 快照
    snap = portfolio.take_snapshot(date)

    return {"trades": trades, "snapshot": snap}
