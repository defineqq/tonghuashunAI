"""
把 strategies/ 里的技术策略接入 backtest/engine.py 的策略函数签名。

技术策略吐"每根 K 线一个动作"，我们把它转换成：
    - 对**单只股票**的时间序列，通过 execute_day 逐日反馈到账户
    - 对**多只股票**的场景，每天用策略最新信号决定该股当日 buy/sell/hold

用法：
    from strategies.adapter import make_strategy_fn
    strategy_fn = make_strategy_fn("ma_cross", params={"fast": 5, "slow": 20})
    engine.run(strategy_fn=strategy_fn, universe=[...], start=..., end=...)
"""

from __future__ import annotations

import pandas as pd

from strategies.base import SignalAction, BarSignal
from strategies.registry import registry
from paper_trade.broker import BuySignal
from paper_trade.risk import SellSignal


def make_strategy_fn(strategy_id: str, params: dict | None = None,
                     position_size: float = 0.18, min_cash_pct: float = 0.10,
                     signal_lag_days: int = 1):
    """
    signal_lag_days: 信号延迟 N 日成交。默认 1 = "T-1 日收盘后产生信号 → T 日成交"，
    避免未来函数污染。设为 0 = 老行为（当日信号当日成交，会有未来函数）。
    """
    """
    把一个技术策略包装成 backtest.engine.run 需要的 strategy_fn。

    Args:
        strategy_id: 已注册的策略 id
        params: 覆盖默认参数
        position_size: 每只股票的仓位比例
        min_cash_pct: 保留最少现金比例（避免满仓）

    Returns:
        function (portfolio, universe, as_of) → (buys, sells)
    """
    strategy = registry.get(strategy_id)
    if strategy is None:
        raise ValueError(f"策略未注册: {strategy_id}")

    # 每只股票的信号缓存：{symbol: (last_end, {date_str: action_reason})}
    # 用 last_end 表示当时用到的结束日期，as_of 超过就重新算
    signal_cache: dict[str, tuple[str, dict[str, str]]] = {}

    def _get_signal_map(symbol: str, as_of: str) -> dict[str, str]:
        cached = signal_cache.get(symbol)
        if cached and cached[0] >= as_of:
            return cached[1]
        # 拉一大段数据（用 as_of + 半年余量做上限），减少重算次数
        from datetime import datetime, timedelta
        end_dt = datetime.strptime(as_of, "%Y-%m-%d") + timedelta(days=180)
        end_str = end_dt.strftime("%Y-%m-%d")

        from data_layer import market
        try:
            df = market.daily(symbol, start="2020-01-01", end=end_str)
        except Exception:
            signal_cache[symbol] = (end_str, {})
            return {}
        if df.empty:
            signal_cache[symbol] = (end_str, {})
            return {}
        # 为 MARKET_CAP 指标注入总市值（亿元）—— 从全 A 快照读，读不到就不注入
        try:
            snap = market.snapshot()
            mcap_col = next((c for c in snap.columns if "总市值" in c), None)
            code_col = next((c for c in snap.columns if c in ("代码", "symbol")), None)
            if mcap_col and code_col:
                snap_row = snap[snap[code_col].astype(str).str.zfill(6) == symbol]
                if not snap_row.empty:
                    df.attrs["market_cap_yi"] = float(snap_row[mcap_col].iloc[0]) / 1e8
        except Exception:
            pass
        try:
            bar_signals = strategy.generate_signals(df, params or {})
        except Exception:
            signal_cache[symbol] = (end_str, {})
            return {}
        # 信号左移 signal_lag_days 个交易日：T 日收盘产生的信号，映射到 T+lag 日成交
        # 用 df["date"] 作为交易日序列（自动跳过节假日/周末）
        dates = df["date"].reset_index(drop=True)
        date_index = {d: i for i, d in enumerate(dates)}
        m = {}
        for bs in bar_signals:
            if bs.action == SignalAction.HOLD:
                continue
            idx = date_index.get(bs.date)
            if idx is None:
                continue
            target_idx = idx + signal_lag_days
            if target_idx >= len(dates):
                continue  # 信号在最后几天，还没到成交日
            exec_date = dates.iloc[target_idx]
            m[exec_date.strftime("%Y-%m-%d")] = bs.action.value + "|" + bs.reason
        signal_cache[symbol] = (end_str, m)
        return m

    def strategy_fn(portfolio, universe, as_of, **kwargs):
        buys: list[BuySignal] = []
        sells: list[SellSignal] = []
        for symbol in universe:
            m = _get_signal_map(symbol, as_of)
            if as_of not in m:
                continue
            action, _, reason = m[as_of].partition("|")
            if action == "buy" and symbol not in portfolio.positions:
                buys.append(BuySignal(symbol=symbol, target_pct=position_size,
                                      reason=f"{strategy.meta.name}: {reason}"))
            elif action == "sell" and symbol in portfolio.positions:
                sells.append(SellSignal(symbol=symbol, reason=f"{strategy.meta.name}: {reason}", ratio=1.0))
        return buys, sells

    return strategy_fn
