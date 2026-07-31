"""7. 双推动 Dual Thrust — 突破上下轨买卖。"""

from __future__ import annotations

import pandas as pd

from strategies.base import (
    TechnicalStrategy, BarSignal, SignalAction,
    StrategyKind, StrategyMeta, StrategyParam,
)
from strategies.registry import registry


class DualThrustStrategy(TechnicalStrategy):
    meta = StrategyMeta(
        id="dual_thrust",
        name="Dual Thrust 双推动",
        kind=StrategyKind.PRESET,
        category="突破",
        description="用 N 日 HHV-LLC 和 HHC-LLV 定义波动幅度，突破买入/跌破卖出。",
        long_description="""
**逻辑**
- 计算过去 N 天的 range = max(HHV-LLC, HHC-LLV)（HHV=最高价的高，LLC=收盘价的低）
- 今日上轨 = 昨收 + K1 * range
- 今日下轨 = 昨收 - K2 * range
- **买入**：收盘价突破上轨
- **卖出**：收盘价跌破下轨

**特点**：Michael Chalek 提出的经典日内策略，对趋势启动敏感。
""",
        tags=["突破", "波动率"],
        params=[
            StrategyParam("n", "回看周期", "int", 5, 2, 30, 1),
            StrategyParam("k1", "上轨系数", "float", 0.5, 0.1, 2.0, 0.1, help="向上突破的敏感度"),
            StrategyParam("k2", "下轨系数", "float", 0.5, 0.1, 2.0, 0.1, help="向下突破的敏感度"),
        ],
    )

    def generate_signals(self, bars: pd.DataFrame, params: dict | None = None) -> list[BarSignal]:
        p = {**self.default_params(), **(params or {})}
        n, k1, k2 = int(p["n"]), float(p["k1"]), float(p["k2"])
        hh = bars["high"].rolling(n).max()
        lc = bars["close"].rolling(n).min()
        hc = bars["close"].rolling(n).max()
        ll = bars["low"].rolling(n).min()
        rng = pd.concat([(hh - lc), (hc - ll)], axis=1).max(axis=1)
        prev_close = bars["close"].shift(1)
        upper = prev_close + k1 * rng.shift(1)
        lower = prev_close - k2 * rng.shift(1)
        breakout = bars["close"] > upper
        breakdown = bars["close"] < lower
        signals = []
        for i, date in enumerate(bars["date"]):
            if bool(breakout.iloc[i]):
                signals.append(BarSignal(date, SignalAction.BUY, "突破上轨"))
            elif bool(breakdown.iloc[i]):
                signals.append(BarSignal(date, SignalAction.SELL, "跌破下轨"))
            else:
                signals.append(BarSignal(date, SignalAction.HOLD, ""))
        return signals


registry.register(DualThrustStrategy())
