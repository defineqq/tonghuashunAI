"""
my_strategies — 自定义策略
=========================

- swing_v1.py  日级波段策略：综合评分选股 + 风控择时

约定：策略暴露一个 generate_signals(portfolio, universe, as_of) 函数，
返回 (buy_signals, sell_signals) tuple。
"""

__all__ = ["swing_v1"]
