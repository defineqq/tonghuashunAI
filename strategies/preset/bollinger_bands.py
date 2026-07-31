"""3. 布林带 — 均值回归风格。价碰下轨买入，触上轨卖出。"""

from __future__ import annotations

import pandas as pd

from strategies.base import (
    TechnicalStrategy, BarSignal, SignalAction,
    StrategyKind, StrategyMeta, StrategyParam,
)
from strategies.registry import registry


class BollingerBandsStrategy(TechnicalStrategy):
    meta = StrategyMeta(
        id="bollinger_bands",
        name="布林带",
        kind=StrategyKind.PRESET,
        category="均值回归",
        description="价格跌破下轨买入，突破上轨卖出。适合震荡市。",
        long_description="""
**逻辑**
- 布林带 = 均线（默认 20 日）± N 倍标准差（默认 2 倍）
- **买入**：收盘价跌破下轨 → 超卖，博反弹
- **卖出**：收盘价突破上轨 → 超买，止盈

**适用**：横盘震荡市；不适合单边趋势（趋势市里价格可以持续贴着上轨/下轨走）。
""",
        tags=["震荡市", "均值回归"],
        params=[
            StrategyParam("n", "周期", "int", 20, 5, 60, 1, help="布林带均线天数"),
            StrategyParam("std_mult", "标准差倍数", "float", 2.0, 1.0, 3.0, 0.1,
                          help="上下轨距离均线的倍数。2.0 覆盖 95% 数据。"),
        ],
    )

    def generate_signals(self, bars: pd.DataFrame, params: dict | None = None) -> list[BarSignal]:
        p = {**self.default_params(), **(params or {})}
        upper, mid, lower = self.bollinger(bars["close"], int(p["n"]), float(p["std_mult"]))
        close = bars["close"]
        # 用穿越下轨/上轨作为信号，避免连续多次触发
        touched_lower = (close < lower) & (close.shift() >= lower.shift())
        touched_upper = (close > upper) & (close.shift() <= upper.shift())
        signals = []
        for i, date in enumerate(bars["date"]):
            if bool(touched_lower.iloc[i]):
                signals.append(BarSignal(date, SignalAction.BUY, f"跌破下轨 ¥{lower.iloc[i]:.2f}"))
            elif bool(touched_upper.iloc[i]):
                signals.append(BarSignal(date, SignalAction.SELL, f"突破上轨 ¥{upper.iloc[i]:.2f}"))
            else:
                signals.append(BarSignal(date, SignalAction.HOLD, ""))
        return signals


registry.register(BollingerBandsStrategy())
