"""
统一执行接口 —— Broker 抽象
==========================

所有真正下单的入口都走这个接口。当前只有一个 PaperBroker（本地撮合），
未来接 QMT / 掘金 / vnpy 时新加一个 XyzBroker 实现同样的方法即可，
上层 runner 完全不用改。

关键动词：
    submit_order()     提交委托（返回 Order，此时可能仍是 PENDING）
    cancel_order()     撤单
    query_orders()     查所有活跃委托
    query_positions()  查当前持仓（回一个 dict[symbol -> shares/avg_cost]）
    query_cash()       查可用现金
    on_tick()          外部推送最新价，触发撮合（仅 PaperBroker 需要）
"""

from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from paper_trade.broker import FeeConfig, _buy_fees, _sell_fees, _is_sh, _round_lot
from paper_trade.portfolio import Portfolio, Trade


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ORDERS_DIR = PROJECT_ROOT / "logs" / "live_orders"
ORDERS_DIR.mkdir(parents=True, exist_ok=True)
_LOCK = Lock()


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"       # 已挂单，未成交
    PARTIAL = "partial"       # 部分成交
    FILLED = "filled"         # 全部成交
    CANCELLED = "cancelled"   # 已撤单
    REJECTED = "rejected"     # 废单（资金不足/涨跌停等）


@dataclass
class Order:
    order_id: str
    symbol: str
    side: OrderSide
    shares: int
    limit_price: float           # 限价（0 表示市价，但 A 股不允许，实际按 fill_at_open 走）
    submitted_at: str
    status: OrderStatus = OrderStatus.PENDING
    filled_shares: int = 0
    filled_avg_price: float = 0.0
    fees_paid: float = 0.0
    reason: str = ""             # 策略给出的原因，便于 UI 展示
    account: str = "default"
    finished_at: Optional[str] = None
    reject_reason: Optional[str] = None


class Broker(ABC):
    """所有 broker 实现必须提供的接口。"""

    @abstractmethod
    def submit_order(self, symbol: str, side: OrderSide, shares: int,
                     limit_price: float, reason: str = "") -> Order: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    def query_orders(self, active_only: bool = False) -> list[Order]: ...

    @abstractmethod
    def query_positions(self) -> dict[str, dict[str, Any]]: ...

    @abstractmethod
    def query_cash(self) -> float: ...


def _account_dir(account: str) -> Path:
    d = ORDERS_DIR / account
    d.mkdir(parents=True, exist_ok=True)
    return d


