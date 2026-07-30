"""
swing_v1 — 日级波段策略
========================

逻辑：
    1. 从股票池里筛出综合评分 >= threshold 的候选（默认 65）
    2. 按评分排序，取 Top N（配置里的 max_positions - 已持仓数量）
    3. 已持仓的不加仓（简化）
    4. 卖出交给风控（止损/止盈/到期），策略本身不主动生成卖出信号
    5. 若某只已持仓股跌出综合评分前 30%，可选生成主动减仓信号（默认关闭）

配置读取 configs/strategy.yaml 中的 swing_v1 段。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

import yaml

from paper_trade.broker import BuySignal
from paper_trade.risk import SellSignal


def _load_cfg(path: str | Path = "configs/strategy.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["swing_v1"]


def generate_signals(
    portfolio,
    universe: Iterable[str],
    as_of: str | None = None,
    min_score: float = 65.0,
    use_llm: bool = True,
    cfg_path: str | Path = "configs/strategy.yaml",
    weights: dict | None = None,
) -> tuple[list[BuySignal], list[SellSignal]]:
    """
    根据当前账户 + 股票池 + 综合评分生成买卖信号。

    Args:
        portfolio: paper_trade.portfolio.Portfolio
        universe: 候选股票池（list of 6 位代码）
        as_of: YYYY-MM-DD
        min_score: 综合评分下限
        use_llm: 是否用 LLM 打情绪分
        cfg_path: 策略配置
        weights: 四维权重字典，覆盖 cfg_path 里的默认值（用于回测切换风格）

    Returns:
        (buy_signals, sell_signals)
    """
    from analysis.scorer import rank_universe  # 惰性 import

    as_of = as_of or datetime.now().strftime("%Y-%m-%d")
    cfg = _load_cfg(cfg_path)
    max_positions = cfg.get("max_positions", 5)
    position_size = cfg.get("position_size", 0.18)

    # 排除已持仓的股票
    universe = [s for s in universe if s not in portfolio.positions]
    if not universe:
        return [], []

    ranked = rank_universe(universe, as_of=as_of, use_llm=use_llm, verbose=False, weights=weights)
    if ranked.empty:
        return [], []

    # 过滤分数下限 + 剩余仓位限制
    slots = max_positions - len(portfolio.positions)
    if slots <= 0:
        return [], []

    top = ranked[ranked["total"] >= min_score].head(slots)
    buys = [
        BuySignal(symbol=row["symbol"], target_pct=position_size, reason=f"swing_v1 综合分 {row['total']:.1f}")
        for _, row in top.iterrows()
    ]

    # 主动卖出信号：swing_v1 目前不主动卖，全交给风控
    sells: list[SellSignal] = []

    return buys, sells
