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


def test_extract_json_handles_extra_data_after_object():
    """真实 bug 案例：完整 JSON 后又跟了散文 → json.loads 报 Extra data。"""
    raw = ('```json\n{"action": "backtest_technical", "args": {"start": "2024-01-01"}}\n```\n'
           '上面就是我的决策，希望有用。')
    r = agent_loop._extract_json(raw)
    assert r["action"] == "backtest_technical"


def test_extract_json_handles_two_back_to_back_objects():
    """LLM 偶尔连输两个 JSON —— 只取第一个。"""
    raw = '{"action": "finish", "args": {}}\n{"another": "obj"}'
    r = agent_loop._extract_json(raw)
    assert r["action"] == "finish"


def test_extract_json_handles_preamble_text():
    """前面有介绍语。"""
    raw = '这是我的输出：\n{"action":"backtest_score","args":{}}'
    assert agent_loop._extract_json(raw)["action"] == "backtest_score"


def test_extract_json_rejects_when_no_object():
    import pytest
    with pytest.raises(ValueError):
        agent_loop._extract_json("这里根本没 JSON。")


def test_extract_json_repairs_unescaped_quotes_in_string_value():
    """
    真实案例：summary 里带了未转义的英文双引号
    `"summary": "本轮围绕"昨日涨停"策略进行..."`
    _extract_json 应自动修复并解析成功。
    """
    raw = (
        '```json\n'
        '{"action": "finish", "args": {"summary": "本轮围绕"昨日涨停→高开反包"策略'
        '进行了多轮迭代", "best": {"strategy": "x"}}}\n'
        '```'
    )
    r = agent_loop._extract_json(raw)
    assert r["action"] == "finish"
    assert "本轮围绕" in r["args"]["summary"]
    assert "昨日涨停" in r["args"]["summary"]


def test_extract_json_repairs_multiple_unescaped_quotes():
    raw = '{"a": "他说"你好"", "b": "另一段"引号""}'
    r = agent_loop._extract_json(raw)
    assert r["a"] == '他说"你好"'
    assert r["b"] == '另一段"引号"'


def test_run_loop_retries_llm_on_bad_json(monkeypatch, isolate_tasks_dir):
    """
    LLM 第一次吐脏 JSON 时不应立刻 failed，应自动重试；
    重试成功后任务继续完成，不算失败。
    """
    _stub_provider(monkeypatch)
    calls = {"n": 0}

    def flaky_ask(task, retry_hint=None):
        calls["n"] += 1
        if calls["n"] == 1:
            # 第一次抛脏 JSON 错
            err = ValueError("LLM 返回不是合法 JSON：Expecting delimiter")
            err.raw_reply = 'raw broken'
            raise err
        # 第二次返回合法 finish，任务成功结束
        return {"action": "finish", "reason": "重试后 OK",
                "args": {"summary": "OK"}}, "raw ok"

    monkeypatch.setattr(agent_loop, "_ask_llm", flaky_ask)
    monkeypatch.setattr(agent_loop.time, "sleep", lambda x: None)
    task = agent_loop.AgentTask(
        task_id="self_heal", goal="test", max_iterations=3,
        started_at="now", provider="claude",
    )
    task.save()
    agent_loop._run_loop(task)
    # 未 failed，成功完成
    assert task.status == "done"
    assert calls["n"] == 2  # 一次失败 + 一次成功
    # 最后一步不是 llm_error
    assert task.steps[-1].action == "finish"


