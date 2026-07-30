"""
基本面评分
==========

打分子项：
    - 估值分位：当前 PE / PB 处于历史（3 年）分位数越低越好
    - 盈利能力：ROE > 8% 加分（用财务摘要）
    - 增长性：营收 / 净利润同比增速

简化版：不依赖复杂财务模型，用 AkShare 能拿到的公开指标做粗略打分。
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from data_layer import fundamental


def _valuation_percentile(symbol: str, years: int = 3) -> tuple[float, float]:
    """
    返回 (PE 历史分位, PB 历史分位)，0=最低（最便宜），100=最高（最贵）。

    分位越低越"便宜"。
    """
    df = fundamental.valuation(symbol)
    if df.empty or "pe" not in df.columns:
        return 50.0, 50.0

    cutoff = datetime.now() - pd.Timedelta(days=years * 365)
    df = df[df["trade_date"] >= cutoff].dropna(subset=["pe", "pb"])
    if len(df) < 60:  # 数据太少无法算分位
        return 50.0, 50.0

    latest_pe = df["pe"].iloc[-1]
    latest_pb = df["pb"].iloc[-1]
    pe_pct = float((df["pe"] <= latest_pe).sum() / len(df) * 100)
    pb_pct = float((df["pb"] <= latest_pb).sum() / len(df) * 100)
    return pe_pct, pb_pct


def score(symbol: str, as_of: str | None = None, with_detail: bool = False) -> float | dict:
    """
    基本面综合评分（0-100）。

    子项：
        valuation:  估值分位（越低越加分，用 100 - 分位）
        profitability: ROE / 毛利率 达标度
        growth: 增长率
    """
    try:
        pe_pct, pb_pct = _valuation_percentile(symbol)
        val_score = 100 - (pe_pct + pb_pct) / 2  # 分位低 → 分高

        # 财务摘要能拿到 ROE、毛利率、营收增长率等
        fin = fundamental.financial_abstract(symbol)
        prof_score = 50.0
        growth_score = 50.0
        if not fin.empty:
            # AkShare stock_financial_abstract 返回的表结构是 (指标, 报告期1, 报告期2, ...)
            # 用最新一期
            if "指标" in fin.columns and fin.shape[1] > 1:
                latest_col = fin.columns[1]  # 最新报告期通常在第 2 列
                lookup = dict(zip(fin["指标"], fin[latest_col]))
                # ROE：> 15% 满分，8-15% 中，< 5% 差
                try:
                    roe = float(str(lookup.get("净资产收益率", "0")).replace("%", ""))
                    prof_score = float(np.clip(50 + (roe - 8) * 3, 0, 100))
                except (ValueError, TypeError):
                    pass
                # 营收增长率
                try:
                    growth = float(str(lookup.get("营业收入同比增长", "0")).replace("%", ""))
                    growth_score = float(np.clip(50 + growth * 2, 0, 100))
                except (ValueError, TypeError):
                    pass
    except Exception:
        val_score = prof_score = growth_score = 50.0

    subs = {
        "valuation": round(val_score, 1),
        "profitability": round(prof_score, 1),
        "growth": round(growth_score, 1),
    }
    total = round(sum(subs.values()) / len(subs), 2)
    if with_detail:
        return {"total": total, "sub": subs}
    return total
