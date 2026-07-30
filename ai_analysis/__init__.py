"""
ai_analysis — LLM 驱动的情绪面评分与分析报告
============================================

模块：
- llm_client.py     统一 LLM 调用接口（支持 Claude / OpenAI / DeepSeek）
- news_scorer.py    分析财联社电报，输出大盘情绪评分
- stock_scorer.py   分析个股公告 + 龙虎榜 + 关联新闻，输出个股情绪评分
- daily_report.py   生成每日选股分析报告（markdown）
- prompts/          Prompt 模板

设计：
- 无 API key 时自动退化到 stub 模式（返回中性 50 分），保证下游能跑
- 支持多家 LLM 后端切换，用环境变量控制 LLM_PROVIDER

注：按需 import 具体模块。
"""

__all__ = ["llm_client", "news_scorer", "stock_scorer", "daily_report"]
