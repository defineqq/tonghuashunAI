"""
analysis — 四维度评分层
======================

对一只（或一组）股票在给定日期的四个维度打分，输出 0–100 分。
上层策略把四个分加权得到综合分，用于选股。

- technical.py         技术面：均线 / 动量 / 波动率 / 量能 / RSI
- fundamental_score.py 基本面：估值分位 / ROE / 增长 / 财务健康
- moneyflow_score.py   资金面：北向净流入 / 主力净流入 / 换手
- sentiment_score.py   情绪面：LLM 分析公告/新闻/龙虎榜（M2 阶段）
- scorer.py            综合打分 + 排序

约定：每个评分器暴露一个 score(symbol, as_of) -> float | dict 函数，返回 0-100。

注：这里刻意不做 eager import（子模块依赖 akshare 等）。按需 import 具体模块。
"""

__all__ = ["technical", "fundamental_score", "moneyflow_score", "scorer"]
