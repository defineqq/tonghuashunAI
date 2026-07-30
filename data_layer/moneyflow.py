"""
资金流数据
==========

- 北向资金：陆股通每日流入
- 主力/超大单：个股主力净流入
- 板块资金流

短线波段最有效的资金面信号，通常是"北向异动"和"主力净流入连续正值"。
"""

from __future__ import annotations

import akshare as ak
import pandas as pd

from data_layer.cache import cached


@cached("moneyflow", max_age_hours=4)
def northbound_daily() -> pd.DataFrame:
    """
    北向资金每日净流入（沪股通 + 深股通合计），历史序列。

    Returns:
        columns: date, net_inflow_yi (亿元), sh_net, sz_net
    """
    df = ak.stock_hsgt_hist_em(symbol="北向资金")
    return df


@cached("moneyflow", max_age_hours=4)
def northbound_holdings(symbol: str) -> pd.DataFrame:
    """
    单只个股的北向资金持仓变化（陆股通每日持股）。
    """
    return ak.stock_hsgt_individual_em(stock=symbol)


@cached("moneyflow", max_age_hours=2)
def stock_moneyflow(symbol: str) -> pd.DataFrame:
    """
    个股主力资金流向（超大单/大单/中单/小单）历史序列。

    Returns:
        columns: date, close, pct_change, main_net (主力净流入), main_net_pct,
                 super_large, large, medium, small
    """
    # AkShare 需要 sh/sz 前缀
    market_prefix = "sh" if symbol.startswith("6") else "sz"
    return ak.stock_individual_fund_flow(stock=symbol, market=market_prefix)


@cached("moneyflow", max_age_hours=2)
def sector_moneyflow() -> pd.DataFrame:
    """
    今日板块资金流排行（申万一级行业）。
    """
    return ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