class PaperBroker(Broker):
    """
    本地撮合：委托进内存队列 → on_tick 用最新价撮合 → 落到 Portfolio。
    与老 paper_trade.broker 不同：**这套是异步事件驱动**，配 M9 定时 runner。

    并发保护：所有变更走 _LOCK。撮合按 FIFO 顺序。
    """

    def __init__(self, portfolio: Portfolio, fee_cfg: FeeConfig | None = None,
                 account: str = "default"):
        self.portfolio = portfolio
        self.fee_cfg = fee_cfg or FeeConfig()
        self.account = account
        self.orders: dict[str, Order] = {}
        self._load()

    # ---- 持久化 -------------------------------------------------

    def _orders_path(self) -> Path:
        return _account_dir(self.account) / "orders.json"

    def _load(self):
        p = self._orders_path()
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for od in data:
                od["side"] = OrderSide(od["side"])
                od["status"] = OrderStatus(od["status"])
                self.orders[od["order_id"]] = Order(**od)
        except Exception:
            pass

    def _save(self):
        with _LOCK:
            data = [asdict(o) for o in self.orders.values()]
            # dataclass asdict 已把 enum 转成值，但为 mypy 兼容再显式一次
            for od in data:
                od["side"] = od["side"].value if hasattr(od["side"], "value") else od["side"]
                od["status"] = od["status"].value if hasattr(od["status"], "value") else od["status"]
            self._orders_path().write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                            encoding="utf-8")

    # ---- Broker 接口 --------------------------------------------

    def submit_order(self, symbol: str, side: OrderSide, shares: int,
                     limit_price: float, reason: str = "") -> Order:
        shares = _round_lot(shares) if side == OrderSide.BUY else int(shares)
        if shares <= 0:
            order = Order(
                order_id=uuid.uuid4().hex[:12],
                symbol=symbol, side=side, shares=0,
                limit_price=float(limit_price),
                submitted_at=datetime.now().isoformat(timespec="seconds"),
                reason=reason, account=self.account,
                status=OrderStatus.REJECTED, reject_reason="shares<=0",
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
            self.orders[order.order_id] = order
            self._save()
            return order

        order = Order(
            order_id=uuid.uuid4().hex[:12],
            symbol=symbol, side=side, shares=int(shares),
            limit_price=float(limit_price),
            submitted_at=datetime.now().isoformat(timespec="seconds"),
            reason=reason, account=self.account,
        )
        self.orders[order.order_id] = order
        self._save()
        return order

    def cancel_order(self, order_id: str) -> bool:
        with _LOCK:
            o = self.orders.get(order_id)
            if o is None:
                return False
            if o.status not in (OrderStatus.PENDING, OrderStatus.PARTIAL):
                return False
            o.status = OrderStatus.CANCELLED
            o.finished_at = datetime.now().isoformat(timespec="seconds")
        self._save()
        return True

    def query_orders(self, active_only: bool = False) -> list[Order]:
        vs = list(self.orders.values())
        if active_only:
            vs = [o for o in vs if o.status in (OrderStatus.PENDING, OrderStatus.PARTIAL)]
        return sorted(vs, key=lambda o: o.submitted_at, reverse=True)

    def query_positions(self) -> dict[str, dict[str, Any]]:
        return {
            sym: {"shares": p.shares, "avg_cost": p.avg_cost,
                  "last_price": p.last_price, "open_date": p.open_date}
            for sym, p in self.portfolio.positions.items()
        }

    def query_cash(self) -> float:
        return self.portfolio.cash

    # ---- 撮合入口（PaperBroker 专属）-----------------------------

    def on_tick(self, prices: dict[str, float]) -> list[Order]:
        """
        用最新价扫一遍活跃委托，能撮的立刻撮。
        返回本 tick 里状态变化（新成交/新废单）的 Order 列表。
        """
        changed: list[Order] = []
        with _LOCK:
            for o in list(self.orders.values()):
                if o.status not in (OrderStatus.PENDING, OrderStatus.PARTIAL):
                    continue
                px = prices.get(o.symbol)
                if px is None or px <= 0:
                    continue
                # A 股买卖限价规则：限价买 ≥ 市价才成，限价卖 ≤ 市价才成
                if o.side == OrderSide.BUY and o.limit_price >= px:
                    self._fill(o, px)
                    changed.append(o)
                elif o.side == OrderSide.SELL and o.limit_price <= px:
                    self._fill(o, px)
                    changed.append(o)
        if changed:
            self._save()
        return changed

    def _fill(self, o: Order, price: float) -> None:
        """
        简化撮合：一次全成交。真实市场里可能部分成交，此处刻意从简，
        对散户量化 20 万以下的策略基本没影响。
        """
        remaining = o.shares - o.filled_shares
        if remaining <= 0:
            return
        amount = remaining * price
        is_sh = _is_sh(o.symbol)
        if o.side == OrderSide.BUY:
            fee = _buy_fees(amount, is_sh, self.fee_cfg)
            total = amount + fee
            if self.portfolio.cash < total:
                o.status = OrderStatus.REJECTED
                o.reject_reason = f"资金不足：需 {total:.2f} > 可用 {self.portfolio.cash:.2f}"
                o.finished_at = datetime.now().isoformat(timespec="seconds")
                return
            # 落 Trade + 持仓
            self.portfolio.apply_buy(o.symbol, remaining, price, fee,
                                      date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                      reason=o.reason or "live_paper")
        else:
            pos = self.portfolio.positions.get(o.symbol)
            if pos is None or pos.shares < remaining:
                o.status = OrderStatus.REJECTED
                o.reject_reason = "持仓不足"
                o.finished_at = datetime.now().isoformat(timespec="seconds")
                return
            fee = _sell_fees(amount, is_sh, self.fee_cfg)
            self.portfolio.apply_sell(o.symbol, remaining, price, fee,
                                       date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                       reason=o.reason or "live_paper")

        # 更新委托状态
        o.filled_shares = o.shares
        # 加权平均成交价（当前实现只有一次成交所以就是 price）
        o.filled_avg_price = price
        o.fees_paid += fee
        o.status = OrderStatus.FILLED
        o.finished_at = datetime.now().isoformat(timespec="seconds")
