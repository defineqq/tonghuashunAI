"""
hello_qbot.py — 最小验证示例
============================

目标：验证环境搭建 OK。跑通这一个脚本就说明：
    1. AkShare 能拉到 A 股行情
    2. Backtrader 能跑回测
    3. Qbot 提供的策略能被复用

用法：
    cd /home/gem/tonghuashunAI
    source .venv/bin/activate     # 先建好虚拟环境并装依赖
    python examples/hello_qbot.py

参数：默认回测 600519（贵州茅台）2023-01-01 至 2024-12-31 的 15 日均线策略。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import backtrader as bt
import akshare as ak
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "vendor" / "Qbot"))

from qbot.strategies.bigger_than_ema_bt import BiggerThanEmaStrategy  # noqa: E402


def fetch_daily(symbol: str, start: str, end: str) -> pd.DataFrame:
    """用 AkShare 拉 A 股日线，转成 backtrader 需要的列格式。"""
    raw = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
        adjust="qfq",
    )
    df = raw.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
        }
    )
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df["openinterest"] = 0
    return df[["open", "high", "low", "close", "volume", "openinterest"]]


def run_backtest(
    symbol: str = "600519",
    start: str = "2023-01-01",
    end: str = "2024-12-31",
    cash: float = 100_000.0,
    stake: int = 100,
) -> None:
    df = fetch_daily(symbol, start, end)
    print(f"拉取到 {symbol} {len(df)} 条日线 ({df.index.min().date()} → {df.index.max().date()})")

    cerebro = bt.Cerebro()
    data = bt.feeds.PandasData(
        dataname=df,
        fromdate=datetime.strptime(start, "%Y-%m-%d"),
        todate=datetime.strptime(end, "%Y-%m-%d"),
    )
    cerebro.adddata(data)
    cerebro.addstrategy(BiggerThanEmaStrategy)
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.addsizer(bt.sizers.FixedSize, stake=stake)

    print(f"期初资金: {cerebro.broker.getvalue():.2f}")
    cerebro.run()
    final = cerebro.broker.getvalue()
    print(f"期末资金: {final:.2f}")
    print(f"收益率:   {(final / cash - 1) * 100:.2f}%")


if __name__ == "__main__":
    run_backtest()
