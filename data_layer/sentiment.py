"""
情绪面数据
==========

- 公司公告（个股）
- 财经新闻（大盘）
- 龙虎榜
- 概念热度

这些"文本 + 结构化"数据是 LLM 分析层（M2 阶段）的输入原料。
"""

from __future__ import annotations

import akshare as ak
import pandas as pd

from data_layer.cache import cached


@cached("sentiment", max_age_hours=4)
def announcements(symbol: str, limit: int = 50) -> pd.DataFrame:
    """
    个股公告列表（最新在前）。

    Returns:
        columns: 公告标题, 公告日期, 公告链接
    """
    df = ak.stock_notice_report(symbol=symbol)
    return df.head(limit) if len(df) > limit else df


@cached("sentiment", max_age_hours=1)
def cls_news(limit: int = 100) -> pd.DataFrame:
    """
    财联社电报最新新闻（大盘全市场）。

    Returns:
        columns: 发布日期, 发布时间, 内容
    """
    df = ak.stock_info_global_cls(symbol="全部")
    return df.head(limit) if len(df) > limit else df


@cached("sentiment", max_age_hours=6)
def lhb_daily(date: str) -> pd.DataFrame:
    """
    某一天的龙虎榜（详细每日榜单）。

    Args:
        date: YYYYMMDD
    """
    return ak.stock_lhb_detail_em(start_date=date, end_date=date)


@cached("sentiment", max_age_hours=6)
def hot_concept() -> pd.DataFrame:
    """今日概念板块涨跌榜。"""
    return ak.stock_board_concept_name_em()
