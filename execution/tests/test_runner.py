"""
LiveRunner 测试
================

不启动真实网络 / 线程，只验证时段判定 + tick 静默逻辑 + 状态持久化。
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from execution import runner as rn


@pytest.fixture(autouse=True)
def isolate_state_dir(tmp_path, monkeypatch):
    d = tmp_path / "live_runner"
    d.mkdir()
    monkeypatch.setattr(rn, "STATE_DIR", d)
    return d


def test_is_trading_hours_weekend():
    # 周六
    assert rn.is_trading_hours(datetime(2026, 8, 1, 10, 30)) is False
    # 周日
    assert rn.is_trading_hours(datetime(2026, 8, 2, 10, 30)) is False


def test_is_trading_hours_morning():
    # 2026-07-31 是周五
    assert rn.is_trading_hours(datetime(2026, 7, 31, 10, 30)) is True
    assert rn.is_trading_hours(datetime(2026, 7, 31, 9, 29)) is False   # 开盘前
    assert rn.is_trading_hours(datetime(2026, 7, 31, 11, 31)) is False  # 午休


def test_is_trading_hours_afternoon():
    assert rn.is_trading_hours(datetime(2026, 7, 31, 13, 0)) is True
    assert rn.is_trading_hours(datetime(2026, 7, 31, 15, 0)) is True
    assert rn.is_trading_hours(datetime(2026, 7, 31, 15, 1)) is False


def test_tick_skipped_outside_hours(monkeypatch, tmp_path):
    """非交易时段调 _tick_once 不应发快照请求。"""
    monkeypatch.setattr(rn, "is_trading_hours", lambda now=None: False)
    called = {"n": 0}
    def fake_snap():
        called["n"] += 1
        return pd.DataFrame()
    from data_layer import market
    monkeypatch.setattr(market, "snapshot", fake_snap)

    from paper_trade.portfolio import default_path
    monkeypatch.setattr("paper_trade.portfolio.default_path",
                        lambda a: tmp_path / f"{a}.json")

    runner = rn.LiveRunner(account="test_skip", tick_seconds=5)
    runner._tick_once()
    assert called["n"] == 0


def test_state_load_after_save(isolate_state_dir):
    s = rn.RunnerState(account="persist_test", status="running",
                       started_at="2026-07-31T09:31:00", ticks_count=5)
    s.save()
    loaded = rn.RunnerState.load("persist_test")
    assert loaded is not None
    assert loaded.status == "running"
    assert loaded.ticks_count == 5


def test_state_load_missing_returns_none(isolate_state_dir):
    assert rn.RunnerState.load("never_created") is None
