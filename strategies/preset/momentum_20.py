"""9. 20 日动量 — 追近期涨幅最猛的股票。"""

from __future__ import annotations

import pandas as pd

from strategies.base import (
    TechnicalStrategy, BarSignal, SignalAction,
    StrategyKind, StrategyMeta, StrategyParam,
)
from strategies.registry import registry


class Momentum20Strategy(TechnicalStrategy):
    meta = StrategyMeta(
        id="momentum_20",
        name="20 日动量",
        kind=StrategyKind.PRESET,
        category="动量",
        description="近 N 日涨幅超过阈值时买入，跌幅超过阈值时卖出。",
        long_description="""
**逻辑**
- 计算近 N 日收益率
- **买入**：近 N 日涨幅 > 阈值（默认 5%，表示"强势启动"）
- **卖出**：近 N 日涨幅 < 卖出阈值（默认 -3%）

**适用**：牛市中期，寻找强势加速股。
**风险**：容易追高，一旦回调很惨。
""",
        tags=["动量", "追强势"],
        params=[
            StrategyParam("n", "动量周期", "int", 20, 5, 60, 1),
            StrategyParam("buy_thr", "买入涨幅 %", "float", 5.0, 1.0, 30.0, 0.5, help="近 N 日涨幅大于此值买入"),
            StrategyParam("sell_thr", "卖出跌幅 %", "float", -3.0, -20.0, -0.5, 0.5, help="近 N 日跌幅小于此值卖出"),
        ],
    )

    def generate_signals(self, bars: pd.DataFrame, params: dict | None = None) -> list[BarSignal]:
        p = {**self.default_params(), **(params or {})}
        n = int(p["n"])
        ret = bars["close"].pct_change(n) * 100
        buy_cross = (ret > p["buy_thr"]) & (ret.shift() <= p["buy_thr"])
        sell_cross = (ret < p["sell_thr"]) & (ret.shift() >= p["sell_thr"])
        signals = []
        for i, date in enumerate(bars["date"]):
            if bool(buy_cross.iloc[i]):
                signals.append(BarSignal(date, SignalAction.BUY, f"近{n}日涨幅 {ret.iloc[i]:.1f}%"))
            elif bool(sell_cross.iloc[i]):
                signals.append(BarSignal(date, SignalAction.SELL, f"近{n}日跌幅 {ret.iloc[i]:.1f}%"))
            else:
                signals.append(BarSignal(date, SignalAction.HOLD, ""))
        return signals


registry.register(Momentum20Strategy())
