"""
账户与持仓状态
==============

设计要点：
- Portfolio 是纯数据类 + JSON 序列化，业务逻辑放在 broker 里
- 每天调用 mark_to_market(date) 用当日收盘价计算总市值和 PnL
- history 里存每天一份快照，便于回测后画曲线

JSON 结构示例：
{
  "account_id": "swing_v1",
  "initial_cash": 100000.0,
  "cash": 87500.0,
  "positions": {
    "600519": {"shares": 100, "avg_cost": 1650.0, "open_date": "2024-10-08"}
  },
  "trades": [
    {"date": "2024-10-08", "symbol": "600519", "side": "buy",
     "shares": 100, "price": 1650.0, "cost": 165165.0, "reason": "swing_v1 signal"}
  ],
  "daily_snapshots": [
    {"date": "2024-10-08", "cash": 82500, "positions_value": 165000, "total": 247500, "pnl_pct": -0.01}
  ]
}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path


@dataclass
class Position:
    shares: int                   # 持股数（100 股为最小单位）
    avg_cost: float               # 平均成本（含费）
    open_date: str                # 建仓日期 YYYY-MM-DD
    last_price: float = 0.0       # 最新价（mark_to_market 时更新）

    @property
    def market_value(self) -> float:
        return self.shares * self.last_price

    @property
    def unrealized_pnl(self) -> float:
        return (self.last_price - self.avg_cost) * self.shares

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.avg_cost == 0:
            return 0.0
        return (self.last_price - self.avg_cost) / self.avg_cost


@dataclass
class Trade:
    date: str
    symbol: str
    side: str                     # "buy" | "sell"
    shares: int
    price: float
    amount: float                 # 成交金额（不含费）
    fee: float                    # 手续费 + 印花税 + 过户费
    reason: str = ""              # 触发原因（策略信号 / 止损 / 止盈 / 到期）


@dataclass
class Snapshot:
    date: str
    cash: float
    positions_value: float
    total: float
    pnl_pct: float                # 相对初始资金的累计 PnL
    n_positions: int


@dataclass
class Portfolio:
    account_id: str = "default"
    initial_cash: float = 100_000.0
    cash: float = 100_000.0
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)
    daily_snapshots: list[Snapshot] = field(default_factory=list)

    # ---- 序列化 ----
    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "initial_cash": self.initial_cash,
            "cash": round(self.cash, 2),
            "positions": {s: asdict(p) for s, p in self.positions.items()},
            "trades": [asdict(t) for t in self.trades],
            "daily_snapshots": [asdict(s) for s in self.daily_snapshots],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Portfolio":
        return cls(
            account_id=d["account_id"],
            initial_cash=d["initial_cash"],
            cash=d["cash"],
            positions={s: Position(**p) for s, p in d.get("positions", {}).items()},
            trades=[Trade(**t) for t in d.get("trades", [])],
            daily_snapshots=[Snapshot(**s) for s in d.get("daily_snapshots", [])],
        )

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Portfolio":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    # ---- 计算 ----
    def positions_value(self) -> float:
        return sum(p.market_value for p in self.positions.values())

    def total_value(self) -> float:
        return self.cash + self.positions_value()

    def total_pnl_pct(self) -> float:
        if self.initial_cash == 0:
            return 0.0
        return (self.total_value() - self.initial_cash) / self.initial_cash

    def take_snapshot(self, date: str) -> Snapshot:
        snap = Snapshot(
            date=date,
            cash=round(self.cash, 2),
            positions_value=round(self.positions_value(), 2),
            total=round(self.total_value(), 2),
            pnl_pct=round(self.total_pnl_pct(), 4),
            n_positions=len(self.positions),
        )
        self.daily_snapshots.append(snap)
        return snap

    @classmethod
    def new(cls, account_id: str, initial_cash: float = 100_000.0) -> "Portfolio":
        return cls(account_id=account_id, initial_cash=initial_cash, cash=initial_cash)

    # ---- 事件驱动式操作（M9 live_paper 用）----
    def apply_buy(self, symbol: str, shares: int, price: float, fee: float,
                  date: str, reason: str = "") -> None:
        """执行一笔买单：扣现金 → 更新加权成本 → 记 Trade。"""
        amount = shares * price
        total_cost = amount + fee
        self.cash = round(self.cash - total_cost, 4)
        pos = self.positions.get(symbol)
        if pos is None:
            self.positions[symbol] = Position(
                shares=shares, avg_cost=(total_cost / shares) if shares else 0.0,
                open_date=date, last_price=price,
            )
        else:
            new_shares = pos.shares + shares
            # 加权平均成本（含费）
            pos.avg_cost = round((pos.avg_cost * pos.shares + total_cost) / new_shares, 4)
            pos.shares = new_shares
            pos.last_price = price
        self.trades.append(Trade(date=date, symbol=symbol, side="buy",
                                  shares=shares, price=price, amount=amount,
                                  fee=fee, reason=reason))

    def apply_sell(self, symbol: str, shares: int, price: float, fee: float,
                   date: str, reason: str = "") -> None:
        """执行一笔卖单：加回现金 → 减仓位 → 记 Trade。"""
        pos = self.positions.get(symbol)
        if pos is None or pos.shares < shares:
            raise ValueError(f"apply_sell: 持仓不足 symbol={symbol}")
        amount = shares * price
        proceeds = amount - fee
        self.cash = round(self.cash + proceeds, 4)
        pos.shares -= shares
        pos.last_price = price
        if pos.shares == 0:
            del self.positions[symbol]
        self.trades.append(Trade(date=date, symbol=symbol, side="sell",
                                  shares=shares, price=price, amount=amount,
                                  fee=fee, reason=reason))


_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def default_path(account_id: str) -> Path:
    """账户文件默认路径：<项目根>/logs/portfolio/{account_id}.json"""
    return _PROJECT_ROOT / "logs" / "portfolio" / f"{account_id}.json"


def load_or_create(account_id: str, initial_cash: float = 100_000.0) -> Portfolio:
    """加载已存在的账户，或新建一个。"""
    p = default_path(account_id)
    if p.exists():
        return Portfolio.load(p)
    return Portfolio.new(account_id, initial_cash)
