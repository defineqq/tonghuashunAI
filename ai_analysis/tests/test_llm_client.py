"""
llm_client.py 的单测（不需要真实 API key，全部走 stub 分支）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ai_analysis.llm_client import chat, _resolve_provider, is_configured, current_provider  # noqa: E402


def test_stub_when_no_keys(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    assert _resolve_provider("auto") == "stub"
    assert not is_configured()
    resp = chat("hello")
    assert "stub" in resp.lower()


def test_stub_json_mode(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    resp = chat("给我一个 0-100 的评分", json_mode=True)
    data = json.loads(resp)
    assert 0 <= data["score"] <= 100
    assert data["sentiment"] == "neutral"


def test_auto_prefers_claude(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake")
    assert _resolve_provider("auto") == "claude"


def test_explicit_provider_overrides_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    assert _resolve_provider("auto") == "openai"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
