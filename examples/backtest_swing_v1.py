"""
backtest_swing_v1.py — 对 swing_v1 策略做历史回测
=============================================

用法：
    # 最小示例：小池子 + 短时间（快速验证）
    python examples/backtest_swing_v1.py --limit 20 --start 2024-06-01 --end 2024-09-30

    # 完整回测（沪深300 全池，1 年）
    python examples/backtest_swing_v1.py --start 2024-01-01 --end 2024-12-31

    # 换池
    python examples/backtest_swing_v1.py --pool 000905 --start 2024-06-01 --end 2024-12-31
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pool", default="000300")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--cash", type=float, default=100_000)
    p.add_argument("--limit", type=int, default=None, help="调试用：只跑池子的前 N 只")
    p.add_argument("--min-score", type=float, default=65.0)
    args = p.parse_args()

    from data_layer import universe as uni
    from my_strategies import swing_v1
    from backtest import engine, report

    idx_fn = {
        "000300": uni.hs300_constituents,
        "000905": uni.csi500_constituents,
        "000852": uni.csi1000_constituents,
    }.get(args.pool)
    if idx_fn is None:
        print(f"未知指数: {args.pool}")
        sys.exit(1)

    df_idx = idx_fn()
    code_col = next((c for c in df_idx.columns if "代码" in c and "指数" not in c), None)
    symbols = [str(x).zfill(6) for x in df_idx[code_col].tolist()]
    if args.limit:
        symbols = symbols[: args.limit]

    result = engine.run(
        strategy_fn=swing_v1.generate_signals,
        universe=symbols,
        start=args.start,
        end=args.end,
        initial_cash=args.cash,
        strategy_kwargs={"min_score": args.min_score, "use_llm": False},  # 回测禁用 LLM
        max_positions=5,
    )

    print("\n===== 回测汇总 =====")
    for k, v in result["metrics"].items():
        print(f"  {k}: {v}")

    md_path = report.render(result, strategy_name="swing_v1")
    print(f"\n📄 报告已生成: {md_path}")


if __name__ == "__main__":
    main()
