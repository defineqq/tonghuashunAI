"""1. 双均线交叉（金叉/死叉）— 最经典的趋势跟踪策略。"""

from __future__ import annotations

import pandas as pd

from strategies.base import (
    TechnicalStrategy, BarSignal, SignalAction,
    StrategyKind, StrategyMeta, StrategyParam,
)
from strategies.registry import registry


class MACrossStrategy(TechnicalStrategy):
    meta = StrategyMeta(
        id="ma_cross",
        name="双均线交叉",
        kind=StrategyKind.PRESET,
        category="趋势",
        description="短期均线上穿长期均线时买入，下穿时卖出。经典的趋势跟踪策略。",
        long_description="""
**逻辑**
- 计算两条移动平均线：快线（默认 5 日）和慢线（默认 20 日）
- **买入**：快线上穿慢线（"金叉"）→ 趋势向上
- **卖出**：快线下穿慢线（"死叉"）→ 趋势向下

**适用**：趋势明确、有中期波动的市场；牛市和明确下跌市中效果最好。
**风险**：震荡市里会来回被"钓鱼"，产生大量假信号。
""",
        tags=["经典", "趋势跟踪", "适合新手"],
        params=[
            StrategyParam("fast", "快线周期", "int", 5, min=2, max=60, step=1,
                          help="短期均线的天数。数值越小信号越敏感。"),
            StrategyParam("slow", "慢线周期", "int", 20, min=5, max=250, step=1,
                          help="长期均线的天数。数值越大越稳。"),
        ],
    )

    def generate_signals(self, bars: pd.DataFrame, params: dict | None = None) -> list[BarSignal]:
        p = {**self.default_params(), **(params or {})}
        fast_n, slow_n = int(p["fast"]), int(p["slow"])
        close = bars["close"]
        fast_ma = self.sma(close, fast_n)
        slow_ma = self.sma(close, slow_n)
        golden = self.cross_up(fast_ma, slow_ma)
        death = self.cross_down(fast_ma, slow_ma)

        signals = []
        for i, date in enumerate(bars["date"]):
            if bool(golden.iloc[i]):
                signals.append(BarSignal(date, SignalAction.BUY, f"MA{fast_n} 上穿 MA{slow_n}"))
            elif bool(death.iloc[i]):
                signals.append(BarSignal(date, SignalAction.SELL, f"MA{fast_n} 下穿 MA{slow_n}"))
            else:
                signals.append(BarSignal(date, SignalAction.HOLD, ""))
        return signals


registry.register(MACrossStrategy())
