"""
PaperBroker 撮合测试
====================

验证限价撮合、资金/持仓校验、状态机、持久化。
"""

from __future__ import annotations

import pytest

from execution.broker import (
    ORDERS_DIR, Order, OrderSide, OrderStatus, PaperBroker,
)
from paper_trade.portfolio import Portfolio


@pytest.fixture(autouse=True)
def isolate_orders_dir(tmp_path, monkeypatch):
    d = tmp_path / "live_orders"
    d.mkdir()
    from execution import broker as bmod
    monkeypatch.setattr(bmod, "ORDERS_DIR", d)
    return d


def _new_broker(cash: float = 100_000) -> PaperBroker:
    return PaperBroker(Portfolio.new("test_acct", initial_cash=cash), account="test_acct")


def test_buy_at_limit_fills_when_market_below_limit():
    br = _new_broker()
    o = br.submit_order("600519", OrderSide.BUY, 100, limit_price=150.0, reason="test")
    assert o.status == OrderStatus.PENDING

    changed = br.on_tick({"600519": 149.0})   # 市价 1490 <= 限价 1500 → 应成交
    assert len(changed) == 1
    assert changed[0].status == OrderStatus.FILLED
    assert changed[0].filled_shares == 100
    # 现金扣掉了成交金额 + 手续费
    assert br.portfolio.cash < 100_000 - 100 * 149


def test_buy_stays_pending_when_market_above_limit():
    br = _new_broker()
    o = br.submit_order("600519", OrderSide.BUY, 100, limit_price=150.0)
    br.on_tick({"600519": 160.0})   # 市价 160 > 限价 150 → 不成交
    assert br.orders[o.order_id].status == OrderStatus.PENDING


def test_sell_fills_when_market_above_limit():
    br = _new_broker()
    # 先造出持仓
    br.submit_order("600519", OrderSide.BUY, 100, limit_price=150.0)
    br.on_tick({"600519": 149.0})
    # 卖
    o = br.submit_order("600519", OrderSide.SELL, 100, limit_price=150.0)
    br.on_tick({"600519": 152.0})
    assert br.orders[o.order_id].status == OrderStatus.FILLED
    assert "600519" not in br.portfolio.positions


def test_reject_when_cash_insufficient():
    br = _new_broker(cash=5000)
    br.submit_order("600519", OrderSide.BUY, 100, limit_price=100.0)  # 需 1 万
    changed = br.on_tick({"600519": 99.0})
    assert changed[0].status == OrderStatus.REJECTED
    assert "资金不足" in changed[0].reject_reason


def test_reject_sell_when_no_position():
    br = _new_broker()
    br.submit_order("600519", OrderSide.SELL, 100, limit_price=150.0)
    changed = br.on_tick({"600519": 160.0})
    assert changed[0].status == OrderStatus.REJECTED
    assert "持仓不足" in changed[0].reject_reason


def test_shares_rounded_to_lot():
    br = _new_broker()
    o = br.submit_order("600519", OrderSide.BUY, 150, limit_price=100.0)
    # _round_lot 会把 150 → 100 或 200，具体依赖实现，只要是 100 的倍数即可
    assert o.shares % 100 == 0


def test_cancel_pending_order():
    br = _new_broker()
    o = br.submit_order("600519", OrderSide.BUY, 100, limit_price=150.0)
    assert br.cancel_order(o.order_id) is True
    assert br.orders[o.order_id].status == OrderStatus.CANCELLED


def test_cannot_cancel_finished_order():
    br = _new_broker()
    o = br.submit_order("600519", OrderSide.BUY, 100, limit_price=150.0)
    br.on_tick({"600519": 149.0})   # 成交
    assert br.cancel_order(o.order_id) is False


def test_orders_persist_across_broker_instances():
    br = _new_broker()
    o = br.submit_order("600519", OrderSide.BUY, 100, limit_price=150.0)
    br2 = PaperBroker(br.portfolio, account="test_acct")
    assert o.order_id in br2.orders
    assert br2.orders[o.order_id].status == OrderStatus.PENDING


def test_shares_zero_rejected():
    br = _new_broker()
    o = br.submit_order("600519", OrderSide.BUY, 50, limit_price=150.0)
    # 50 股被 round_lot 变成 0（一手 100 股为最小单位）
    assert o.status == OrderStatus.REJECTED
    assert "shares" in (o.reject_reason or "")
