"""
paper_trade_demo.py — 跑一次完整的"每日盘后模拟撮合"
==================================================

流程：
    1. 加载 / 新建假想账户（logs/portfolio/swing_v1.json）
    2. 从股票池生成 swing_v1 买入信号
    3. 拉当日收盘价
    4. execute_day 触发风控 + 撮合
    5. 保存账户，打印今日快照 + 成交列表

用法：
    python examples/paper_trade_demo.py                  # 使用配置文件里的股票池
    python examples/paper_trade_demo.py --limit 30       # 只跑前 30 只（加速）
    python examples/paper_trade_demo.py --date 2024-12-20
    python examples/paper_trade_demo.py --no-llm         # 跳过 LLM 评分（更快）
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--account", default="swing_v1")
    p.add_argument("--cash", type=float, default=100_000)
    p.add_argument("--date", default=None, help="模拟日期 YYYY-MM-DD, 默认今天")
    p.add_argument("--limit", type=int, default=50, help="股票池大小")
    p.add_argument("--min-score", type=float, default=65.0)
    p.add_argument("--no-llm", action="store_true")
    args = p.parse_args()

    from data_layer import universe as uni
    from data_layer import market
    from paper_trade import portfolio as pfolio
    from paper_trade.broker import execute_day, FeeConfig
    from paper_trade.risk import RiskConfig
    from my_strategies import swing_v1
    import yaml

    date = args.date or datetime.now().strftime("%Y-%m-%d")

    # 1. 账户
    port = pfolio.load_or_create(args.account, initial_cash=args.cash)
    print(f"账户 {args.account}: 现金 ¥{port.cash:.2f}, 持仓 {len(port.positions)} 只, 总值 ¥{port.total_value():.2f}")

    # 2. 股票池
    symbols = uni.load_pool()[: args.limit]
    print(f"股票池: {len(symbols)} 只")

    # 3. 生成信号
    print("生成信号中...（首次会拉数据+打分，可能较慢）")
    buys, sells = swing_v1.generate_signals(
        port, symbols, as_of=date, min_score=args.min_score, use_llm=not args.no_llm,
    )
    print(f"  买入信号: {len(buys)} 只")
    for b in buys:
        print(f"    - {b.symbol}: {b.reason}")

    # 4. 拉当日收盘价（覆盖持仓 + 买入信号）
    all_symbols = list(set(list(port.positions.keys()) + [b.symbol for b in buys]))
    close_prices = {}
    for s in all_symbols:
        try:
            df = market.daily(s, start="2020-01-01", end=date)
            if not df.empty:
                close_prices[s] = float(df["close"].iloc[-1])
        except Exception as e:
            print(f"  拉 {s} 收盘价失败: {e}")

    if not close_prices:
        print("⚠️  没有拿到任何收盘价，跳过撮合")
        return

    # 5. 加载风控参数
    with open("configs/strategy.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)["swing_v1"]
    risk_cfg = RiskConfig(
        stop_loss_pct=cfg.get("stop_loss_pct", 0.05),
        take_profit_pct=cfg.get("take_profit_pct", 0.15),
        max_hold_days=cfg.get("max_hold_days", 10),
    )

    # 6. execute
    result = execute_day(
        port, date, close_prices,
        buy_signals=buys, sell_signals=sells,
        risk_cfg=risk_cfg, fee_cfg=FeeConfig(),
        max_positions=cfg.get("max_positions", 5),
    )

    # 7. 保存
    port.save(pfolio.default_path(args.account))

    # 8. 打印
    snap = result["snapshot"]
    print(f"\n===== {date} 快照 =====")
    print(f"现金:     ¥{snap.cash:>12,.2f}")
    print(f"持仓市值: ¥{snap.positions_value:>12,.2f}")
    print(f"总值:     ¥{snap.total:>12,.2f}")
    print(f"累计 PnL: {snap.pnl_pct*100:>+6.2f}%")
    print(f"持仓数:   {snap.n_positions}")

    if result["trades"]:
        print("\n===== 今日成交 =====")
        for t in result["trades"]:
            print(f"  [{t.side}] {t.symbol} × {t.shares} @ ¥{t.price:.2f}  fee ¥{t.fee:.2f}  · {t.reason}")

    if port.positions:
        print("\n===== 当前持仓 =====")
        for sym, pos in port.positions.items():
            print(f"  {sym}: {pos.shares} 股 @ 成本 ¥{pos.avg_cost:.2f}  现价 ¥{pos.last_price:.2f}  PnL {pos.unrealized_pnl_pct*100:+.2f}%")

    print(f"\n📄 账户已保存到 logs/portfolio/{args.account}.json")


if __name__ == "__main__":
    main()
