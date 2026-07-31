"""2. MACD 金叉死叉 — 趋势 + 动量结合。"""

from __future__ import annotations

import pandas as pd

from strategies.base import (
    TechnicalStrategy, BarSignal, SignalAction,
    StrategyKind, StrategyMeta, StrategyParam,
)
from strategies.registry import registry


class MACDGoldenStrategy(TechnicalStrategy):
    meta = StrategyMeta(
        id="macd_golden",
        name="MACD 金叉死叉",
        kind=StrategyKind.PRESET,
        category="趋势",
        description="MACD 快慢线金叉时买入，死叉时卖出。趋势+动量的经典结合。",
        long_description="""
**逻辑**
- 计算 MACD 的 DIF 快线和 DEA 慢线（默认 12/26/9）
- **买入**：DIF 上穿 DEA（金叉）
- **卖出**：DIF 下穿 DEA（死叉）

**优势**：比单一均线更抗噪，因为用了指数加权，对近期变化更敏感。
**劣势**：滞后性仍存在，急涨急跌时反应慢。
""",
        tags=["经典", "趋势+动量"],
        params=[
            StrategyParam("fast", "快线", "int", 12, 2, 30, 1, help="快线 EMA 周期"),
            StrategyParam("slow", "慢线", "int", 26, 5, 60, 1, help="慢线 EMA 周期"),
            StrategyParam("signal", "信号线", "int", 9, 2, 20, 1, help="DEA 平滑周期"),
        ],
    )

    def generate_signals(self, bars: pd.DataFrame, params: dict | None = None) -> list[BarSignal]:
        p = {**self.default_params(), **(params or {})}
        dif, dea, _ = self.macd(bars["close"], p["fast"], p["slow"], p["signal"])
        golden = self.cross_up(dif, dea)
        death = self.cross_down(dif, dea)
        signals = []
        for i, date in enumerate(bars["date"]):
            if bool(golden.iloc[i]):
                signals.append(BarSignal(date, SignalAction.BUY, "MACD 金叉"))
            elif bool(death.iloc[i]):
                signals.append(BarSignal(date, SignalAction.SELL, "MACD 死叉"))
            else:
                signals.append(BarSignal(date, SignalAction.HOLD, ""))
        return signals


registry.register(MACDGoldenStrategy())
