"""
broker 与 portfolio 的单元测试
============================

用固定的 close_prices dict 模拟行情，不依赖 akshare。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from paper_trade.broker import (  # noqa: E402
    BuySignal, FeeConfig, buy, sell, execute_day, mark_to_market,
)
from paper_trade.portfolio import Portfolio, Position, Trade
from paper_trade.risk import RiskConfig, SellSignal


def test_new_portfolio():
    p = Portfolio.new("test", initial_cash=100_000)
    assert p.cash == 100_000
    assert p.total_value() == 100_000
    assert p.total_pnl_pct() == 0.0
    assert len(p.positions) == 0


def test_buy_basic():
    """一手都买不起时返回 None（50000 元买 1500 元/股，凑不齐 100 股）。"""
    p = Portfolio.new("test", 100_000)
    fee_cfg = FeeConfig()
    t = buy(p, "600519", target_amount=50_000, close_price=1500.0, date="2024-10-01", reason="test", fee_cfg=fee_cfg)
    assert t is None
    assert "600519" not in p.positions

    # 200_000 就够买 100 股茅台
    p2 = Portfolio.new("test", 300_000)
    t2 = buy(p2, "600519", target_amount=200_000, close_price=1500.0, date="2024-10-01", reason="test", fee_cfg=fee_cfg)
    assert t2 is not None
    assert t2.shares == 100
    assert "600519" in p2.positions


def test_buy_lot_size():
    p = Portfolio.new("test", 100_000)
    # 20 元的股票，target 10000 → 大约 500 股 → 整手 500
    t = buy(p, "000001", target_amount=10_000, close_price=20.0, date="2024-10-01", reason="test", fee_cfg=FeeConfig())
    assert t is not None
    assert t.shares % 100 == 0
    assert t.shares >= 400


def test_sell_all():
    p = Portfolio.new("test", 200_000)
    fee_cfg = FeeConfig()
    buy(p, "000001", 50_000, 20.0, "2024-10-01", "buy", fee_cfg)
    cash_before = p.cash
    shares_before = p.positions["000001"].shares
    t = sell(p, "000001", 1.0, 22.0, "2024-10-05", "profit", fee_cfg)
    assert t is not None
    assert t.shares == shares_before
    assert "000001" not in p.positions  # 全平后仓位清空
    assert p.cash > cash_before  # 涨了 10% 卖出应该赚


def test_mark_to_market_updates_pnl():
    p = Portfolio.new("test", 200_000)
    buy(p, "000001", 50_000, 20.0, "2024-10-01", "buy", FeeConfig())
    mark_to_market(p, {"000001": 22.0})
    pos = p.positions["000001"]
    assert pos.last_price == 22.0
    assert pos.unrealized_pnl_pct > 0
    assert p.total_value() > 200_000  # 浮盈使总值上升


def test_execute_day_stop_loss():
    """跌超 5% 应触发止损。"""
    p = Portfolio.new("test", 300_000)
    buy(p, "000001", 100_000, 20.0, "2024-10-01", "buy", FeeConfig())
    # 第二天跌 10%
    result = execute_day(
        p, "2024-10-02",
        close_prices={"000001": 18.0},
        buy_signals=[],
        risk_cfg=RiskConfig(stop_loss_pct=0.05),
    )
    assert len(result["trades"]) == 1
    assert result["trades"][0].side == "sell"
    assert "止损" in result["trades"][0].reason
    assert "000001" not in p.positions


def test_execute_day_take_profit():
    """涨超 15% 应触发止盈减半。"""
    p = Portfolio.new("test", 300_000)
    buy(p, "000001", 100_000, 20.0, "2024-10-01", "buy", FeeConfig())
    orig_shares = p.positions["000001"].shares
    result = execute_day(
        p, "2024-10-02",
        close_prices={"000001": 24.0},  # +20%
        risk_cfg=RiskConfig(take_profit_pct=0.15, take_profit_action="half"),
    )
    assert len(result["trades"]) == 1
    assert result["trades"][0].side == "sell"
    assert "止盈" in result["trades"][0].reason
    # 剩下的约一半
    remaining = p.positions.get("000001")
    assert remaining is not None
    assert remaining.shares == orig_shares - result["trades"][0].shares


def test_execute_day_max_positions_limit():
    """最多同时持有 max_positions 只。"""
    p = Portfolio.new("test", 500_000)
    signals = [
        BuySignal(f"00000{i}", target_pct=0.15) for i in range(1, 6)
    ]
    prices = {f"00000{i}": 20.0 for i in range(1, 6)}
    execute_day(p, "2024-10-01", prices, buy_signals=signals, max_positions=3)
    assert len(p.positions) <= 3


def test_portfolio_serialization(tmp_path):
    p = Portfolio.new("test", 200_000)
    buy(p, "000001", 50_000, 20.0, "2024-10-01", "buy", FeeConfig())
    p.take_snapshot("2024-10-01")
    path = tmp_path / "p.json"
    p.save(path)

    p2 = Portfolio.load(path)
    # JSON 存的是 round(2)，允许 2 分钱以内的误差
    assert abs(p2.cash - p.cash) < 0.01
    assert p2.positions["000001"].shares == p.positions["000001"].shares
    assert len(p2.trades) == 1
    assert len(p2.daily_snapshots) == 1


def test_execute_day_skips_buy_on_limit_up():
    """涨停日买单必须被跳过。"""
    p = Portfolio.new("test", 1_000_000)
    fee_cfg = FeeConfig()
    execute_day(
        p, "2024-01-02",
        close_prices={"600519": 110.0},
        buy_signals=[BuySignal(symbol="600519", target_pct=0.2, reason="try")],
        price_info={"600519": {"close": 110.0, "pct_change": 9.85}},  # 涨停
        fee_cfg=fee_cfg,
    )
    assert "600519" not in p.positions, "涨停日不应买入"
    # 快照仍会记录（只是没成交）
    assert len(p.daily_snapshots) == 1


def test_execute_day_buy_allowed_below_limit_up():
    """非涨停日买单正常成交。"""
    p = Portfolio.new("test", 1_000_000)
    fee_cfg = FeeConfig()
    execute_day(
        p, "2024-01-02",
        close_prices={"600519": 110.0},
        buy_signals=[BuySignal(symbol="600519", target_pct=0.2, reason="try")],
        price_info={"600519": {"close": 110.0, "pct_change": 9.0}},  # 未到涨停
        fee_cfg=fee_cfg,
    )
    assert "600519" in p.positions


def test_execute_day_skips_sell_on_limit_down():
    """跌停日卖单必须被跳过（保持持仓，下一日再试）。"""
    p = Portfolio.new("test", 1_000_000)
    fee_cfg = FeeConfig()
    # 先建仓
    buy(p, "600519", target_amount=100_000, close_price=100.0,
        date="2024-01-01", reason="init", fee_cfg=fee_cfg)
    initial_shares = p.positions["600519"].shares
    # 跌停日卖出信号
    execute_day(
        p, "2024-01-02",
        close_prices={"600519": 90.0},
        sell_signals=[SellSignal(symbol="600519", ratio=1.0, reason="stop_loss")],
        price_info={"600519": {"close": 90.0, "pct_change": -9.9}},  # 跌停
        fee_cfg=fee_cfg,
    )
    assert "600519" in p.positions, "跌停日不应卖出"
    assert p.positions["600519"].shares == initial_shares


def test_execute_day_kcb_limit_20pct():
    """科创板涨停阈值 20%（688 开头），9.85% 不算涨停应放行。"""
    p = Portfolio.new("test", 1_000_000)
    execute_day(
        p, "2024-01-02",
        close_prices={"688981": 55.0},
        buy_signals=[BuySignal(symbol="688981", target_pct=0.2, reason="try")],
        price_info={"688981": {"close": 55.0, "pct_change": 9.85}},  # 主板算涨停但科创板不算
        fee_cfg=FeeConfig(),
    )
    assert "688981" in p.positions

    # 科创板 20% 才算涨停
    p2 = Portfolio.new("test", 1_000_000)
    execute_day(
        p2, "2024-01-02",
        close_prices={"688981": 65.0},
        buy_signals=[BuySignal(symbol="688981", target_pct=0.2, reason="try")],
        price_info={"688981": {"close": 65.0, "pct_change": 19.9}},
        fee_cfg=FeeConfig(),
    )
    assert "688981" not in p2.positions, "科创板 19.9% 视为涨停应跳过"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
