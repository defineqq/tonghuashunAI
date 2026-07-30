"""
资金流数据
==========

- 北向资金：陆股通每日流入
- 主力/超大单：个股主力净流入
- 板块资金流

短线波段最有效的资金面信号，通常是"北向异动"和"主力净流入连续正值"。
"""

from __future__ import annotations

import pandas as pd

from data_layer.cache import cached


@cached("moneyflow", max_age_hours=4)
def northbound_daily() -> pd.DataFrame:
    """
    北向资金每日净流入（沪股通 + 深股通合计），历史序列。

    Returns:
        columns: date, net_inflow_yi (亿元), sh_net, sz_net
    """
    import akshare as ak
    df = ak.stock_hsgt_hist_em(symbol="北向资金")
    return df


@cached("moneyflow", max_age_hours=4)
def northbound_holdings(symbol: str) -> pd.DataFrame:
    """
    单只个股的北向资金持仓变化（陆股通每日持股）。
    """
    import akshare as ak
    return ak.stock_hsgt_individual_em(stock=symbol)


@cached("moneyflow", max_age_hours=2)
def stock_moneyflow(symbol: str) -> pd.DataFrame:
    """
    个股主力资金流向。

    尝试顺序：东财（有历史）→ 新浪（只有当日快照，但至少能用）。
    返回的 DataFrame 至少包含 date（新浪快照会用今天）+ 主力净流入相关列。
    """
    import akshare as ak

    # 首选：东财历史
    market_prefix = "sh" if symbol.startswith("6") else "sz"
    try:
        df = ak.stock_individual_fund_flow(stock=symbol, market=market_prefix)
        if not df.empty:
            return df
    except Exception:
        pass

    # 回退：新浪，从全 A 快照里筛出这只
    try:
        all_df = ak.stock_fund_flow_individual(symbol="即时")
        # 新浪列名：股票代码 / 股票简称 / 最新价 / 涨跌幅 / 换手率 / 流入资金 / 流出资金 / 净额 / 成交额
        code_col = next((c for c in all_df.columns if "代码" in c), None)
        if code_col:
            match = all_df[all_df[code_col].astype(str).str.zfill(6) == symbol]
            if not match.empty:
                # 构造成东财类似格式：单日一行，"主力净流入-净额" 用"净额"
                import pandas as pd
                from datetime import datetime
                row = match.iloc[0]
                today = datetime.now().strftime("%Y-%m-%d")
                # 净额单位换算（新浪返回万元字符串或数值）
                net = row.get("净额", 0)
                if isinstance(net, str):
                    try:
                        # 可能包含"万"字
                        net = float(net.replace(",", "").replace("万", ""))
                    except ValueError:
                        net = 0
                return pd.DataFrame([{
                    "日期": today,
                    "收盘价": row.get("最新价", 0),
                    "涨跌幅": row.get("涨跌幅", 0),
                    "主力净流入-净额": net,
                }])
    except Exception:
        pass

    return pd.DataFrame()


@cached("moneyflow", max_age_hours=2)
def sector_moneyflow() -> pd.DataFrame:
    """
    今日板块资金流排行（申万一级行业）。
    """
    import akshare as ak
    return ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
