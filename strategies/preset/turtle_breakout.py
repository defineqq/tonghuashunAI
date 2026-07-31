"""6. 海龟交易法 — 唐奇安通道突破（简化版）。"""

from __future__ import annotations

import pandas as pd

from strategies.base import (
    TechnicalStrategy, BarSignal, SignalAction,
    StrategyKind, StrategyMeta, StrategyParam,
)
from strategies.registry import registry


class TurtleBreakoutStrategy(TechnicalStrategy):
    meta = StrategyMeta(
        id="turtle_breakout",
        name="海龟突破",
        kind=StrategyKind.PRESET,
        category="突破",
        description="突破 N 日高点买入，跌破 M 日低点卖出。经典的趋势跟踪。",
        long_description="""
**逻辑**
- **买入**：收盘价创出过去 N 日新高（默认 20 日）→ 突破入场
- **卖出**：收盘价创出过去 M 日新低（默认 10 日）→ 破位止损

**背景**：来自 1980 年代海龟交易实验，Richard Dennis 教一批完全没交易经验的
"海龟"用这套系统，据说四年半赚了 1.75 亿美元。

**适用**：大级别趋势市，比如 A 股 2014-2015、2020-2021 的板块行情。
**劣势**：震荡市里每次突破都被打脸，回撤大。
""",
        tags=["突破", "趋势跟踪", "海龟法则"],
        params=[
            StrategyParam("enter_n", "入场周期", "int", 20, 5, 100, 1, help="突破过去 N 日高点买入"),
            StrategyParam("exit_n", "出场周期", "int", 10, 3, 50, 1, help="跌破过去 N 日低点卖出"),
        ],
    )

    def generate_signals(self, bars: pd.DataFrame, params: dict | None = None) -> list[BarSignal]:
        p = {**self.default_params(), **(params or {})}
        enter_n, exit_n = int(p["enter_n"]), int(p["exit_n"])
        close = bars["close"]
        high_n = bars["high"].rolling(enter_n).max().shift(1)  # 用上一根截止的
        low_m = bars["low"].rolling(exit_n).min().shift(1)
        breakout = close > high_n
        breakdown = close < low_m
        signals = []
        for i, date in enumerate(bars["date"]):
            if bool(breakout.iloc[i]):
                signals.append(BarSignal(date, SignalAction.BUY, f"突破 {enter_n} 日高点"))
            elif bool(breakdown.iloc[i]):
                signals.append(BarSignal(date, SignalAction.SELL, f"跌破 {exit_n} 日低点"))
            else:
                signals.append(BarSignal(date, SignalAction.HOLD, ""))
        return signals


registry.register(TurtleBreakoutStrategy())
