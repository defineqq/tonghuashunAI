"""
Markdown 报告 + phase 生命周期测试
==================================
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


def _mk_task(**kw):
    return agent_loop.AgentTask(
        task_id=kw.get("task_id", "t1"),
        goal=kw.get("goal", "示例目标"),
        max_iterations=kw.get("max_iterations", 5),
        started_at="2026-07-31T20:00:00",
        provider="claude",
        status=kw.get("status", "running"),
    )


def test_save_also_writes_markdown(isolate_tasks_dir):
    t = _mk_task(task_id="mdtask")
    t.save()
    md_file = isolate_tasks_dir / "mdtask.md"
    assert md_file.exists(), "save() 应同步写 markdown"
    content = md_file.read_text(encoding="utf-8")
    assert "AI 研究报告" in content
    assert "示例目标" in content


def test_render_markdown_reflects_phases():
    t = _mk_task(task_id="mdphase")
    t.steps.append(agent_loop.Step(
        idx=1, at="2026-07-31T20:01:00", action="thinking",
        args={}, reason="正在向 LLM 请求下一步决策...", phase="thinking",
    ))
    md = t.render_markdown()
    assert "第 1 轮" in md
    assert "正在思考" in md, "phase=thinking 应显示占位 emoji"

    # 转 executing
    t.steps[0].phase = "executing"
    t.steps[0].action = "backtest_score"
    t.steps[0].reason = "试试均衡策略"
    md = t.render_markdown()
    assert "正在执行" in md
    assert "试试均衡策略" in md


def test_render_markdown_shows_backtest_metrics():
    t = _mk_task(task_id="mdbt", status="done")
    t.finished_at = "2026-07-31T20:05:00"
    t.steps.append(agent_loop.Step(
        idx=1, at="2026-07-31T20:01:00", action="backtest_score",
        args={"start": "2024-01-01"}, reason="试试均衡",
        phase="done", duration_ms=12345,
        result={
            "metrics": {"cumulative_return": 0.15, "annualized_return": 0.30,
                        "max_drawdown": 0.08, "sharpe": 1.5},
            "trades_count": 42,
            "config": {"preset": "balanced"},
        },
    ))
    t.final = {"summary": "找到了", "best": {"strategy": "swing_v1_balanced"}}
    md = t.render_markdown()
    assert "15.00%" in md
    assert "夏普：1.50" in md
    assert "找到了" in md
    assert "swing_v1_balanced" in md


def test_render_markdown_with_error():
    t = _mk_task(task_id="mderr", status="failed")
    t.error = "LLM 决策失败：xxx"
    t.steps.append(agent_loop.Step(
        idx=1, at="2026-07-31T20:01:00", action="backtest_score",
        args={"preset": "balanced"}, reason="试试",
        phase="failed", error="RuntimeError: 数据源不可用",
    ))
    md = t.render_markdown()
    assert "错误" in md
    assert "RuntimeError" in md


def test_thinking_placeholder_written_before_llm_returns(monkeypatch, isolate_tasks_dir):
    """
    验证核心用户诉求：在 LLM 还没返回前就能看到"正在思考"步骤。
    做法：mock chat 前先看盘（此时应能读到 phase=thinking 的 step），
    然后让 chat 返回 finish 就退出。
    """
    monkeypatch.setattr(agent_loop, "current_provider", lambda: "claude")

    observed = {"before_llm_had_placeholder": False}

    def fake_chat(prompt, **kw):
        # 此时 _run_loop 应该已经把占位 step 写入磁盘
        reloaded = agent_loop.AgentTask.load("phasetest")
        if reloaded and reloaded.steps and reloaded.steps[0].phase == "thinking":
            observed["before_llm_had_placeholder"] = True
        return json.dumps({"action": "finish", "reason": "done",
                           "args": {"summary": "s"}})

    monkeypatch.setattr(agent_loop, "chat", fake_chat)

    task = _mk_task(task_id="phasetest")
    task.save()
    agent_loop._run_loop(task)

    assert observed["before_llm_had_placeholder"], \
        "LLM 调用前应该已经写入 phase=thinking 的占位 step 到磁盘"
    # 循环结束后最终该 step 应该是 done
    assert task.steps[-1].phase == "done"
    assert task.steps[-1].action == "finish"


def test_llm_error_marks_step_failed(monkeypatch):
    monkeypatch.setattr(agent_loop, "current_provider", lambda: "claude")
    monkeypatch.setattr(agent_loop, "_ask_llm",
                        lambda t: (_ for _ in ()).throw(ValueError("bad json")))
    task = _mk_task(task_id="errphase")
    task.save()
    agent_loop._run_loop(task)
    assert task.status == "failed"
    assert task.steps[-1].phase == "failed"
    assert task.steps[-1].action == "llm_error"
