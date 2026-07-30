"""
rank_hs300.py — 从沪深 300 中选出综合评分最高的 N 只
================================================

用法：
    python examples/rank_hs300.py               # 默认沪深300 前 10
    python examples/rank_hs300.py --pool 000905 # 中证500
    python examples/rank_hs300.py --top 20

首次运行会缓慢（要下 300+ 只股票的行情、估值、资金流数据），后续依赖缓存。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.scorer import rank_universe  # noqa: E402
from data_layer import universe  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pool", default="000300", help="指数代码：000300=沪深300, 000905=中证500")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--as-of", default=None, help="截止日期 YYYY-MM-DD, 默认今天")
    p.add_argument("--limit", type=int, default=None, help="调试用：只跑池子的前 N 只")
    p.add_argument("--no-llm", action="store_true", help="跳过 LLM 情绪评分（更快，但情绪维度全部 50）")
    args = p.parse_args()

    # 加载股票池
    idx_fn = {
        "000300": universe.hs300_constituents,
        "000905": universe.csi500_constituents,
        "000852": universe.csi1000_constituents,
    }.get(args.pool)
    if idx_fn is None:
        print(f"未知指数: {args.pool}")
        sys.exit(1)

    df_idx = idx_fn()
    code_col = next((c for c in df_idx.columns if "代码" in c and "指数" not in c), None)
    symbols = [str(x).zfill(6) for x in df_idx[code_col].tolist()]
    if args.limit:
        symbols = symbols[: args.limit]

    print(f"股票池: {args.pool} 共 {len(symbols)} 只，开始打分...")
    top = rank_universe(symbols, as_of=args.as_of, top_n=args.top, use_llm=not args.no_llm, verbose=True)

    print("\n===== 综合评分 Top {} =====".format(args.top))
    print(top.to_string(index=False))


if __name__ == "__main__":
    main()
