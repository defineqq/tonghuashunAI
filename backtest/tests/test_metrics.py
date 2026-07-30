"""
backtest.metrics 的单测（构造已知序列验证公式）
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backtest.metrics import (  # noqa: E402
    annualized_return, cumulative_return, max_drawdown, sharpe, volatility, summarize,
)


def test_cumulative_return_flat():
    r = pd.Series([0.0, 0.0, 0.0])
    assert cumulative_return(r) == 0.0


def test_cumulative_return_gains():
    r = pd.Series([0.1, 0.1])   # (1.1 * 1.1) - 1 = 0.21
    assert abs(cumulative_return(r) - 0.21) < 1e-9


def test_max_drawdown_no_loss():
    curve = pd.Series([100.0, 110.0, 120.0])
    assert max_drawdown(curve) == 0.0


def test_max_drawdown_v():
    curve = pd.Series([100.0, 80.0, 90.0])
    # 从 100 跌到 80 → -20%
    assert abs(max_drawdown(curve) - 0.20) < 1e-9


def test_volatility_zero_for_flat():
    r = pd.Series([0.0, 0.0, 0.0, 0.0])
    assert volatility(r) == 0.0


def test_summarize_shape():
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=252),
        "total": np.linspace(100_000, 120_000, 252),
    })
    m = summarize(df)
    assert m["n_days"] == 252
    assert m["cumulative_return"] > 0
    assert m["end_value"] > m["start_value"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
