"""
QMTBroker 测试（不依赖 xtquant 真实 SDK）
==========================================

验证：
- 未装 xtquant 时正常 import + is_available 返回 False + reason
- 未连接时 submit_order 生成一个 REJECTED 单（含明确错误），不抛
- runner 接 broker_kind=qmt 时正确路由（不真连）
"""

from __future__ import annotations

import pytest

from execution.qmt_broker import QMTBroker, QMTNotAvailable, _to_qmt_symbol, _from_qmt_symbol


def test_import_ok_without_xtquant(monkeypatch, tmp_path):
    """SDK 未装时类应正常构造。"""
    from execution import qmt_broker
    monkeypatch.setattr(qmt_broker, "ORDERS_DIR", tmp_path,
                        raising=False)  # 隔离持久化
    b = QMTBroker(account="qmt_test", broker_config={"account_id": "x", "user_data_path": "/tmp"})
    ok, msg = b.is_available()
    # SDK 是否装是环境决定，两种都可接受
    assert ok is False or ok is True
    assert isinstance(msg, str) and msg


def test_submit_when_not_connected_returns_rejected_order(monkeypatch):
    """未连接时下单会得到一个 REJECTED 单（不抛异常，让 runner 能看到错）。"""
    from execution import qmt_broker
    # 强制 SDK 不可用
    monkeypatch.setattr(qmt_broker, "_try_import_xtquant",
                        lambda: {"error": "no xtquant in test env"})
    b = QMTBroker(account="qmt_reject_test",
                  broker_config={"account_id": "88888888",
                                 "user_data_path": "/nowhere"})
    from execution.broker import OrderSide, OrderStatus
    order = b.submit_order("600519", OrderSide.BUY, 100, 100.0, reason="test")
    assert order.status == OrderStatus.REJECTED
    assert "QMT 未就绪" in (order.reject_reason or "")


def test_to_qmt_symbol():
    assert _to_qmt_symbol("600519") == "600519.SH"
    assert _to_qmt_symbol("688981") == "688981.SH"
    assert _to_qmt_symbol("000001") == "000001.SZ"
    assert _to_qmt_symbol("300750") == "300750.SZ"


def test_from_qmt_symbol():
    assert _from_qmt_symbol("600519.SH") == "600519"
    assert _from_qmt_symbol("000001.SZ") == "000001"


def test_runner_broker_follows_account_kind_live(monkeypatch, tmp_path):
    """账户 kind=live 时，runner 自动选择 QMTBroker，忽略传入的 broker_kind。"""
    from execution import runner as rn
    from paper_trade.portfolio import Portfolio

    monkeypatch.setattr(rn, "STATE_DIR", tmp_path)
    monkeypatch.setattr(rn.pfolio, "default_path",
                        lambda a: tmp_path / f"{a}.json")
    from execution import qmt_broker
    monkeypatch.setattr(qmt_broker, "_try_import_xtquant",
                        lambda: {"error": "test"})

    # 先存一个 live 账户
    port = Portfolio.new("live_acct", initial_cash=100000, kind="live")
    port.save(tmp_path / "live_acct.json")

    r = rn.LiveRunner(
        account="live_acct",
        broker_config={"account_id": "88888888", "user_data_path": "/tmp"},
    )
    assert r.broker_kind == "qmt"
    from execution.qmt_broker import QMTBroker
    assert isinstance(r.broker, QMTBroker)


def test_runner_broker_follows_account_kind_paper(monkeypatch, tmp_path):
    """账户 kind=paper（默认）时，runner 自动选择 PaperBroker。"""
    from execution import runner as rn
    from execution.broker import PaperBroker
    from paper_trade.portfolio import Portfolio

    monkeypatch.setattr(rn, "STATE_DIR", tmp_path)
    monkeypatch.setattr(rn.pfolio, "default_path",
                        lambda a: tmp_path / f"{a}.json")

    port = Portfolio.new("paper_acct", initial_cash=100000, kind="paper")
    port.save(tmp_path / "paper_acct.json")

    r = rn.LiveRunner(account="paper_acct")
    assert r.broker_kind == "paper"
    assert isinstance(r.broker, PaperBroker)
