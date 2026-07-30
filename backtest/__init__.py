"""
backtest — 历史回测框架
======================

- engine.py   核心：给定策略 + 时间区间，逐日调用 execute_day，输出账户曲线
- metrics.py  绩效指标：年化收益、最大回撤、夏普、胜率
- report.py   报告输出：Markdown + CSV，可选画曲线（matplotlib 可选）
"""

__all__ = ["engine", "metrics", "report"]
