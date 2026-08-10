"""
Portfolio.kind 字段测试
========================

- 默认 paper
- 显式 live
- 老账户（无 kind 字段）读盘视为 paper
- 非法 kind 报错
"""

from __future__ import annotations

import json

import pytest

from paper_trade.portfolio import Portfolio


def test_default_kind_is_paper():
    p = Portfolio.new("t1")
    assert p.kind == "paper"


def test_explicit_live_kind():
    p = Portfolio.new("t2", kind="live")
    assert p.kind == "live"


def test_invalid_kind_raises():
    with pytest.raises(ValueError):
        Portfolio.new("t3", kind="foo")


def test_old_json_without_kind_defaults_to_paper(tmp_path):
    """兼容老账户 JSON 里没有 kind 字段的情况。"""
    p = tmp_path / "old.json"
    p.write_text(json.dumps({
        "account_id": "legacy",
        "initial_cash": 100000,
        "cash": 100000,
        "positions": {},
        "trades": [],
        "daily_snapshots": [],
    }), encoding="utf-8")
    port = Portfolio.load(p)
    assert port.kind == "paper"


def test_roundtrip_preserves_kind(tmp_path):
    p1 = Portfolio.new("rt", kind="live")
    fp = tmp_path / "rt.json"
    p1.save(fp)
    p2 = Portfolio.load(fp)
    assert p2.kind == "live"
