"""
backtest.tasks 测试
====================

验证任务化包装：进度回调、取消、失败、持久化 + 加载。
不真的启动线程，直接跑 _run_task。
"""

from __future__ import annotations

import time

import pytest

from backtest import tasks as bt_tasks


@pytest.fixture(autouse=True)
def isolate_dir(tmp_path, monkeypatch):
    d = tmp_path / "backtest_tasks"
    d.mkdir()
    monkeypatch.setattr(bt_tasks, "TASKS_DIR", d)
    return d


def test_run_task_success_captures_result():
    task = bt_tasks.BacktestTask(
        task_id="ok1", label="示例", request={},
        started_at="now",
    )
    task.save()
    def fn(cb):
        cb(1, 3, "2024-01-01")
        cb(3, 3, "2024-01-03")
        return {"metrics": {"cumulative_return": 0.1}, "trades_count": 2}
    bt_tasks._run_task(task, fn)
    assert task.status == "done"
    assert task.result["metrics"]["cumulative_return"] == 0.1
    assert task.progress["done"] == 3


def test_run_task_failure_records_error():
    task = bt_tasks.BacktestTask(
        task_id="fail1", label="示例", request={}, started_at="now",
    )
    task.save()
    def fn(cb): raise RuntimeError("boom")
    bt_tasks._run_task(task, fn)
    assert task.status == "failed"
    assert "boom" in task.error


def test_cancel_during_run():
    """引擎在进度回调里检测到 cancelled 会抛 BacktestCancelled → 状态置 cancelled。"""
    task = bt_tasks.BacktestTask(
        task_id="cancel1", label="示例", request={}, started_at="now",
    )
    task.save()

    def fn(cb):
        cb(1, 10, "2024-01-01")
        # 模拟外部 cancel：写回磁盘
        bt_tasks.cancel_task("cancel1")
        cb(2, 10, "2024-01-02")   # 这里应该抛
        return {"unreached": True}

    bt_tasks._run_task(task, fn)
    assert task.status == "cancelled"


def test_cancel_before_run_no_op_on_done():
    """已完成任务再取消不会改变 done 状态。"""
    task = bt_tasks.BacktestTask(
        task_id="done1", label="示例", request={}, started_at="now",
        status="done",
    )
    task.save()
    t = bt_tasks.cancel_task("done1")
    assert t.status == "done"


def test_cancel_nonexistent_returns_none():
    assert bt_tasks.cancel_task("nope") is None


def test_load_and_list_persist():
    for i, st in enumerate(["done", "cancelled", "running"]):
        task = bt_tasks.BacktestTask(
            task_id=f"list{i}", label=f"lbl{i}", request={},
            started_at="now", status=st,
            result={"metrics": {"cumulative_return": 0.1 * i,
                                "annualized_return": 0.2 * i,
                                "max_drawdown": 0.05,
                                "sharpe": 1.0 * i}} if st == "done" else None,
        )
        task.save()
        time.sleep(0.01)  # 让 mtime 有差异

    r = bt_tasks.list_tasks(limit=10)
    ids = {t["task_id"] for t in r}
    assert ids >= {"list0", "list1", "list2"}
    # 只有 done 才有 metrics_summary
    done = [t for t in r if t["task_id"] == "list0"][0]
    assert done["metrics_summary"] is not None
    assert done["metrics_summary"]["cumulative_return"] == 0
    running = [t for t in r if t["task_id"] == "list2"][0]
    assert running["metrics_summary"] is None
