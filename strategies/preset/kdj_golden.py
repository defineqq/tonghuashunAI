"""5. KDJ 金叉死叉 — 随机指标交叉信号。"""

from __future__ import annotations

import pandas as pd

from strategies.base import (
    TechnicalStrategy, BarSignal, SignalAction,
    StrategyKind, StrategyMeta, StrategyParam,
)
from strategies.registry import registry


class KDJGoldenStrategy(TechnicalStrategy):
    meta = StrategyMeta(
        id="kdj_golden",
        name="KDJ 金叉死叉",
        kind=StrategyKind.PRESET,
        category="震荡",
        description="K 线上穿 D 线时买入，下穿时卖出。灵敏度高于 MACD。",
        long_description="""
**逻辑**
- KDJ 是随机指标，反映近期价格在高低点区间的相对位置
- K 线（快）、D 线（慢）、J 线（更快，K 和 D 的差异放大）
- **买入**：K 上穿 D（KDJ 金叉）
- **卖出**：K 下穿 D（KDJ 死叉）

**优势**：反应快，捕捉短期反转比 MACD 快 1-3 天。
**劣势**：假信号多，需要配合成交量或其他过滤。
""",
        tags=["高灵敏度", "震荡市"],
        params=[
            StrategyParam("n", "RSV 周期", "int", 9, 5, 30, 1),
        ],
    )

    def generate_signals(self, bars: pd.DataFrame, params: dict | None = None) -> list[BarSignal]:
        p = {**self.default_params(), **(params or {})}
        k, d, _ = self.kdj(bars["high"], bars["low"], bars["close"], int(p["n"]))
        golden = self.cross_up(k, d)
        death = self.cross_down(k, d)
        signals = []
        for i, date in enumerate(bars["date"]):
            if bool(golden.iloc[i]):
                signals.append(BarSignal(date, SignalAction.BUY, f"KDJ 金叉 K={k.iloc[i]:.0f}"))
            elif bool(death.iloc[i]):
                signals.append(BarSignal(date, SignalAction.SELL, f"KDJ 死叉 K={k.iloc[i]:.0f}"))
            else:
                signals.append(BarSignal(date, SignalAction.HOLD, ""))
        return signals


registry.register(KDJGoldenStrategy())
