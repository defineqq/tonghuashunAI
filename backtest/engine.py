"""
回测引擎
========

给定：
    - 策略函数 strategy(portfolio, universe, as_of) → (buys, sells)
    - 时间区间 [start, end]
    - 股票池 universe
    - 初始现金 initial_cash

引擎：
    对每个交易日 t：
    1. 收集所有相关股票 t 日的收盘价（会用到的：持仓 + 全池的候选）
    2. 调用策略生成买卖信号
    3. 调用 broker.execute_day 撮合
    4. 每 N 天打印一次进度

注意：为了让回测跑得动，评分时禁用 LLM（use_llm=False），情绪面统一 50。
      如果要做"含 LLM 的回测"，成本极高（每天每股一次调用），暂不做。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from data_layer import market
from paper_trade import portfolio as pfolio
from paper_trade.broker import execute_day, FeeConfig
from paper_trade.risk import RiskConfig


def get_trading_days(start: str, end: str, ref_symbol: str = "600519") -> list[str]:
    """
    用一只主流股票的日线索引作为交易日历（AkShare 数据里非交易日不出现）。

    数据源失败时降级：生成 start~end 内的所有工作日（周一~周五）。这不精确
    （会包含节假日），但足以让回测流程跑通、给用户一个可视化结果。
    """
    try:
        df = market.daily(ref_symbol, start=start, end=end)
        if not df.empty:
            return [d.strftime("%Y-%m-%d") for d in df["date"].tolist()]
    except Exception:
        pass

    # 降级：本地生成工作日
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    days = []
    d = start_dt
    while d <= end_dt:
        if d.weekday() < 5:  # 周一 0 到 周五 4
            days.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return days


def _load_close_prices(symbols: Iterable[str], date: str) -> dict[str, float]:
    """加载指定日期各股票的收盘价（用缓存）。"""
    result = {}
    for s in symbols:
        try:
            df = market.daily(s, start="2018-01-01", end=date)
            match = df[df["date"] <= pd.Timestamp(date)]
            if not match.empty:
                result[s] = float(match["close"].iloc[-1])
        except Exception:
            pass
    return result


def _load_price_info(symbols: Iterable[str], date: str) -> dict[str, dict]:
    """
    加载指定日期各股票的收盘价 + 涨跌幅。broker 用它判涨跌停能否成交。
    返回 {sym: {"close": float, "pct_change": float}}
    """
    result = {}
    for s in symbols:
        try:
            df = market.daily(s, start="2018-01-01", end=date)
            match = df[df["date"] <= pd.Timestamp(date)]
            if match.empty:
                continue
            last = match.iloc[-1]
            result[s] = {
                "close": float(last["close"]),
                "pct_change": float(last["pct_change"]) if "pct_change" in last else 0.0,
            }
        except Exception:
            pass
    return result


def run(
    strategy_fn: Callable,
    universe: list[str],
    start: str,
    end: str,
    initial_cash: float = 100_000.0,
    strategy_kwargs: dict | None = None,
    fee_cfg: FeeConfig | None = None,
    risk_cfg: RiskConfig | None = None,
    max_positions: int = 5,
    progress_every: int = 10,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> dict:
    """
    跑一段历史回测。

    Args:
        strategy_fn: 策略函数，签名 (portfolio, universe, as_of, **kwargs) → (buys, sells)
        universe: 股票池
        start / end: YYYY-MM-DD
        strategy_kwargs: 传给策略的额外参数

    Returns:
        {
          "portfolio": 最终账户,
          "snapshots": DataFrame of 每日快照,
          "metrics": dict,
        }
    """
    strategy_kwargs = strategy_kwargs or {}
    fee_cfg = fee_cfg or FeeConfig()
    risk_cfg = risk_cfg or RiskConfig()

    print(f"[backtest] 时间区间: {start} → {end}")
    print(f"[backtest] 股票池: {len(universe)} 只")
    print(f"[backtest] 初始资金: ¥{initial_cash:,.2f}")

    trading_days = get_trading_days(start, end)
    if not trading_days:
        raise RuntimeError(f"无法获取 {start}~{end} 的交易日历")
    print(f"[backtest] 交易日: {len(trading_days)}")

    port = pfolio.Portfolio.new(account_id="backtest", initial_cash=initial_cash)

    for i, date in enumerate(trading_days, 1):
        buys, sells = strategy_fn(port, universe, as_of=date, **strategy_kwargs)

        # 加载当日所有相关股票的收盘价 + 涨跌幅（判涨跌停用）
        relevant = set(list(port.positions.keys()) + [b.symbol for b in buys])
        price_info = _load_price_info(relevant, date)
        close_prices = {s: v["close"] for s, v in price_info.items()}

        execute_day(
            port, date, close_prices,
            buy_signals=buys, sell_signals=sells,
            risk_cfg=risk_cfg, fee_cfg=fee_cfg,
            max_positions=max_positions,
            price_info=price_info,
        )

        if i % progress_every == 0 or i == len(trading_days):
            snap = port.daily_snapshots[-1]
            print(f"  [{i}/{len(trading_days)}] {date}  总值 ¥{snap.total:,.0f}  PnL {snap.pnl_pct*100:+.2f}%  持仓 {snap.n_positions}")

        if progress_cb is not None:
            # 每天都通报（任务化下载/取消检测需要）
            progress_cb(i, len(trading_days), date)

    # 汇总
    from backtest.metrics import summarize
    snapshots = pd.DataFrame([{
        "date": s.date, "cash": s.cash, "positions_value": s.positions_value,
        "total": s.total, "pnl_pct": s.pnl_pct, "n_positions": s.n_positions,
    } for s in port.daily_snapshots])
    metrics = summarize(snapshots)

    return {"portfolio": port, "snapshots": snapshots, "metrics": metrics}
