"""
回测报告输出
============

- 生成 Markdown 报告：策略概况 + 指标表 + Top 交易 + 每日净值
- 保存 snapshots.csv 和 trades.csv
- 可选：用 matplotlib 画净值曲线（若已安装）
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


def _try_plot(snapshots: pd.DataFrame, save_to: Path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    fig, ax = plt.subplots(figsize=(10, 5))
    df = snapshots.copy()
    df["date"] = pd.to_datetime(df["date"])
    ax.plot(df["date"], df["total"], label="Total Value", linewidth=1.5)
    ax.set_xlabel("Date")
    ax.set_ylabel("¥ Value")
    ax.set_title("Backtest Equity Curve")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(save_to, dpi=100)
    plt.close(fig)
    return True


def render(
    result: dict,
    strategy_name: str,
    out_dir: str | Path = "logs/backtests",
) -> Path:
    """
    输出 Markdown + CSV。返回主报告文件路径。
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(out_dir) / f"{strategy_name}_{ts}"
    out.mkdir(parents=True, exist_ok=True)

    portfolio = result["portfolio"]
    snapshots = result["snapshots"]
    metrics = result["metrics"]

    # 存 CSV
    snapshots.to_csv(out / "snapshots.csv", index=False, encoding="utf-8-sig")
    trades_df = pd.DataFrame([{
        "date": t.date, "symbol": t.symbol, "side": t.side,
        "shares": t.shares, "price": t.price, "amount": t.amount,
        "fee": t.fee, "reason": t.reason,
    } for t in portfolio.trades])
    trades_df.to_csv(out / "trades.csv", index=False, encoding="utf-8-sig")

    # 画图（可选）
    plotted = _try_plot(snapshots, out / "equity_curve.png")

    # Markdown
    lines = []
    lines.append(f"# 回测报告 · {strategy_name}")
    lines.append("")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    lines.append("## 关键指标")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|---|---|")
    lines.append(f"| 交易日数 | {metrics['n_days']} |")
    lines.append(f"| 起始净值 | ¥{metrics['start_value']:,.2f} |")
    lines.append(f"| 结束净值 | ¥{metrics['end_value']:,.2f} |")
    lines.append(f"| 累计收益 | {metrics['cumulative_return']*100:+.2f}% |")
    lines.append(f"| 年化收益 | {metrics['annualized_return']*100:+.2f}% |")
    lines.append(f"| 最大回撤 | {metrics['max_drawdown']*100:.2f}% |")
    lines.append(f"| 年化波动率 | {metrics['volatility']*100:.2f}% |")
    lines.append(f"| 夏普比率 | {metrics['sharpe']:.2f} |")
    lines.append(f"| 总成交笔数 | {len(portfolio.trades)} |")
    lines.append("")

    if plotted:
        lines.append("## 净值曲线")
        lines.append("")
        lines.append(f"![Equity Curve](./equity_curve.png)")
        lines.append("")

    lines.append("## 最近 20 笔成交")
    lines.append("")
    if not trades_df.empty:
        lines.append("| 日期 | 方向 | 股票 | 数量 | 成交价 | 金额 | 手续费 | 原因 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for _, row in trades_df.tail(20).iterrows():
            lines.append(
                f"| {row['date']} | {row['side']} | {row['symbol']} | {row['shares']} "
                f"| ¥{row['price']:.2f} | ¥{row['amount']:,.0f} | ¥{row['fee']:.2f} | {row['reason']} |"
            )
    else:
        lines.append("_(无交易)_")

    lines.append("")
    lines.append("## 文件清单")
    lines.append(f"- `snapshots.csv`：每日快照")
    lines.append(f"- `trades.csv`：全部成交明细")
    if plotted:
        lines.append(f"- `equity_curve.png`：净值曲线图")

    md_path = out / "report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path
