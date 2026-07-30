"""
个股情绪评分器
==============

用 LLM 分析个股近期公告 + 相关新闻，输出 0-100 分。
无 LLM key 时自动返回中性 50 分。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ai_analysis.llm_client import chat, current_provider
from data_layer import sentiment as sent_data


PROMPT_TMPL = (Path(__file__).parent / "prompts" / "stock_sentiment.md").read_text(encoding="utf-8")


def _format_announcements(df, max_n: int = 15) -> str:
    if df.empty:
        return "(无)"
    df = df.head(max_n)
    title_col = next((c for c in df.columns if "标题" in c), None)
    date_col = next((c for c in df.columns if "日期" in c), None)
    if not (title_col and date_col):
        return df.head(max_n).to_string(index=False)
    lines = [f"- [{row[date_col]}] {row[title_col]}" for _, row in df.iterrows()]
    return "\n".join(lines)


def score(symbol: str, name: str = "", as_of: str | None = None, with_detail: bool = False):
    """
    对单只股票做 LLM 情绪评分。

    Args:
        symbol: 6 位代码
        name:   股票名称（可选，仅用于 prompt 里显示）
        as_of:  YYYY-MM-DD
        with_detail: True 时返回 {total, sentiment, reason, highlights, risk_flags, provider}

    Returns:
        int | dict
    """
    as_of = as_of or datetime.now().strftime("%Y-%m-%d")

    try:
        ann = sent_data.announcements(symbol, limit=20)
        ann_text = _format_announcements(ann)
    except Exception as e:
        ann_text = f"(拉取失败: {e})"

    # 相关新闻：简化起见先留空，M2 后续扩展
    news_text = "(暂未接入个股相关新闻)"

    prompt = PROMPT_TMPL.format(
        symbol=symbol,
        name=name or symbol,
        as_of=as_of,
        announcements=ann_text,
        news=news_text,
    )

    resp = chat(prompt, json_mode=True)
    try:
        parsed = json.loads(resp)
    except json.JSONDecodeError:
        # LLM 可能返回带 markdown 代码块的 JSON，简单剥离一下
        stripped = resp.strip().strip("`").lstrip("json").strip()
        try:
            parsed = json.loads(stripped)
        except Exception:
            parsed = {"score": 50, "sentiment": "neutral", "reason": "解析失败", "highlights": [], "risk_flags": []}

    total = int(parsed.get("score", 50))
    if with_detail:
        return {
            "total": total,
            "sentiment": parsed.get("sentiment", "neutral"),
            "reason": parsed.get("reason", ""),
            "highlights": parsed.get("highlights", []),
            "risk_flags": parsed.get("risk_flags", []),
            "provider": current_provider(),
        }
    return total
