"""4. RSI 超卖反转 — RSI 低位买入，高位卖出。"""

from __future__ import annotations

import pandas as pd

from strategies.base import (
    TechnicalStrategy, BarSignal, SignalAction,
    StrategyKind, StrategyMeta, StrategyParam,
)
from strategies.registry import registry


class RSIReverseStrategy(TechnicalStrategy):
    meta = StrategyMeta(
        id="rsi_reverse",
        name="RSI 超卖反转",
        kind=StrategyKind.PRESET,
        category="均值回归",
        description="RSI 跌破 30 买入（超卖反弹），涨破 70 卖出（超买）。",
        long_description="""
**逻辑**
- 相对强弱指标 RSI(14)：0-100 范围，衡量近期涨跌力量
- **买入**：RSI 从下方穿越 30（超卖状态开始反弹）
- **卖出**：RSI 从上方穿越 70（超买状态开始回落）

**适用**：震荡市 + 蓝筹股。**大牛股会长期在 70+，此策略会过早卖出。**
""",
        tags=["震荡市", "超卖反弹"],
        params=[
            StrategyParam("n", "RSI 周期", "int", 14, 5, 30, 1),
            StrategyParam("oversold", "超卖阈值", "int", 30, 10, 40, 1, help="RSI 低于此值视为超卖"),
            StrategyParam("overbought", "超买阈值", "int", 70, 60, 90, 1, help="RSI 高于此值视为超买"),
        ],
    )

    def generate_signals(self, bars: pd.DataFrame, params: dict | None = None) -> list[BarSignal]:
        p = {**self.default_params(), **(params or {})}
        r = self.rsi(bars["close"], int(p["n"]))
        os_thr, ob_thr = int(p["oversold"]), int(p["overbought"])
        # 上穿 oversold 视为买入；下穿 overbought 视为卖出
        buy_cross = (r > os_thr) & (r.shift() <= os_thr)
        sell_cross = (r < ob_thr) & (r.shift() >= ob_thr)
        signals = []
        for i, date in enumerate(bars["date"]):
            if bool(buy_cross.iloc[i]):
                signals.append(BarSignal(date, SignalAction.BUY, f"RSI={r.iloc[i]:.0f} 反弹"))
            elif bool(sell_cross.iloc[i]):
                signals.append(BarSignal(date, SignalAction.SELL, f"RSI={r.iloc[i]:.0f} 回落"))
            else:
                signals.append(BarSignal(date, SignalAction.HOLD, ""))
        return signals


registry.register(RSIReverseStrategy())
