"""
每日选股分析报告
================

组织：
1. 大盘情绪（LLM 分析财联社电报）
2. 综合评分 Top N 个股 + 每只的四维明细
3. 每只 Top 股的 LLM 情绪解读（利好利空要点、风险提示）

输出 Markdown 文本，可选保存到 logs/reports/YYYY-MM-DD.md
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


def _emoji_sentiment(s: str) -> str:
    return {
        "positive": "利好",
        "risk_on": "偏多",
        "neutral": "中性",
        "negative": "利空",
        "risk_off": "偏空",
    }.get(s, s)


def render(
    as_of: str | None = None,
    symbols: Iterable[str] | None = None,
    top_n: int = 10,
    save_to: str | Path | None = None,
) -> str:
    """
    生成一份完整每日报告。

    Args:
        as_of: YYYY-MM-DD
        symbols: 待分析的股票池；不填则使用 configs/stock_pool.yaml
        top_n: 精选 Top N
        save_to: 保存路径，不填只返回文本

    Returns:
        Markdown 文本
    """
    from ai_analysis import news_scorer
    from analysis.scorer import rank_universe
    from data_layer import universe

    as_of = as_of or datetime.now().strftime("%Y-%m-%d")

    # 1) 大盘情绪
    market = news_scorer.score(as_of=as_of, with_detail=True)

    # 2) 股票池
    if symbols is None:
        try:
            symbols = universe.load_pool()  # 从 configs/stock_pool.yaml
        except Exception as e:
            symbols = ["600519", "000858", "300750"]  # 兜底
            print(f"加载股票池失败，用兜底: {e}")
    symbols = list(symbols)

    # 3) 综合评分
    ranked = rank_universe(symbols, as_of=as_of, top_n=top_n, use_llm=True, verbose=False)

    # 4) 组织 Markdown
    lines = []
    lines.append(f"# A 股每日分析报告 · {as_of}")
    lines.append("")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · LLM: `{market.get('provider','stub')}`")
    lines.append("")

    lines.append("## 一、大盘情绪")
    lines.append("")
    lines.append(f"- **综合评分**：{market['total']}/100（{_emoji_sentiment(market.get('sentiment',''))}）")
    lines.append(f"- **一句话**：{market.get('reason','')}")
    if market.get("hot_sectors"):
        lines.append(f"- **热点板块**：{ '、'.join(market['hot_sectors']) }")
    if market.get("cold_sectors"):
        lines.append(f"- **承压板块**：{ '、'.join(market['cold_sectors']) }")
    if market.get("key_events"):
        lines.append("- **关键事件**：")
        for ev in market["key_events"]:
            lines.append(f"  - {ev}")
    lines.append("")

    lines.append(f"## 二、综合评分 Top {top_n}")
    lines.append("")
    if ranked.empty:
        lines.append("_(池子为空或全部评分失败)_")
    else:
        lines.append("| # | 代码 | 综合 | 技术 | 基本 | 情绪 | 资金 |")
        lines.append("|---|------|------|------|------|------|------|")
        for i, row in ranked.iterrows():
            lines.append(
                f"| {i+1} | {row['symbol']} | **{row['total']:.1f}** "
                f"| {row['technical']:.1f} | {row['fundamental']:.1f} "
                f"| {row['sentiment']:.1f} | {row['moneyflow']:.1f} |"
            )
    lines.append("")

    lines.append("## 三、免责声明")
    lines.append("")
    lines.append("本报告由算法与 LLM 自动生成，仅供研究参考，**不构成投资建议**。")
    lines.append("A 股市场波动剧烈，任何交易风险自负。")

    md = "\n".join(lines)

    if save_to:
        p = Path(save_to)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(md, encoding="utf-8")

    return md
