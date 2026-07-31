"""8. 均值回归 — 跌得多买入，涨得多卖出（Z-score）。"""

from __future__ import annotations

import pandas as pd

from strategies.base import (
    TechnicalStrategy, BarSignal, SignalAction,
    StrategyKind, StrategyMeta, StrategyParam,
)
from strategies.registry import registry


class MeanReversionStrategy(TechnicalStrategy):
    meta = StrategyMeta(
        id="mean_reversion",
        name="均值回归 Z-Score",
        kind=StrategyKind.PRESET,
        category="均值回归",
        description="用 Z-score 衡量偏离度：偏离 -2 倍标准差买入，+2 卖出。",
        long_description="""
**逻辑**
- 计算收盘价近 N 日的均值 μ 和标准差 σ
- Z-score = (今日 - μ) / σ，衡量今日相对平均水平偏离多少个标准差
- **买入**：Z-score < -2（相当罕见的低位）
- **卖出**：Z-score > +2（相当罕见的高位）

**适用**：横盘/震荡的大盘蓝筹；不适合有强劲趋势的股票。
""",
        tags=["均值回归", "统计套利"],
        params=[
            StrategyParam("n", "回看周期", "int", 20, 5, 60, 1),
            StrategyParam("z_buy", "买入 Z 阈值", "float", -2.0, -3.0, -0.5, 0.1),
            StrategyParam("z_sell", "卖出 Z 阈值", "float", 2.0, 0.5, 3.0, 0.1),
        ],
    )

    def generate_signals(self, bars: pd.DataFrame, params: dict | None = None) -> list[BarSignal]:
        p = {**self.default_params(), **(params or {})}
        n = int(p["n"])
        close = bars["close"]
        mean = close.rolling(n).mean()
        std = close.rolling(n).std().replace(0, 1e-9)
        z = (close - mean) / std
        # 用穿越触发，避免连续多次
        buy_cross = (z < p["z_buy"]) & (z.shift() >= p["z_buy"])
        sell_cross = (z > p["z_sell"]) & (z.shift() <= p["z_sell"])
        signals = []
        for i, date in enumerate(bars["date"]):
            if bool(buy_cross.iloc[i]):
                signals.append(BarSignal(date, SignalAction.BUY, f"Z={z.iloc[i]:.2f} 严重偏低"))
            elif bool(sell_cross.iloc[i]):
                signals.append(BarSignal(date, SignalAction.SELL, f"Z={z.iloc[i]:.2f} 严重偏高"))
            else:
                signals.append(BarSignal(date, SignalAction.HOLD, ""))
        return signals


registry.register(MeanReversionStrategy())
