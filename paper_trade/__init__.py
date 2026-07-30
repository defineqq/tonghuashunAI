"""
paper_trade — 本地模拟撮合与账户系统
====================================

模块划分：
- broker.py     成交模型（下单 → 按当日行情撮合）+ 手续费/滑点/印花税
- portfolio.py  账户状态：现金、持仓、历史成交、每日快照 JSON 持久化
- risk.py       风控规则：止损/止盈/最长持有天数/单只最大仓位

设计原则：
- 完全离线运行，不联券商，不需真钱
- 日度粒度：每天调用 execute_day(date) 触发一次撮合
- 状态持久化到 logs/portfolio/{account}.json，可断点续跑
"""

__all__ = ["broker", "portfolio", "risk"]
