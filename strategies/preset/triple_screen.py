"""10. 三重滤网 Triple Screen（Elder）— 长期趋势+中期指标+短期入场三重过滤。"""

from __future__ import annotations

import pandas as pd

from strategies.base import (
    TechnicalStrategy, BarSignal, SignalAction,
    StrategyKind, StrategyMeta, StrategyParam,
)
from strategies.registry import registry


class TripleScreenStrategy(TechnicalStrategy):
    meta = StrategyMeta(
        id="triple_screen",
        name="三重滤网",
        kind=StrategyKind.PRESET,
        category="综合",
        description="长期均线定趋势，中期 MACD 确认动量，短期回踩入场。三重过滤降低假信号。",
        long_description="""
**逻辑**（改编自 Alexander Elder 的三重滤网系统）
- **过滤 1：长期趋势**（EMA50）：只在向上趋势中考虑买入
- **过滤 2：动量方向**（MACD DIF > DEA）：确认中期动量向上
- **过滤 3：短期回踩**（RSI < 50 后反弹）：等短线回调时买入，不追高

**买入**：三个条件同时满足
**卖出**：EMA50 向下 或 MACD 死叉

**优势**：过滤大量假信号，胜率高于单一指标。
**劣势**：入场条件苛刻，牛市早期可能踏空。
""",
        tags=["组合", "多重过滤", "Elder"],
        params=[
            StrategyParam("trend_n", "长期均线", "int", 50, 20, 200, 5),
            StrategyParam("rsi_thr", "RSI 回踩阈值", "int", 50, 30, 70, 1, help="RSI 从下方穿越此值时视为回踩后反弹"),
        ],
    )

    def generate_signals(self, bars: pd.DataFrame, params: dict | None = None) -> list[BarSignal]:
        p = {**self.default_params(), **(params or {})}
        close = bars["close"]
        # 1. 长期趋势
        ema_long = self.ema(close, int(p["trend_n"]))
        trend_up = close > ema_long
        # 2. MACD 方向
        dif, dea, _ = self.macd(close)
        macd_up = dif > dea
        # 3. RSI 回踩反弹
        r = self.rsi(close, 14)
        rsi_bounce = (r > p["rsi_thr"]) & (r.shift() <= p["rsi_thr"])

        buy_now = trend_up & macd_up & rsi_bounce
        # 卖出：趋势反转
        trend_down = self.cross_down(close, ema_long)
        macd_death = self.cross_down(dif, dea)
        sell_now = trend_down | macd_death

        signals = []
        for i, date in enumerate(bars["date"]):
            if bool(buy_now.iloc[i]):
                signals.append(BarSignal(date, SignalAction.BUY, "三重滤网确认"))
            elif bool(sell_now.iloc[i]):
                signals.append(BarSignal(date, SignalAction.SELL, "趋势反转"))
            else:
                signals.append(BarSignal(date, SignalAction.HOLD, ""))
        return signals


registry.register(TripleScreenStrategy())
