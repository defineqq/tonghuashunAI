"""
实时模拟盘 runner —— 后台循环，用最新快照驱动 PaperBroker
=========================================================

每 tick_seconds 秒：
  1. 用 market.snapshot() 拉全 A 实时快照
  2. 提取所有活跃委托的最新价，喂给 PaperBroker.on_tick 触发撮合
  3. 对每只 subscribe 的股票跑一次策略信号函数（可选）
  4. mark-to-market 并落一份持仓快照

只在**交易日的开盘时段**跑（默认 9:30–11:30 / 13:00–15:00）；
非交易时段静默 sleep，不产生请求。

线程化：runner 独立线程，前端 API 只做启动/停止 + 查状态。
每个 account 一个 runner，logs/live_runner/{account}.json 记录状态。
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any, Optional

from data_layer import market
from paper_trade import portfolio as pfolio

from execution.broker import PaperBroker, Order, OrderSide


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "logs" / "live_runner"
STATE_DIR.mkdir(parents=True, exist_ok=True)

_RUNNERS: dict[str, "LiveRunner"] = {}
_REG_LOCK = threading.Lock()


TRADING_MORNING = (dtime(9, 30), dtime(11, 30))
TRADING_AFTERNOON = (dtime(13, 0), dtime(15, 0))


def is_trading_hours(now: datetime | None = None) -> bool:
    """粗略判断：在交易时段内？不检查节假日（AkShare 交易日历接口不稳定，交给下游）。"""
    now = now or datetime.now()
    if now.weekday() >= 5:  # 周末
        return False
    t = now.time()
    return (TRADING_MORNING[0] <= t <= TRADING_MORNING[1]
            or TRADING_AFTERNOON[0] <= t <= TRADING_AFTERNOON[1])


@dataclass
class RunnerState:
    account: str
    status: str = "stopped"          # running | stopped | error
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    last_tick_at: Optional[str] = None
    ticks_count: int = 0
    orders_filled_count: int = 0
    tick_seconds: int = 15
    error: Optional[str] = None
    # UI 只读：symbols 是当前 runner 关心的候选池，若为空则只看已有持仓
    watch_symbols: list[str] = field(default_factory=list)
    strategy_id: Optional[str] = None
    strategy_params: dict[str, Any] = field(default_factory=dict)

    def save(self):
        (STATE_DIR / f"{self.account}.json").write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, account: str) -> Optional["RunnerState"]:
        p = STATE_DIR / f"{account}.json"
        if not p.exists():
            return None
        return cls(**json.loads(p.read_text(encoding="utf-8")))


class LiveRunner:
    def __init__(self, account: str, watch_symbols: list[str] | None = None,
                 strategy_id: Optional[str] = None,
                 strategy_params: dict | None = None,
                 tick_seconds: int = 15):
        self.account = account
        self.watch_symbols = list(watch_symbols or [])
        self.strategy_id = strategy_id
        self.strategy_params = strategy_params or {}
        self.tick_seconds = max(5, int(tick_seconds))  # 最快 5 秒/tick，避免刷爆快照 API
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.portfolio = pfolio.load_or_create(account)
        self.broker = PaperBroker(self.portfolio, account=account)
        self.state = RunnerState(
            account=account,
            watch_symbols=self.watch_symbols,
            strategy_id=strategy_id,
            strategy_params=self.strategy_params,
            tick_seconds=self.tick_seconds,
        )

    # ---- 控制 --------------------------------------------------

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.state.status = "running"
        self.state.started_at = datetime.now().isoformat(timespec="seconds")
        self.state.stopped_at = None
        self.state.error = None
        self.state.save()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.state.status = "stopped"
        self.state.stopped_at = datetime.now().isoformat(timespec="seconds")
        self.state.save()

    # ---- 主循环 ------------------------------------------------

    def _loop(self):
        try:
            while not self._stop.is_set():
                try:
                    self._tick_once()
                except Exception as e:
                    # tick 内异常不停 runner，只记录，下轮继续
                    self.state.error = f"{type(e).__name__}: {str(e)[:200]}"
                # 等 tick_seconds 但可被 stop 立即打断
                if self._stop.wait(self.tick_seconds):
                    break
        finally:
            self.state.status = "stopped"
            self.state.stopped_at = datetime.now().isoformat(timespec="seconds")
            self.state.save()

    def _tick_once(self):
        # 非交易时段直接返回，不发请求
        if not is_trading_hours():
            return

        # 1) 拉快照
        try:
            df = market.snapshot()
        except Exception as e:
            self.state.error = f"快照失败: {e}"
            self.state.save()
            return

        # 快照列名兜底
        code_col = next((c for c in df.columns if c in ("代码", "symbol")), None)
        price_col = next((c for c in df.columns if c in ("最新价", "close", "price")), None)
        if not (code_col and price_col):
            self.state.error = f"快照列不识别 {list(df.columns)[:5]}"
            self.state.save()
            return

        # 2) 建 code -> price 索引
        df = df.copy()
        df[code_col] = df[code_col].astype(str).str.zfill(6)
        prices = dict(zip(df[code_col], df[price_col].astype(float)))

        # 3) 撮合活跃委托
        changed = self.broker.on_tick(prices)
        for o in changed:
            if o.status.value == "filled":
                self.state.orders_filled_count += 1

        # 4) 更新 mark-to-market
        for sym, pos in self.portfolio.positions.items():
            if sym in prices:
                pos.last_price = prices[sym]
        self.portfolio.save(pfolio.default_path(self.account))

        # 5) 策略生成新信号（如果配置了）
        if self.strategy_id:
            try:
                self._run_strategy_once(prices)
            except Exception as e:
                self.state.error = f"策略执行失败: {e}"

        # 6) 更新 runner 状态
        self.state.last_tick_at = datetime.now().isoformat(timespec="seconds")
        self.state.ticks_count += 1
        self.state.save()

    def _run_strategy_once(self, prices: dict[str, float]) -> None:
        """
        对 watch_symbols 里每只股票跑一次策略；仅当没有活跃委托 & 未持仓时才下新单。
        委托类型：限价单，用当前快照价 ±0.5% 作为价格保护。
        """
        from strategies.registry import registry, bootstrap
        bootstrap()
        strat = registry.get(self.strategy_id) if self.strategy_id else None
        if strat is None:
            return

        active_syms = {o.symbol for o in self.broker.query_orders(active_only=True)}

        for sym in self.watch_symbols:
            if sym in active_syms:
                continue
            price = prices.get(sym)
            if not price:
                continue
            # 简化：这里只做"是否持仓 + 是否有信号"，具体 signal 由策略决定
            # 因为分钟/日线数据要拉，成本高，M9 阶段先只根据"有无持仓 + 有无候选"下单
            has_position = sym in self.portfolio.positions
            # 用日线拉取最近 60 根做一次策略决策
            try:
                df = market.daily(sym, start="2024-01-01",
                                   end=datetime.now().strftime("%Y-%m-%d"))
                if df.empty or len(df) < 60:
                    continue
                signals = strat.generate_signals(df, self.strategy_params or {})
                latest = signals[-1] if signals else None
                if latest is None:
                    continue
                action = latest.action.value if hasattr(latest.action, "value") else str(latest.action)
                if action == "buy" and not has_position and self.portfolio.cash > 5000:
                    # 单只固定 20% 仓位
                    cash_slot = self.portfolio.cash * 0.2
                    shares = int(cash_slot / price / 100) * 100
                    if shares >= 100:
                        self.broker.submit_order(
                            symbol=sym, side=OrderSide.BUY, shares=shares,
                            limit_price=round(price * 1.005, 2),
                            reason=f"{self.strategy_id}: {latest.reason or 'buy'}",
                        )
                elif action == "sell" and has_position:
                    self.broker.submit_order(
                        symbol=sym, side=OrderSide.SELL,
                        shares=self.portfolio.positions[sym].shares,
                        limit_price=round(price * 0.995, 2),
                        reason=f"{self.strategy_id}: {latest.reason or 'sell'}",
                    )
            except Exception:
                continue


def get_runner(account: str) -> Optional[LiveRunner]:
    with _REG_LOCK:
        return _RUNNERS.get(account)


def start_runner(account: str, watch_symbols: list[str] | None = None,
                 strategy_id: Optional[str] = None,
                 strategy_params: dict | None = None,
                 tick_seconds: int = 15) -> LiveRunner:
    with _REG_LOCK:
        r = _RUNNERS.get(account)
        if r and r._thread and r._thread.is_alive():
            return r
        r = LiveRunner(account=account, watch_symbols=watch_symbols,
                       strategy_id=strategy_id, strategy_params=strategy_params,
                       tick_seconds=tick_seconds)
        _RUNNERS[account] = r
        r.start()
        return r


def stop_runner(account: str) -> bool:
    with _REG_LOCK:
        r = _RUNNERS.get(account)
        if r is None:
            return False
        r.stop()
        return True


def list_runners() -> list[dict]:
    out = []
    for f in STATE_DIR.glob("*.json"):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return sorted(out, key=lambda d: d.get("started_at", ""), reverse=True)
