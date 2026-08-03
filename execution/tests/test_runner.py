"""
LiveRunner 测试
================

不启动真实网络 / 线程，只验证时段判定 + tick 静默逻辑 + 状态持久化。
"""

from __future__ import annotations

import json
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


def test_update_runner_hot_switches_strategy(monkeypatch):
    """update_runner 应在不停线程的前提下改内存里的策略/池子/tick。"""
    runner = rn.LiveRunner(account="hot_swap", strategy_id="old", tick_seconds=15)
    # 手动注册到 _RUNNERS 里（不真的启动线程）
    rn._RUNNERS["hot_swap"] = runner

    r = rn.update_runner("hot_swap", strategy_id="new_strategy",
                          watch_symbols=["600519"], tick_seconds=30)
    assert r is not None
    assert runner.strategy_id == "new_strategy"
    assert runner.watch_symbols == ["600519"]
    assert runner.tick_seconds == 30
    # state 也同步了
    assert runner.state.strategy_id == "new_strategy"
    assert runner.state.tick_seconds == 30

    # 清理注册表，避免影响其它测试
    rn._RUNNERS.pop("hot_swap", None)


def test_update_nonexistent_runner_returns_none():
    assert rn.update_runner("never_started_acct", strategy_id="foo") is None


def test_update_empty_strategy_clears_it(monkeypatch):
    """传空串 strategy_id 表示"清空策略、只跑手动下单"。"""
    runner = rn.LiveRunner(account="clear_strat", strategy_id="foo")
    rn._RUNNERS["clear_strat"] = runner

    rn.update_runner("clear_strat", strategy_id="")
    assert runner.strategy_id is None
    rn._RUNNERS.pop("clear_strat", None)


def test_resume_runners_picks_up_running_state(isolate_state_dir, monkeypatch):
    """resume_runners 应扫描 state 文件，把 status=running 的重新拉起。"""
    # 造两条 state：一 running 一 stopped
    (isolate_state_dir / "resume_me.json").write_text(json.dumps({
        "account": "resume_me", "status": "running",
        "started_at": "2026-08-01T09:31:00",
        "watch_symbols": ["600519"],
        "strategy_id": "ma_cross",
        "strategy_params": {},
        "tick_seconds": 20,
    }, ensure_ascii=False))
    (isolate_state_dir / "skip_me.json").write_text(json.dumps({
        "account": "skip_me", "status": "stopped",
        "started_at": "2026-08-01T09:31:00",
    }, ensure_ascii=False))

    # mock start_runner 只登记不真启动
    called = {}
    def fake_start(account, **kwargs):
        called[account] = kwargs
        # 返回一个假 runner
        class F: pass
        return F()
    monkeypatch.setattr(rn, "start_runner", fake_start)

    resumed = rn.resume_runners()
    assert resumed == ["resume_me"]
    assert called["resume_me"]["strategy_id"] == "ma_cross"
    assert called["resume_me"]["tick_seconds"] == 20
    assert called["resume_me"]["watch_symbols"] == ["600519"]
