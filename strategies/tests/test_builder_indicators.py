"""
条件构建器指标覆盖测试
======================

用合成数据保证每个新增指标：
1) 求值不抛异常
2) 返回和 bars 等长的 boolean Series
3) 至少能在预设场景下命中一次（防止逻辑写反）
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.builder import (
    INDICATORS, list_indicators, validate_spec, BuilderStrategy, _eval_rule,
)


@pytest.fixture
def bars() -> pd.DataFrame:
    """
    120 根合成 K 线：
    - 前 60 根震荡下跌，制造缩量、超卖、创新低
    - 后 60 根趋势上行，制造放量、连阳、创新高、涨停、跳空
    """
    n = 120
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    close = np.concatenate([
        100 + np.cumsum(np.random.RandomState(0).normal(-0.3, 1.0, 60)),
        # 后半段：稳步上涨 + 一次 10% 涨停 + 一次 3% 跳空
        90 + np.linspace(0, 25, 60),
    ])
    close[85] = close[84] * 1.10   # 涨停
    close[100] = close[99] * 0.90  # 跌停
    open_ = close - 0.5
    open_[70] = close[69] * 1.03   # 向上跳空
    open_[95] = close[94] * 0.97   # 向下跳空
    high = np.maximum(close, open_) + 0.5
    low  = np.minimum(close, open_) - 0.5
    volume = np.concatenate([
        np.random.RandomState(1).uniform(500, 800, 60),   # 前半段：低量
        np.random.RandomState(2).uniform(1500, 2500, 60), # 后半段：放量
    ])
    amount = volume * close
    turnover = np.concatenate([
        np.full(60, 0.5),
        np.full(60, 6.0),
    ])
    pct = np.concatenate([[0.0], np.diff(close) / close[:-1] * 100])
    return pd.DataFrame({
        "date": idx,
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume, "amount": amount,
        "turnover_rate": turnover, "pct_change": pct,
    })


# 每个 (indicator, op) 都应至少命中一次或至少不抛
CASES = [
    ("EMA",           "cross_up",       {"fast":5, "slow":20}, None),
    ("EMA",           "price_above",    {"fast":5, "slow":20}, None),
    ("MA_ARRANGE",    "bull",           {"short":5,"mid":20,"long":60}, None),
    ("MA_ARRANGE",    "bear",           {"short":5,"mid":20,"long":60}, None),
    ("VOLUME",        "surge",          {"n":20}, 1.5),
    ("VOLUME",        "shrink",         {"n":20}, 0.7),
    ("VOLUME",        "abs>",           {"n":20}, 100),
    ("AMOUNT",        "abs>",           {"n":20}, 0.0001),
    ("AMOUNT",        "ratio>",         {"n":20}, 1.2),
    ("TURNOVER",      ">",              {}, 3.0),
    ("TURNOVER",      "in",             {}, None),
    ("WR",            "<",              {"n":14}, -80),
    ("WR",            ">",              {"n":14}, -20),
    ("WR",            "cross_up",       {"n":14}, -80),
    ("CCI",           ">",              {"n":14}, 100),
    ("CCI",           "<",              {"n":14}, -100),
    ("CCI",           "cross_up",       {"n":14}, -100),
    ("OBV",           "cross_up",       {"n":30}, None),
    ("OBV",           "cross_down",     {"n":30}, None),
    ("ADX",           ">",              {"n":14}, 20),
    ("ADX",           "<",              {"n":14}, 80),
    ("HIGH_LOW_N",    "new_high",       {"n":20}, None),
    ("HIGH_LOW_N",    "new_low",        {"n":20}, None),
    ("CONSEC",        "up>=",           {}, 3),
    ("CONSEC",        "dn>=",           {}, 3),
    ("GAP",           "up>",            {}, 2.0),
    ("GAP",           "down>",          {}, 2.0),
    ("LIMIT",         "up",             {}, None),
    ("LIMIT",         "down",           {}, None),
    ("CHIP",          "profit>",        {"n":60}, 10),
    ("CHIP",          "trap>",          {"n":60}, 10),
    ("CHIP",          "concentration>", {"n":60}, 5),
    # ---- M8.9 新增，填 AI 反复抱怨"无法表达"的缺口 ----
    ("ATR",           "pct>",           {"n":14}, 1.0),
    ("ATR",           "pct<",           {"n":14}, 10.0),
    ("ATR",           "stop_hit",       {"n":14}, 1.5),
    ("SLOPE_MA",      "up>",            {"n":20, "lookback":5}, 0.1),
    ("SLOPE_MA",      "dn<",            {"n":20, "lookback":5}, -0.1),
    ("SLOPE_MA",      "rising",         {"n":20, "lookback":5}, None),
    ("SLOPE_MA",      "falling",        {"n":20, "lookback":5}, None),
    ("MACD_HIST",     "hist>0",         {}, None),
    ("MACD_HIST",     "hist<0",         {}, None),
    ("MACD_HIST",     "hist_expanding", {}, 3),
    ("MACD_HIST",     "hist_shrinking", {}, 3),
    ("MACD_HIST",     "dif_stay_above_zero", {}, 3),
    ("MACD_HIST",     "dif_stay_below_zero", {}, 3),
    ("STAY_MA",       "above",          {"n":20, "days":3}, None),
    ("STAY_MA",       "below",          {"n":20, "days":3}, None),
    ("MARKET_CAP",    ">",              {}, 100),
    ("MARKET_CAP",    "<",              {}, 1000),
]


@pytest.mark.parametrize("ind,op,params,value", CASES)
def test_indicator_evaluates(bars: pd.DataFrame, ind: str, op: str, params, value):
    rule = {"indicator": ind, "op": op, "params": params, "value": value}
    result = _eval_rule(bars, rule)
    assert isinstance(result, pd.Series)
    assert len(result) == len(bars)
    # 确保返回 boolean-like
    assert result.dtype == bool or result.dtype == object


def test_list_indicators_covers_new():
    keys = {i["key"] for i in list_indicators()}
    for expected in ["EMA", "MA_ARRANGE", "VOLUME", "AMOUNT", "TURNOVER",
                     "WR", "CCI", "OBV", "ADX", "HIGH_LOW_N", "CONSEC",
                     "GAP", "LIMIT", "CHIP",
                     "ATR", "SLOPE_MA", "MACD_HIST", "STAY_MA", "MARKET_CAP"]:
        assert expected in keys, f"missing {expected}"


# ---- 新指标：语义正确性验证（不是随便过就行） ----------------------


def test_slope_ma_up_matches_uptrend(bars):
    """合成数据后 60 根是稳步上涨，MA20 应该在上升。"""
    rule = {"indicator": "SLOPE_MA", "op": "rising",
            "params": {"n": 20, "lookback": 5}, "value": None}
    r = _eval_rule(bars, rule)
    # 上涨段（后半 60 根，让 MA20 有时间形成）应该大量命中
    assert r.iloc[-30:].sum() > 15, "上涨段 rising 命中太少"
    # 下跌段前面应该很少命中
    assert r.iloc[20:55].sum() < r.iloc[-30:].sum()


def test_slope_ma_falling_matches_downtrend(bars):
    rule = {"indicator": "SLOPE_MA", "op": "falling",
            "params": {"n": 20, "lookback": 5}, "value": None}
    r = _eval_rule(bars, rule)
    # 下跌段（前 60 根）后半段应该有一定命中
    early = r.iloc[25:55].sum()
    late = r.iloc[-30:].sum()
    assert early > late, f"falling 应更多在下跌段命中，实测 early={early} late={late}"


def test_stay_ma_above_requires_all_days(bars):
    """STAY_MA above 要求"连续 N 日"都在均线上；一天低于就不算。"""
    rule = {"indicator": "STAY_MA", "op": "above",
            "params": {"n": 20, "days": 3}, "value": None}
    r = _eval_rule(bars, rule)
    # 上涨段 stay above 命中数应大于下跌段
    assert r.iloc[-30:].sum() > r.iloc[25:55].sum()


def test_macd_hist_positive_vs_dif_cross_zero_differ(bars):
    """
    这条测试直接说明为什么要加 MACD_HIST：
    AI 反复抱怨 dif_above_zero 只是"上穿瞬间"，无法判断"当前柱状图是正"。
    新指标 hist>0 命中数应远大于旧的 dif_above_zero（后者一波趋势只命中 1 次）。
    """
    from strategies.base import TechnicalStrategy
    dif, dea, hist = TechnicalStrategy.macd(bars["close"])
    # 旧 op：只在上穿零轴那一根 K 线为 True
    old = TechnicalStrategy.cross_up(dif, pd.Series(0, index=dif.index))
    # 新 op：所有柱状图为正的 K 线都为 True
    r_new = _eval_rule(bars, {"indicator": "MACD_HIST", "op": "hist>0",
                              "params": {}, "value": None})
    assert r_new.sum() > old.sum() + 5, \
        f"MACD_HIST.hist>0 应比 dif 上穿零轴命中多得多，实测 new={r_new.sum()} old={old.sum()}"


def test_atr_stop_hit_triggers_on_pullback(bars):
    """
    ATR 追踪止损：在稳步上涨末段应无触发，回撤（如涨停后的调整）会触发。
    这里只验证"至少在整个序列上触发过"，避免假 True。
    """
    rule = {"indicator": "ATR", "op": "stop_hit",
            "params": {"n": 14}, "value": 1.5}
    r = _eval_rule(bars, rule)
    assert r.dtype == bool
    # 至少要有触发点（下跌段应该触发）
    assert r.sum() > 0, "ATR stop_hit 应至少触发一次"


def test_atr_pct_greater_than(bars):
    rule = {"indicator": "ATR", "op": "pct>",
            "params": {"n": 14}, "value": 0.1}
    r = _eval_rule(bars, rule)
    # 阈值极低（0.1%），几乎所有 K 线都应命中
    assert r.iloc[-50:].sum() > 40


def test_market_cap_uses_bars_attrs(bars):
    """MARKET_CAP 从 bars.attrs['market_cap_yi'] 读，缺失时不过滤。"""
    # 未注入市值：应全 True（不过滤）
    r_no = _eval_rule(bars, {"indicator": "MARKET_CAP", "op": ">",
                              "params": {}, "value": 100})
    assert r_no.all()

    # 注入 500 亿：过滤"> 100 亿"应全 True，过滤"> 1000 亿"应全 False
    bars_with_mcap = bars.copy()
    bars_with_mcap.attrs["market_cap_yi"] = 500.0
    r_pass = _eval_rule(bars_with_mcap, {"indicator": "MARKET_CAP", "op": ">",
                                          "params": {}, "value": 100})
    r_fail = _eval_rule(bars_with_mcap, {"indicator": "MARKET_CAP", "op": ">",
                                          "params": {}, "value": 1000})
    assert r_pass.all() and (not r_fail.any())


def test_validate_spec_accepts_new_indicators():
    spec = {
        "id": "test_new",
        "name": "综合新指标",
        "buy": {
            "logic": "AND",
            "rules": [
                {"indicator": "MA_ARRANGE", "op": "bull",
                 "params": {"short": 5, "mid": 20, "long": 60}},
                {"indicator": "VOLUME", "op": "surge",
                 "params": {"n": 20}, "value": 1.5},
            ],
        },
        "sell": {
            "logic": "OR",
            "rules": [
                {"indicator": "WR", "op": ">", "params": {"n": 14}, "value": -20},
            ],
        },
    }
    ok, err = validate_spec(spec)
    assert ok, err


def test_builder_strategy_runs(bars: pd.DataFrame):
    """端到端：拿新指标生成信号，能跑通不炸。"""
    spec = {
        "id": "e2e",
        "name": "端到端",
        "buy": {
            "logic": "AND",
            "rules": [
                {"indicator": "HIGH_LOW_N", "op": "new_high", "params": {"n": 20}},
                {"indicator": "VOLUME",     "op": "surge",    "params": {"n": 20}, "value": 1.2},
            ],
        },
        "sell": {
            "logic": "OR",
            "rules": [
                {"indicator": "WR", "op": ">", "params": {"n": 14}, "value": -20},
            ],
        },
    }
    ok, err = validate_spec(spec)
    assert ok, err
    strat = BuilderStrategy(spec)
    signals = strat.generate_signals(bars)
    assert len(signals) == len(bars)
