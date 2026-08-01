"""
Agent 引用旧任务测试
======================

验证：
- reference_ids 字段在 AgentTask 上保留
- render_markdown 会展示引用列表
- _render_reference_summary 能读旧任务并压缩成一段摘要
- LLM 调用前 prompt 里应该拼接了引用块
- 引用不存在的 ID 时 _render_reference_summary 返回警示（不崩）
"""

from __future__ import annotations

import json

import pytest

from ai_analysis import agent_loop


@pytest.fixture(autouse=True)
def isolate_tasks_dir(tmp_path, monkeypatch):
    d = tmp_path / "agent_tasks"
    d.mkdir()
    monkeypatch.setattr(agent_loop, "TASKS_DIR", d)
    return d


def _make_task(**kw):
    return agent_loop.AgentTask(
        task_id=kw.get("task_id", "t1"),
        goal=kw.get("goal", "找一个策略"),
        max_iterations=kw.get("max_iterations", 5),
        started_at="2026-08-01T00:00:00",
        provider="claude",
        status=kw.get("status", "running"),
        reference_ids=kw.get("reference_ids", []),
    )


def _make_finished_task_with_backtest(task_id: str, cum_ret=0.15):
    t = _make_task(task_id=task_id, status="done")
    t.finished_at = "2026-08-01T00:10:00"
    t.steps.append(agent_loop.Step(
        idx=1, at="2026-08-01T00:01:00", action="backtest_technical",
        args={}, reason="试试均线交叉", phase="done", duration_ms=15000,
        result={
            "metrics": {"cumulative_return": cum_ret, "annualized_return": 0.30,
                        "max_drawdown": 0.08, "sharpe": 1.2},
            "trades_count": 42,
            "config": {"strategy_id": "ma_cross", "pool": "000300", "limit": 20,
                       "start": "2024-01-01", "end": "2024-06-30"},
        },
    ))
    t.final = {
        "summary": "均线交叉在沪深 300 表现不错",
        "best": {"strategy": "ma_cross", "params": {"fast": 5, "slow": 20}},
    }
    t.save()
    return t


def test_reference_ids_persisted():
    t = _make_task(task_id="reftask", reference_ids=["abc123", "def456"])
    t.save()
    reloaded = agent_loop.AgentTask.load("reftask")
    assert reloaded.reference_ids == ["abc123", "def456"]


def test_render_markdown_shows_references():
    t = _make_task(task_id="mdrefs", reference_ids=["old_a", "old_b"])
    md = t.render_markdown()
    assert "引用参考任务" in md
    assert "`old_a`" in md and "`old_b`" in md


def test_render_reference_summary_captures_metrics():
    _make_finished_task_with_backtest("old_task_1")
    summary = agent_loop._render_reference_summary("old_task_1")
    assert "old_task_1" in summary
    assert "15.0%" in summary          # cumulative_return
    assert "ma_cross" in summary       # config
    assert "均线交叉" in summary        # final summary
    assert "找一个策略" in summary       # original goal


def test_render_reference_summary_missing_task():
    """引用了不存在的 ID：返回警示但不抛。"""
    s = agent_loop._render_reference_summary("noexist")
    assert "不存在" in s


def test_render_reference_block_empty_ids():
    assert agent_loop._render_reference_block([]) == ""


def test_render_reference_block_multiple():
    _make_finished_task_with_backtest("ref_x", cum_ret=0.05)
    _make_finished_task_with_backtest("ref_y", cum_ret=0.20)
    block = agent_loop._render_reference_block(["ref_x", "ref_y"])
    assert "参考此前的实验结果" in block
    assert "ref_x" in block and "ref_y" in block
    assert "5.0%" in block and "20.0%" in block


def test_prompt_contains_references_when_asking_llm(monkeypatch):
    """
    最关键的测试：验证 _ask_llm 在有 reference_ids 时会把引用注入 prompt。
    """
    _make_finished_task_with_backtest("history_task", cum_ret=0.15)
    monkeypatch.setattr(agent_loop, "current_provider", lambda: "claude")

    captured = {}
    def fake_chat(prompt, **kw):
        captured["prompt"] = prompt
        return json.dumps({"action": "finish", "reason": "done",
                           "args": {"summary": "ok"}})
    monkeypatch.setattr(agent_loop, "chat", fake_chat)

    t = _make_task(task_id="new_task", reference_ids=["history_task"])
    t.save()
    agent_loop._ask_llm(t)

    assert "参考此前的实验结果" in captured["prompt"]
    assert "history_task" in captured["prompt"]
    assert "15.0%" in captured["prompt"], "旧任务的回测指标应进 prompt"
    assert "ma_cross" in captured["prompt"]


def test_prompt_no_reference_block_when_empty(monkeypatch):
    """没有 reference_ids 时 prompt 里不应出现引用块。"""
    monkeypatch.setattr(agent_loop, "current_provider", lambda: "claude")
    captured = {}
    monkeypatch.setattr(agent_loop, "chat",
                        lambda prompt, **kw: (
                            captured.setdefault("prompt", prompt),
                            json.dumps({"action": "finish", "reason": "",
                                        "args": {"summary": "s"}}),
                        )[1])

    t = _make_task(task_id="notask", reference_ids=[])
    agent_loop._ask_llm(t)
    assert "参考此前的实验结果" not in captured["prompt"]


def test_start_agent_accepts_reference_ids(monkeypatch):
    """确保 start_agent 会把 reference_ids 塞进任务。"""
    # 不真的启动线程：把 Thread 拦下来
    monkeypatch.setattr(agent_loop, "Thread",
                        lambda **kw: type("T", (), {"start": lambda self: None})())
    monkeypatch.setattr(agent_loop, "current_provider", lambda: "stub")

    t = agent_loop.start_agent("goal", max_iterations=3,
                               reference_ids=["r1", "  r2  ", "", "r3"])
    # 空字符串被过滤，两端空格被 strip
    assert t.reference_ids == ["r1", "r2", "r3"]