def test_run_loop_gives_up_after_max_retries(monkeypatch, isolate_tasks_dir):
    """LLM 连续 3 次都吐脏 JSON 才真正 failed。"""
    _stub_provider(monkeypatch)
    calls = {"n": 0}

    def always_bad(task, retry_hint=None):
        calls["n"] += 1
        err = ValueError("bad json")
        err.raw_reply = "broken"
        raise err

    monkeypatch.setattr(agent_loop, "_ask_llm", always_bad)
    monkeypatch.setattr(agent_loop.time, "sleep", lambda x: None)
    task = agent_loop.AgentTask(
        task_id="give_up", goal="test", max_iterations=3,
        started_at="now", provider="claude",
    )
    task.save()
    agent_loop._run_loop(task)
    assert task.status == "failed"
    # 首次 + 2 次重试 = 3 次调用
    assert calls["n"] == 3
    assert task.steps[-1].action == "llm_error"


def test_llm_error_persists_raw_reply(monkeypatch, isolate_tasks_dir):
    """LLM 返回脏数据时，step.raw_llm 应保留完整原文用于复盘（不只是 200 截断）。"""
    # 让 _ask_llm 抛带 raw_reply 属性的 ValueError
    long_raw = "```json\n{" + '"x":1,' * 200 + '"end":true' + "\n```\n后面还有一堆解释文字" * 50

    def fake_ask(t, retry_hint=None):
        err = ValueError("LLM 返回不是合法 JSON：模拟")
        err.raw_reply = long_raw
        raise err

    monkeypatch.setattr(agent_loop, "_ask_llm", fake_ask)
    # 让重试 sleep 更快，不然测试很慢
    monkeypatch.setattr(agent_loop.time, "sleep", lambda x: None)
    task = agent_loop.AgentTask(
        task_id="rawpersist", goal="x", max_iterations=2,
        started_at="now", provider="claude",
    )
    agent_loop._run_loop(task)
    assert task.status == "failed"
    last = task.steps[-1]
    assert last.action == "llm_error"
    assert last.raw_llm is not None
    # 应存了远超 200 字节的原文（含 3 次尝试的 raw 累积）
    assert len(last.raw_llm) > 500


def test_finish_terminates_loop(monkeypatch):
    """LLM 一上来就 finish，应立刻停止。"""
    _stub_provider(monkeypatch)
    decisions = iter([
        {"action": "finish", "reason": "已达成", "args": {
            "best": {"strategy": "swing_v1", "metrics": {"cumulative_return": 1.0}},
            "summary": "找到了",
        }}
    ])
    monkeypatch.setattr(agent_loop, "_ask_llm", lambda t, retry_hint=None: (next(decisions), "fake raw"))
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
                        lambda t, retry_hint=None: ({"action": "list_strategies", "reason": "repeat", "args": {}}, "fake raw"))
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
    monkeypatch.setattr(agent_loop, "_ask_llm", lambda t, retry_hint=None: (next(decisions), "fake raw"))
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
    def bad_llm(t, retry_hint=None): raise ValueError("LLM 返回不是合法 JSON")
    monkeypatch.setattr(agent_loop, "_ask_llm", bad_llm)
    monkeypatch.setattr(agent_loop.time, "sleep", lambda x: None)
    task = agent_loop.AgentTask(
        task_id="test4", goal="?", max_iterations=3,
        started_at="now", provider="claude",
    )
    _run_sync(task)
    assert task.status == "failed"
    # 3 次重试后仍失败才会有这条错误
    assert "LLM 连续" in task.error or "3 次" in task.error


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
    monkeypatch.setattr(agent_loop, "_ask_llm", lambda t, retry_hint=None: (next(decisions), "fake raw"))
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
                        lambda t, retry_hint=None: ({"action": "finish", "reason": "ok",
                                    "args": {"summary": "s"}}, "fake raw"))
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
                        lambda t, retry_hint=None: ({"action": "finish", "args": {"summary": "s"}, "reason": ""}, "fake raw"))
    for i in range(3):
        t = agent_loop.AgentTask(
            task_id=f"list{i}", goal=f"goal{i}", max_iterations=2,
            started_at="now", provider="claude",
        )
        _run_sync(t)
    tasks = agent_loop.list_tasks(limit=10)
    ids = {t["task_id"] for t in tasks}
    assert ids >= {"list0", "list1", "list2"}
