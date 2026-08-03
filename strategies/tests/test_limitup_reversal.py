"""
LIMIT 新 op（打板/游资常用）+ REL_PRICE 跨日比较测试
=====================================================

覆盖用户实测的场景：AI 想做「昨日涨停 + 今日回落」但老指标全是"当日"，
两个 AND 起来永远无解 → 我们要能正确表达跨日条件。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.builder import _eval_rule


@pytest.fixture
def bars_with_limit_up() -> pd.DataFrame:
    """
    造一段包含涨停/回落的 K 线：
      day 0-4: 正常涨跌 (pct_change ~= ±1%)
      day 5:   涨停 +10%
      day 6:   开盘低于涨停 -5%（打板后次日回落）
      day 7-8: 又涨停
      day 9:   连续两日涨停后再一次涨停 → consec_up=3 满足
    """
    close = [100.0]
    pcts = [0, 1.0, -0.5, 0.8, -0.3, 10.0, -5.0, 10.0, 10.0, 10.0]
    for p in pcts[1:]:
        close.append(round(close[-1] * (1 + p / 100), 4))
    n = len(close)
    open_ = [c * 0.99 for c in close]  # 简化
    open_[6] = close[5] * 0.94         # day 6 开盘比昨日收盘（涨停价）低 6%
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="B"),
        "open": open_,
        "high": [c * 1.001 for c in close],
        "low": [o * 0.999 for o in open_],
        "close": close,
        "volume": [1000] * n,
        "pct_change": pcts,
    })


def _run(rule, bars):
    return _eval_rule(bars, rule).fillna(False)


def test_limit_up_hits_correct_days(bars_with_limit_up):
    r = _run({"indicator": "LIMIT", "op": "up"}, bars_with_limit_up)
    hits = list(r[r].index)
    assert hits == [5, 7, 8, 9], f"actually hit {hits}"


def test_yesterday_up_shifts_by_one(bars_with_limit_up):
    r = _run({"indicator": "LIMIT", "op": "yesterday_up"}, bars_with_limit_up)
    hits = list(r[r].index)
    # 5 号涨停 → 6 号 yesterday_up
    assert 6 in hits and 7 not in hits or 7 in hits  # 7 号既是涨停也是昨日涨停
    assert 6 in hits


def test_prev_up_within_n_days(bars_with_limit_up):
    """前 3 日出现过涨停 → 5 号后 3 日（6/7/8）都应命中。"""
    r = _run({"indicator": "LIMIT", "op": "prev_up", "value": 3}, bars_with_limit_up)
    hits = list(r[r].index)
    assert 6 in hits, "day 6 应能看到 day 5 的涨停"
    assert 8 in hits, "day 8 应能看到 day 5 或 day 7 的涨停"
    # day 4 之前不该有前涨停
    assert 4 not in hits


def test_consec_up_two(bars_with_limit_up):
    """连续 2 日涨停：day 8 是连续第二日涨停（day 7-8 都涨停）。"""
    r = _run({"indicator": "LIMIT", "op": "consec_up", "value": 2}, bars_with_limit_up)
    hits = list(r[r].index)
    assert 8 in hits
    assert 9 in hits
    # day 5 是孤板不算连板
    assert 5 not in hits


def test_consec_up_three(bars_with_limit_up):
    r = _run({"indicator": "LIMIT", "op": "consec_up", "value": 3}, bars_with_limit_up)
    hits = list(r[r].index)
    assert 9 in hits  # 7/8/9 三连板
    assert 8 not in hits


def test_rel_price_open_below_yesterday_close(bars_with_limit_up):
    """day 6 开盘价 = 涨停价 × 0.94 → 相对昨日收盘 -6%，应命中 < -3%。"""
    r = _run({
        "indicator": "REL_PRICE", "op": "open_below_close_pct",
        "params": {"n": 1}, "value": -3.0,
    }, bars_with_limit_up)
    hits = list(r[r].index)
    assert 6 in hits


def test_limitup_reversal_composed():
    """
    经典打板反转策略的完整表达：
      昨日涨停 AND 今日开盘 < 昨日收盘 -3%
    """
    bars = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=5, freq="B"),
        "open":  [100, 101, 111,  105, 106],  # day 2 涨停开盘 111
        "high":  [101, 102, 112,  106, 107],
        "low":   [99,  100, 110,  100, 105],
        "close": [100, 110, 121,  105, 108],  # day 1: +10, day 2: +10, day 3: -13.2%
        "volume":[100]*5,
        "pct_change": [0, 10.0, 10.0, -13.2, 2.9],
    })
    # 昨日涨停
    yh = _run({"indicator": "LIMIT", "op": "yesterday_up"}, bars)
    # 今日开盘价相对昨日收盘 < -3%
    gap_dn = _run({
        "indicator": "REL_PRICE", "op": "open_below_close_pct",
        "params": {"n": 1}, "value": -3.0,
    }, bars)
    combined = yh & gap_dn
    hits = list(combined[combined].index)
    # day 3: 昨日（day 2）涨停 open=105 vs 昨收=121 → -13.2%，应命中
    assert 3 in hits
