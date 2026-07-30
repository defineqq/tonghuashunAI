"""
大盘情绪评分器
==============

用 LLM 分析财联社近期电报，输出大盘 0-100 情绪分。
无 LLM key 时返回中性 50 分。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ai_analysis.llm_client import chat, current_provider
from data_layer import sentiment as sent_data


PROMPT_TMPL = (Path(__file__).parent / "prompts" / "market_sentiment.md").read_text(encoding="utf-8")


def _format_news(df, max_n: int = 40) -> str:
    if df.empty:
        return "(无)"
    df = df.head(max_n)
    time_col = next((c for c in df.columns if "时间" in c or "日期" in c), None)
    content_col = next((c for c in df.columns if "内容" in c or "标题" in c), None)
    if not (time_col and content_col):
        return df.to_string(index=False)
    lines = [f"- [{row[time_col]}] {row[content_col]}" for _, row in df.iterrows()]
    return "\n".join(lines)


def score(as_of: str | None = None, with_detail: bool = False):
    """
    大盘情绪评分。

    Args:
        as_of: YYYY-MM-DD
        with_detail: 返回明细

    Returns:
        int | dict
    """
    as_of = as_of or datetime.now().strftime("%Y-%m-%d")

    try:
        news = sent_data.cls_news(limit=50)
        news_text = _format_news(news)
    except Exception as e:
        news_text = f"(拉取失败: {e})"

    prompt = PROMPT_TMPL.format(as_of=as_of, news=news_text)
    resp = chat(prompt, json_mode=True)

    try:
        parsed = json.loads(resp)
    except json.JSONDecodeError:
        stripped = resp.strip().strip("`").lstrip("json").strip()
        try:
            parsed = json.loads(stripped)
        except Exception:
            parsed = {"score": 50, "sentiment": "neutral", "reason": "解析失败"}

    total = int(parsed.get("score", 50))
    if with_detail:
        return {
            "total": total,
            "sentiment": parsed.get("sentiment", "neutral"),
            "reason": parsed.get("reason", ""),
            "hot_sectors": parsed.get("hot_sectors", []),
            "cold_sectors": parsed.get("cold_sectors", []),
            "key_events": parsed.get("key_events", []),
            "provider": current_provider(),
        }
    return total
