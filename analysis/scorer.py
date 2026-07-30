"""
综合评分器
==========

按 configs/strategy.yaml 的权重把三/四个维度评分加权合并，输出候选股排名。

调用示例：
    from analysis.scorer import rank_universe
    top = rank_universe(["600519","000858","300750"], as_of="2024-12-01", top_n=5)
    print(top)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml

from analysis import technical, fundamental_score, moneyflow_score


def _load_weights(config_path: str | Path = "configs/strategy.yaml") -> dict:
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["swing_v1"]["weights"]


def score_one(symbol: str, as_of: str | None = None, weights: dict | None = None) -> dict:
    """
    对单只股票打四维度评分。sentiment 维度暂返回 50（中性），M2 阶段接入 LLM 后启用。
    """
    weights = weights or _load_weights()
    as_of = as_of or datetime.now().strftime("%Y-%m-%d")

    tech = technical.score(symbol, as_of=as_of, with_detail=True)
    fund = fundamental_score.score(symbol, as_of=as_of, with_detail=True)
    money = moneyflow_score.score(symbol, as_of=as_of, with_detail=True)
    sent_total = 50.0  # M2 阶段填充

    total = (
        tech["total"] * weights["technical"]
        + fund["total"] * weights["fundamental"]
        + sent_total * weights["sentiment"]
        + money["total"] * weights["moneyflow"]
    )

    return {
        "symbol": symbol,
        "as_of": as_of,
        "total": round(total, 2),
        "technical": tech["total"],
        "fundamental": fund["total"],
        "sentiment": sent_total,
        "moneyflow": money["total"],
        "detail": {
            "technical": tech["sub"],
            "fundamental": fund["sub"],
            "moneyflow": money["sub"],
        },
    }


def rank_universe(
    symbols: list[str],
    as_of: str | None = None,
    top_n: int | None = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """
    对一组股票打分并排序。

    Returns:
        DataFrame，按 total 降序，包含 symbol, total, technical, fundamental, sentiment, moneyflow 列。
    """
    weights = _load_weights()
    rows = []
    for i, sym in enumerate(symbols, 1):
        if verbose:
            print(f"[{i}/{len(symbols)}] scoring {sym}...")
        try:
            r = score_one(sym, as_of=as_of, weights=weights)
            rows.append({k: v for k, v in r.items() if k != "detail"})
        except Exception as e:
            if verbose:
                print(f"  失败: {e}")

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("total", ascending=False).reset_index(drop=True)
    if top_n:
        df = df.head(top_n)
    return df
