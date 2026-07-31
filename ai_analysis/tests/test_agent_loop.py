"""
agent_loop 测试
===============

不启动真实 LLM。mock 掉 chat 和实际 backtest engine，只验证：
- 决策 → 执行 → 保存日志的完整循环
- 上限强制中断
- LLM 返回未知 action / 非法 JSON 的容错
- 任务持久化 + 加载
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from ai_analysis import agent_loop


@pytest.fixture(autouse=True)
def isolate_tasks_dir(tmp_path, monkeypatch):
    """把任务写入目录换成 tmp，避免污染真实 logs/。"""
    d = tmp_path / "agent_tasks"
    d.mkdir()
    monkeypatch.setattr(agent_loop, "TASKS_DIR", d)
    return d


def _run_sync(task):
    """本地版：不用线程，直接跑 _run_loop 便于断言。"""
    agent_loop._run_loop(task)


def _stub_provider(monkeypatch):
    monkeypatch.setattr(agent_loop, "current_provider", lambda: "claude")


def test_extract_json_handles_code_block():
    r = agent_loop._extract_json('```json\n{"a": 1}\n```')
    assert r == {"a": 1}


def test_finish_terminates_loop(monkeypatch):
    """LLM 一上来就 finish，应立刻停止。"""
    _stub_provider(monkeypatch)
    decisions = iter([
        {"action": "finish", "reason": "已达成", "args": {
            "best": {"strategy": "swing_v1", "metrics": {"cumulative_return": 1.0}},
            "summary": "找到了",
        }}
    ])
    monkeypatch.setattr(agent_loop, "_ask_llm", lambda t: next(decisions))
    task = agent_loop.AgentTask(
        task_id="test1", goal="示例", max_iterations=5,
        started_at="now", provider="claude",
    )
    task.save()
    _run_sync(task)
    assert task.status == "done"
    assert len(task.steps) == 1
    assert task.final["summary"] == "找到了"


def test_max_iterations_forced_stop(monkeypatch):
    """LLM 永远不 finish，应到达上限强制结束。"""
    _stub_provider(monkeypatch)
    # 反复 list_strategies
    monkeypatch.setattr(agent_loop, "_ask_llm",
                        lambda t: {"action": "list_strategies", "reason": "repeat", "args": {}})
    # 别真的去列策略
    monkeypatch.setitem(agent_loop.ACTIONS, "list_strategies",
                        lambda args: {"strategies": []})
    task = agent_loop.AgentTask(
        task_id="test2", goal="不 finish", max_iterations=3,
        started_at="now", provider="claude",
    )
    _run_sync(task)
    assert task.status == "done"
    assert len(task.steps) == 3
    assert "到达最大轮数" in task.final["summary"]


def test_unknown_action_recorded_as_error(monkeypatch):
    """LLM 输出未知 action 应记为 error，不打断循环。"""
    _stub_provider(monkeypatch)
    decisions = iter([
        {"action": "nonsense", "reason": "?", "args": {}},
        {"action": "finish", "reason": "算了", "args": {"summary": "放弃"}},
    ])
    monkeypatch.setattr(agent_loop, "_ask_llm", lambda t: next(decisions))
    task = agent_loop.AgentTask(
        task_id="test3", goal="示例", max_iterations=5,
        started_at="now", provider="claude",
    )
    _run_sync(task)
    assert task.status == "done"
    assert task.steps[0].error and "未知 action" in task.steps[0].error
    assert task.steps[1].action == "finish"


def test_llm_bad_json_marks_failed(monkeypatch):
    _stub_provider(monkeypatch)
    def bad_llm(t): raise ValueError("LLM 返回不是合法 JSON")
    monkeypatch.setattr(agent_loop, "_ask_llm", bad_llm)
    task = agent_loop.AgentTask(
        task_id="test4", goal="?", max_iterations=3,
        started_at="now", provider="claude",
    )
    _run_sync(task)
    assert task.status == "failed"
    assert "LLM 决策失败" in task.error


def test_backtest_action_error_recorded(monkeypatch):
    """action 执行出错 → step.error，循环继续。"""
    _stub_provider(monkeypatch)
    decisions = iter([
        {"action": "backtest_score", "reason": "试试", "args": {
            "start": "2024-01-01", "end": "2024-06-30",
            "pool": "000300", "limit": 5, "preset": "balanced",
        }},
        {"action": "finish", "reason": "结束", "args": {"summary": "回测失败了，只能作罢"}},
    ])
    monkeypatch.setattr(agent_loop, "_ask_llm", lambda t: next(decisions))
    def failing(args): raise RuntimeError("simulated failure")
    monkeypatch.setitem(agent_loop.ACTIONS, "backtest_score", failing)
    task = agent_loop.AgentTask(
        task_id="test5", goal="?", max_iterations=5,
        started_at="now", provider="claude",
    )
    _run_sync(task)
    assert task.status == "done"
    assert task.steps[0].error and "simulated failure" in task.steps[0].error
    assert task.steps[1].action == "finish"


def test_task_persistence_and_load(monkeypatch):
    _stub_provider(monkeypatch)
    monkeypatch.setattr(agent_loop, "_ask_llm",
                        lambda t: {"action": "finish", "reason": "ok",
                                   "args": {"summary": "s"}})
    task = agent_loop.AgentTask(
        task_id="persist1", goal="?", max_iterations=2,
        started_at="now", provider="claude",
    )
    _run_sync(task)
    reloaded = agent_loop.AgentTask.load("persist1")
    assert reloaded is not None
    assert reloaded.status == "done"
    assert len(reloaded.steps) == 1


def test_stub_provider_returns_deterministic(monkeypatch):
    """无 LLM key 时 _ask_llm 走 stub 兜底：第一轮回测，第二轮 finish。"""
    monkeypatch.setattr(agent_loop, "current_provider", lambda: "stub")
    # 不真的跑回测，mock 掉
    monkeypatch.setitem(agent_loop.ACTIONS, "backtest_score",
                        lambda args: {"metrics": {"cumulative_return": 0.1},
                                      "trades_count": 3, "config": args})
    task = agent_loop.AgentTask(
        task_id="stub1", goal="?", max_iterations=3,
        started_at="now", provider="stub",
    )
    _run_sync(task)
    assert task.status == "done"
    assert task.steps[0].action == "backtest_score"
    assert task.steps[1].action == "finish"


def test_list_tasks_returns_recent(monkeypatch, isolate_tasks_dir):
    _stub_provider(monkeypatch)
    monkeypatch.setattr(agent_loop, "_ask_llm",
                        lambda t: {"action": "finish", "args": {"summary": "s"}, "reason": ""})
    for i in range(3):
        t = agent_loop.AgentTask(
            task_id=f"list{i}", goal=f"goal{i}", max_iterations=2,
            started_at="now", provider="claude",
        )
        _run_sync(t)
    tasks = agent_loop.list_tasks(limit=10)
    ids = {t["task_id"] for t in tasks}
    assert ids >= {"list0", "list1", "list2"}
