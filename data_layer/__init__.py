"""
data_layer — 统一数据接口层
==========================

对 AkShare 的一层薄封装，加本地 parquet 缓存，让上层策略/分析层不用关心底层数据源。

模块划分：
- cache.py       本地缓存工具（parquet + 时效策略）
- market.py      行情：日线、分钟线、实时快照
- fundamental.py 基本面：财报、估值、行业
- moneyflow.py   资金流：北向、主力净流入、大单
- sentiment.py   情绪面：新闻、公告、龙虎榜
- universe.py    股票池：沪深300/中证500 成分股、过滤规则

用法：
    from data_layer import market
    df = market.daily("600519", start="2024-01-01", end="2024-12-31")
"""

from data_layer import market, fundamental, moneyflow, sentiment, universe  # noqa: F401

__all__ = ["market", "fundamental", "moneyflow", "sentiment", "universe"]
