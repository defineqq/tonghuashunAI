"""
daily_report_demo.py — 生成一份完整的每日选股分析报告
====================================================

用法：
    # 用配置文件的股票池（默认沪深300，前 50 只）
    python examples/daily_report_demo.py

    # 只跑指定的 5 只
    python examples/daily_report_demo.py --symbols 600519 000858 300750 600036 601318

    # 保存到文件
    python examples/daily_report_demo.py --save logs/reports/today.md

无 LLM API key 时，情绪评分会自动使用中性 stub（50 分）。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai_analysis import daily_report  # noqa: E402
from ai_analysis.llm_client import current_provider, is_configured  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", help="手动指定股票代码，如 600519 000858")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--as-of", default=None, help="截止日期 YYYY-MM-DD")
    p.add_argument("--save", default=None, help="保存路径，如 logs/reports/today.md")
    p.add_argument("--limit", type=int, default=50, help="不指定 --symbols 时，从股票池取前 N 只")
    args = p.parse_args()

    if is_configured():
        print(f"✅ LLM: {current_provider()}")
    else:
        print("⚠️  未配置 LLM API key，情绪评分使用中性 stub（50）")
        print("   在 .env 中填 ANTHROPIC_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY 之一即可启用")

    if args.symbols:
        symbols = args.symbols
    else:
        from data_layer import universe
        symbols = universe.load_pool()[: args.limit]

    save_path = args.save
    if not save_path and args.save is None:
        # 未指定 --save 时也默认保存一份
        as_of = args.as_of or datetime.now().strftime("%Y-%m-%d")
        save_path = ROOT / "logs" / "reports" / f"{as_of}.md"

    md = daily_report.render(
        as_of=args.as_of,
        symbols=symbols,
        top_n=args.top,
        save_to=save_path,
    )
    print("\n" + md)
    if save_path:
        print(f"\n📄 已保存: {save_path}")


if __name__ == "__main__":
    main()
