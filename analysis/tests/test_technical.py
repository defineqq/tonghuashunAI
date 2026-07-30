"""
technical.py 的单元测试（不依赖外部 API，构造假 DataFrame）
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from analysis.technical import _sub_scores  # noqa: E402


def _make_df(n: int = 120, trend: str = "up") -> pd.DataFrame:
    """构造一段假日线：trend='up'|'down'|'flat'"""
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    if trend == "up":
        close = np.linspace(10, 20, n) + np.random.normal(0, 0.1, n)
    elif trend == "down":
        close = np.linspace(20, 10, n) + np.random.normal(0, 0.1, n)
    else:
        close = 15 + np.random.normal(0, 0.2, n)
    df = pd.DataFrame({
        "date": dates,
        "open": close - 0.1,
        "high": close + 0.2,
        "low": close - 0.2,
        "close": close,
        "volume": np.random.randint(1_000_000, 5_000_000, n),
    })
    return df


def test_sub_scores_shape_and_range():
    np.random.seed(42)
    df = _make_df(120, "up")
    subs = _sub_scores(df)
    assert set(subs.keys()) == {"trend", "momentum", "rsi", "volume", "volatility"}
    for k, v in subs.items():
        assert 0 <= v <= 100, f"{k}={v} 超出 [0,100]"


def test_uptrend_scores_higher_than_downtrend():
    """上升趋势的 trend 子项分数应高于下降趋势。"""
    np.random.seed(42)
    up = _sub_scores(_make_df(120, "up"))
    np.random.seed(42)
    down = _sub_scores(_make_df(120, "down"))
    assert up["trend"] > down["trend"]


def test_short_data_returns_neutral():
    """数据不足 60 天返回中性分。"""
    df = _make_df(30)
    subs = _sub_scores(df)
    assert all(v == 50 for v in subs.values())


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
