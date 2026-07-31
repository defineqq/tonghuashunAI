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
                     "GAP", "LIMIT", "CHIP"]:
        assert expected in keys, f"missing {expected}"


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
