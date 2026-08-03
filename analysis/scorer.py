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


_PROJECT_ROOT = Path(__file__).resolve().parents[1]


_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_weights(config_path: str | Path | None = None) -> dict:
    if config_path is None:
        config_path = _PROJECT_ROOT / "configs" / "strategy.yaml"
    p = Path(config_path)
    if not p.is_absolute() and not p.exists():
        p = _PROJECT_ROOT / p
    with open(p, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["swing_v1"]["weights"]


def score_one(symbol: str, as_of: str | None = None, weights: dict | None = None, use_llm: bool = True) -> dict:
    """
    对单只股票打四维度评分。

    Args:
        use_llm: True 且已配置 LLM key 时，用 LLM 打情绪分；否则退化为中性 50。
    """
    weights = weights or _load_weights()
    as_of = as_of or datetime.now().strftime("%Y-%m-%d")

    # 每一层都独立 try：任何单点失败降级为中性 50，不影响其他维度
    try:
        tech = technical.score(symbol, as_of=as_of, with_detail=True)
    except Exception as e:
        tech = {"total": 50.0, "sub": {}, "error": str(e)}
    try:
        fund = fundamental_score.score(symbol, as_of=as_of, with_detail=True)
    except Exception as e:
        fund = {"total": 50.0, "sub": {}, "error": str(e)}
    try:
        money = moneyflow_score.score(symbol, as_of=as_of, with_detail=True)
    except Exception as e:
        money = {"total": 50.0, "sub": {}, "error": str(e)}

    if use_llm:
        try:
            from ai_analysis import stock_scorer
            sent = stock_scorer.score(symbol, as_of=as_of, with_detail=True)
            sent_total = sent["total"]
            sent_sub = sent
        except Exception as e:
            sent_total = 50.0
            sent_sub = {"total": 50.0, "reason": f"LLM 评分失败: {e}", "provider": "stub"}
    else:
        sent_total = 50.0
        sent_sub = {"total": 50.0, "reason": "use_llm=False", "provider": "stub"}

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
            "technical": tech.get("sub", {}),
            "fundamental": fund.get("sub", {}),
            "moneyflow": money.get("sub", {}),
            "sentiment": sent_sub,
        },
    }


def rank_universe(
    symbols: list[str],
    as_of: str | None = None,
    top_n: int | None = None,
    use_llm: bool = True,
    verbose: bool = False,
    weights: dict | None = None,
) -> pd.DataFrame:
    """
    对一组股票打分并排序。

    Args:
        use_llm: 是否用 LLM 打情绪分。False 时跳过（跑几百只时更快）。
        weights: 四维权重字典。不填时读 configs/strategy.yaml。

    Returns:
        DataFrame，按 total 降序，包含 symbol, total, technical, fundamental, sentiment, moneyflow 列。
    """
    weights = weights or _load_weights()
    rows = []
    for i, sym in enumerate(symbols, 1):
        if verbose:
            print(f"[{i}/{len(symbols)}] scoring {sym}...")
        try:
            r = score_one(sym, as_of=as_of, weights=weights, use_llm=use_llm)
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
