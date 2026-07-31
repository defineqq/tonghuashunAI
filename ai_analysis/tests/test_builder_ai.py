"""
builder_ai：中文描述 → 策略 JSON
================================

不依赖真实 LLM。分两类测试：
1. stub 分支：没有 API key 时应返回合法 spec
2. mock LLM：给一段假的 JSON 回复，验证抽取、校验、id 兜底
"""

from __future__ import annotations

import json
import os

import pytest

from ai_analysis import builder_ai
from strategies.builder import validate_spec


def _clear_llm_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "stub")


def test_stub_returns_valid_spec(monkeypatch):
    _clear_llm_env(monkeypatch)
    r = builder_ai.generate_spec("随便一句：MA 金叉就买", suggested_id="stub_test")
    assert r["provider"] == "stub"
    spec = r["spec"]
    ok, err = validate_spec(spec)
    assert ok, err
    assert spec["id"] == "stub_test"


def test_empty_prompt_raises(monkeypatch):
    _clear_llm_env(monkeypatch)
    with pytest.raises(ValueError):
        builder_ai.generate_spec("   ")


def test_extract_json_handles_markdown_block():
    """LLM 常把 JSON 包在 ```json``` 里，得能剥出来。"""
    raw = '```json\n{"a":1,"b":[1,2,3]}\n```'
    assert builder_ai._extract_json(raw) == {"a": 1, "b": [1, 2, 3]}


def test_extract_json_handles_extra_text():
    raw = '这是我的输出：\n{"a":1}\n上面就是 JSON'
    assert builder_ai._extract_json(raw) == {"a": 1}


def test_llm_mock_end_to_end(monkeypatch):
    """把 chat 换成假的，验证完整链路 + 校验通过。"""
    fake_spec = {
        "id": "ma_cross_ai",
        "name": "AI 生成 · 均线金叉",
        "description": "MA 金叉买入",
        "buy": {
            "logic": "AND",
            "rules": [
                {"indicator": "MA", "op": "cross_up", "params": {"fast": 5, "slow": 20}},
                {"indicator": "VOLUME", "op": "surge", "params": {"n": 20}, "value": 1.5},
            ],
        },
        "sell": {
            "logic": "OR",
            "rules": [
                {"indicator": "MA", "op": "cross_down", "params": {"fast": 5, "slow": 20}},
            ],
        },
        "notes": "示例",
    }
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")  # 让 current_provider 不走 stub
    monkeypatch.setattr(builder_ai, "current_provider", lambda: "claude")
    monkeypatch.setattr(builder_ai, "chat", lambda *a, **kw: json.dumps(fake_spec))

    r = builder_ai.generate_spec("5 日线金叉 20 日线且放量 1.5 倍买，死叉卖")
    assert r["provider"] == "claude"
    assert r["spec"]["id"] == "ma_cross_ai"
    ok, err = validate_spec(r["spec"])
    assert ok, err


def test_llm_mock_bad_indicator_rejected(monkeypatch):
    bad_spec = {
        "id": "bad", "name": "bad",
        "buy":  {"logic": "AND", "rules": [{"indicator": "NOT_EXIST", "op": "x"}]},
        "sell": {"logic": "OR",  "rules": [{"indicator": "MA", "op": "cross_down"}]},
    }
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(builder_ai, "current_provider", lambda: "claude")
    monkeypatch.setattr(builder_ai, "chat", lambda *a, **kw: json.dumps(bad_spec))

    with pytest.raises(ValueError, match="校验"):
        builder_ai.generate_spec("随便啥")


def test_llm_mock_missing_id_filled(monkeypatch):
    """LLM 忘了 id，应该用 suggested_id 兜底。"""
    spec = {
        "name": "无 ID 的策略",
        "buy":  {"logic": "AND", "rules": [{"indicator": "MA", "op": "cross_up"}]},
        "sell": {"logic": "OR",  "rules": [{"indicator": "MA", "op": "cross_down"}]},
    }
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(builder_ai, "current_provider", lambda: "claude")
    monkeypatch.setattr(builder_ai, "chat", lambda *a, **kw: json.dumps(spec))

    r = builder_ai.generate_spec("MA 金叉", suggested_id="my_backup_id")
    assert r["spec"]["id"] == "my_backup_id"


def test_render_catalog_covers_all_indicators():
    """prompt 里必须列出所有指标，不然 LLM 会瞎编。"""
    from strategies.builder import INDICATORS
    text = builder_ai._render_indicator_catalog()
    for k in INDICATORS:
        assert f"### {k}" in text, f"catalog missing indicator {k}"
