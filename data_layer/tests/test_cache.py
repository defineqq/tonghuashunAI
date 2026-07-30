"""
data_layer 结构与缓存机制的冒烟测试
================================

用 pytest 跑：
    pytest data_layer/tests -v

也可以直接跑：
    python data_layer/tests/test_cache.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# 项目根加入路径
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from data_layer.cache import cached, _fingerprint, clear_cache  # noqa: E402


def test_fingerprint_deterministic():
    """相同参数产生相同指纹，顺序不敏感。"""
    a = _fingerprint(symbol="600519", start="2024-01-01", end="2024-12-31")
    b = _fingerprint(end="2024-12-31", symbol="600519", start="2024-01-01")
    assert a == b


def test_fingerprint_differs_by_param():
    """不同参数产生不同指纹。"""
    a = _fingerprint(symbol="600519")
    b = _fingerprint(symbol="000858")
    assert a != b


def test_cache_roundtrip(tmp_path, monkeypatch):
    """装饰器：首次调用真正执行函数，第二次命中缓存。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    call_count = {"n": 0}

    @cached("test_ns", max_age_hours=None)
    def mock_fetch(symbol: str) -> pd.DataFrame:
        call_count["n"] += 1
        return pd.DataFrame({"symbol": [symbol], "value": [42]})

    r1 = mock_fetch("600519")
    r2 = mock_fetch("600519")
    r3 = mock_fetch("000858")

    assert call_count["n"] == 2  # 600519 命中缓存不重复调用；000858 是新参数
    assert r1.equals(r2)
    assert r3.iloc[0]["symbol"] == "000858"


def test_clear_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    @cached("clear_ns")
    def f(x: int) -> pd.DataFrame:
        return pd.DataFrame({"x": [x]})

    for i in range(3):
        f(i)

    n = clear_cache("clear_ns")
    assert n == 3


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
