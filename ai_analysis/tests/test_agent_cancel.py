"""
Agent 取消 + 恢复相关测试
=========================
"""

from __future__ import annotations

import pytest

from ai_analysis import agent_loop


@pytest.fixture(autouse=True)
def isolate_tasks_dir(tmp_path, monkeypatch):
    d = tmp_path / "agent_tasks"
    d.mkdir()
    monkeypatch.setattr(agent_loop, "TASKS_DIR", d)
    return d


def test_cancel_task_running_flips_status():
    t = agent_loop.AgentTask(
        task_id="cancelrun", goal="test", max_iterations=5,
        started_at="now", provider="claude", status="running",
    )
    t.save()
    r = agent_loop.cancel_task("cancelrun")
    assert r is not None
    assert r.status == "cancelled"
    assert r.finished_at is not None


def test_cancel_task_done_is_noop():
    t = agent_loop.AgentTask(
        task_id="canceldone", goal="test", max_iterations=5,
        started_at="now", provider="claude", status="done",
    )
    t.save()
    r = agent_loop.cancel_task("canceldone")
    assert r.status == "done"


def test_cancel_nonexistent_returns_none():
    assert agent_loop.cancel_task("neverexisted") is None


def test_loop_respects_external_cancel(monkeypatch):
    """在循环中把任务标记为 cancelled，主循环应该在下一轮开头退出。"""
    monkeypatch.setattr(agent_loop, "current_provider", lambda: "claude")

    calls = {"n": 0}
    def fake_ask(t):
        calls["n"] += 1
        # 第 1 轮之后 mark cancelled，第 2 轮不该被调用
        if calls["n"] == 2:
            raise AssertionError("cancel 后不应再问 LLM")
        return {"action": "list_strategies", "reason": "", "args": {}}

    monkeypatch.setattr(agent_loop, "_ask_llm", fake_ask)
    monkeypatch.setitem(agent_loop.ACTIONS, "list_strategies",
                        lambda args: {"strategies": []})

    task = agent_loop.AgentTask(
        task_id="respectcancel", goal="t", max_iterations=5,
        started_at="now", provider="claude",
    )
    task.save()

    # 单线程手动执行 _run_loop，但在第 1 轮结束后从外部 cancel
    # 需要拦一下 save 的时机
    original_save = task.save
    def save_and_maybe_cancel():
        original_save()
        if calls["n"] == 1 and task.status == "running":
            # 模拟外部 cancel（写回磁盘）
            agent_loop.cancel_task("respectcancel")
    task.save = save_and_maybe_cancel  # type: ignore
    agent_loop._run_loop(task)
    assert task.status == "cancelled"
    assert calls["n"] == 1
