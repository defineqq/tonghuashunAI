"""
notify.dispatch 的单元测试（不需要真发消息）
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from notify import dispatch  # noqa: E402


def test_no_config_returns_all_none(monkeypatch):
    for k in ("FEISHU_WEBHOOK", "DINGTALK_WEBHOOK", "WECHAT_WEBHOOK", "SMTP_HOST", "SMTP_USER", "SMTP_PASS", "SMTP_TO"):
        monkeypatch.delenv(k, raising=False)
    r = dispatch.notify("t", "x")
    assert r == {"feishu": None, "dingtalk": None, "wechat": None, "email": None}


def test_summary_line_mixed():
    r = {"feishu": True, "dingtalk": False, "wechat": None, "email": True}
    s = dispatch.summary_line(r)
    assert "feishu:✓" in s
    assert "dingtalk:✗" in s
    assert "wechat:未配置" in s
    assert "email:✓" in s


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
