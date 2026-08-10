"""
QMT (国金 miniQMT / 迅投客户端) 真实盘 Broker
=============================================

用 xtquant SDK 把项目的统一 Broker 接口对接到国金/华泰/东财等 QMT 券商。

**上实盘前必读**
1. 需要在券商开通量化交易权限（一般要求账户资产 ≥ 50 万）
2. 需要券商发的 miniQMT.exe 客户端在同机器上登录并运行
3. pip install xtquant （只在 Windows / 部分 Linux 有官方包）
4. 建议先跑券商的**仿真账户**至少 1 个月，确认无异常再上真钱

配置来源（按优先级）：
    1) 传入 broker_config={'account_id': 'xxx', 'user_data_path': 'C:/QMT/userdata_mini'}
    2) 环境变量 QMT_ACCOUNT_ID / QMT_USER_DATA_PATH
    3) configs/qmt.yaml

**未安装 xtquant 或未配置账号**时：
- 类可以正常 import（不会崩溃打死整个 web）
- 但调 submit_order 会抛 QMTNotAvailable，前端会看到明确报错
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from execution.broker import (
    Broker, Order, OrderSide, OrderStatus, _account_dir, _LOCK as _MOD_LOCK,
)


class QMTNotAvailable(RuntimeError):
    """xtquant 没装 / miniQMT 没登录 / 账号未配置 时抛。"""


def _try_import_xtquant():
    """惰性 import 让本文件在无 xtquant 环境也能被加载。"""
    try:
        from xtquant import xtconstant  # type: ignore
        from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback  # type: ignore
        from xtquant.xttype import StockAccount  # type: ignore
        return {
            "xtconstant": xtconstant,
            "XtQuantTrader": XtQuantTrader,
            "XtQuantTraderCallback": XtQuantTraderCallback,
            "StockAccount": StockAccount,
        }
    except Exception as e:
        return {"error": str(e)}


def _load_config(broker_config: dict | None) -> dict:
    """三层配置来源：入参 > 环境变量 > configs/qmt.yaml。"""
    cfg = dict(broker_config or {})
    for k, env_k in [
        ("account_id", "QMT_ACCOUNT_ID"),
        ("user_data_path", "QMT_USER_DATA_PATH"),
        ("broker", "QMT_BROKER"),
    ]:
        if not cfg.get(k) and os.environ.get(env_k):
            cfg[k] = os.environ[env_k]
    # yaml
    p = Path("configs/qmt.yaml")
    if p.exists():
        try:
            import yaml
            fcfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            for k, v in fcfg.items():
                cfg.setdefault(k, v)
        except Exception:
            pass
    return cfg


class QMTBroker(Broker):
    """
    真接 xtquant 的 Broker 实现。**所有委托都直接发往券商柜台**——请谨慎测试。

    与 PaperBroker 的区别：
    - 无 on_tick 撮合（成交由券商推送回调）
    - query_positions / query_cash 直接问 xtquant，不看本地 Portfolio
    - order 状态同步依赖 XtQuantTraderCallback

    account 参数只用于本地日志/挂单簿持久化路径，与 QMT 账户号不同。
    """

    def __init__(self, account: str, broker_config: dict | None = None):
        self.account = account
        self.broker_config = _load_config(broker_config)
        self._orders: dict[str, Order] = {}
        self._orders_by_qmt_id: dict[int, str] = {}   # QMT 内部 order_id -> 我们的 order_id
        self._lock = Lock()
        self._trader = None       # xtquant XtQuantTrader
        self._stock_account = None
        self._connected = False
        self._sdk = _try_import_xtquant()
        # 加载已持久化的挂单簿（跨重启保留）
        self._load()

    # ---- 元信息 -------------------------------------------------

    def is_available(self) -> tuple[bool, str]:
        """未连接原因（供前端展示）。"""
        if "error" in self._sdk:
            return False, f"xtquant SDK 未安装：{self._sdk['error'][:120]}"
        if not self.broker_config.get("account_id"):
            return False, "未配置 QMT account_id（设置页填写国金资金账号）"
        if not self.broker_config.get("user_data_path"):
            return False, "未配置 QMT user_data_path（miniQMT 客户端安装目录下的 userdata_mini）"
        if not self._connected:
            return False, "尚未连接 miniQMT 客户端（请确保客户端已启动并登录）"
        return True, "已连接 QMT"

    # ---- 连接 ---------------------------------------------------

    def connect(self) -> None:
        """
        建立到 miniQMT 客户端的连接。miniQMT 必须在本机运行且已登录。
        """
        if "error" in self._sdk:
            raise QMTNotAvailable(f"xtquant SDK 未安装：{self._sdk['error']}")
        if not self.broker_config.get("account_id"):
            raise QMTNotAvailable("未配置 account_id")
        if not self.broker_config.get("user_data_path"):
            raise QMTNotAvailable("未配置 user_data_path")

        udp = self.broker_config["user_data_path"]
        session_id = int(datetime.now().strftime("%H%M%S"))
        XtQuantTrader = self._sdk["XtQuantTrader"]
        StockAccount = self._sdk["StockAccount"]

        self._trader = XtQuantTrader(udp, session_id)
        self._trader.register_callback(_make_callback(self))
        self._trader.start()
        result = self._trader.connect()
        if result != 0:
            raise QMTNotAvailable(f"connect() 失败：返回码 {result}（miniQMT 客户端未启动？）")
        self._stock_account = StockAccount(self.broker_config["account_id"], "STOCK")
        sub_result = self._trader.subscribe(self._stock_account)
        if sub_result != 0:
            raise QMTNotAvailable(f"subscribe() 失败：返回码 {sub_result}")
        self._connected = True

    # ---- 内部持久化 ----------------------------------------------

    def _orders_path(self):
        return _account_dir(self.account) / "orders.json"

    def _save(self):
        import json
        with _MOD_LOCK:
            from dataclasses import asdict
            data = [asdict(o) for o in self._orders.values()]
            for od in data:
                od["side"] = od["side"].value if hasattr(od["side"], "value") else od["side"]
                od["status"] = od["status"].value if hasattr(od["status"], "value") else od["status"]
            self._orders_path().write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self):
        import json
        p = self._orders_path()
        if not p.exists():
            return
        try:
            for od in json.loads(p.read_text(encoding="utf-8")):
                od["side"] = OrderSide(od["side"])
                od["status"] = OrderStatus(od["status"])
                self._orders[od["order_id"]] = Order(**od)
        except Exception:
            pass

    # ---- Broker 接口 --------------------------------------------

    def submit_order(self, symbol: str, side: OrderSide, shares: int,
                     limit_price: float, reason: str = "") -> Order:
        if not self._connected:
            try:
                self.connect()
            except QMTNotAvailable as e:
                # 造一个 REJECTED 单让前端能看到失败原因，不抛异常打断 runner
                order = Order(
                    order_id=uuid.uuid4().hex[:12],
                    symbol=symbol, side=side, shares=int(shares),
                    limit_price=float(limit_price),
                    submitted_at=datetime.now().isoformat(timespec="seconds"),
                    reason=reason, account=self.account,
                    status=OrderStatus.REJECTED,
                    reject_reason=f"QMT 未就绪：{e}",
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                )
                self._orders[order.order_id] = order
                self._save()
                return order

        xtconstant = self._sdk["xtconstant"]
        order_type = (xtconstant.STOCK_BUY if side == OrderSide.BUY
                      else xtconstant.STOCK_SELL)
        # QMT 用 6 位代码 + 后缀 SH/SZ
        qmt_symbol = _to_qmt_symbol(symbol)

        qmt_order_id = self._trader.order_stock(
            self._stock_account,
            qmt_symbol,
            order_type,
            int(shares),
            xtconstant.FIX_PRICE,       # 限价单
            float(limit_price),
            "tonghuashunAI",             # strategy_name
            reason or "auto",
        )

        order = Order(
            order_id=uuid.uuid4().hex[:12],
            symbol=symbol, side=side, shares=int(shares),
            limit_price=float(limit_price),
            submitted_at=datetime.now().isoformat(timespec="seconds"),
            reason=reason, account=self.account,
            status=OrderStatus.PENDING if qmt_order_id > 0 else OrderStatus.REJECTED,
            reject_reason=None if qmt_order_id > 0 else f"order_stock 返回 {qmt_order_id}",
        )
        with self._lock:
            self._orders[order.order_id] = order
            if qmt_order_id > 0:
                self._orders_by_qmt_id[qmt_order_id] = order.order_id
        self._save()
        return order

    def cancel_order(self, order_id: str) -> bool:
        with self._lock:
            o = self._orders.get(order_id)
            if o is None or o.status not in (OrderStatus.PENDING, OrderStatus.PARTIAL):
                return False
            # 找 QMT id
            qmt_id = None
            for qid, oid in self._orders_by_qmt_id.items():
                if oid == order_id:
                    qmt_id = qid
                    break
            if qmt_id is None:
                # 只是本地态：直接标 cancelled
                o.status = OrderStatus.CANCELLED
                o.finished_at = datetime.now().isoformat(timespec="seconds")
                self._save()
                return True
        if not self._connected:
            return False
        ret = self._trader.cancel_order_stock(self._stock_account, qmt_id)
        return ret == 0  # 回调会同步 status

    def query_orders(self, active_only: bool = False) -> list[Order]:
        vs = list(self._orders.values())
        if active_only:
            vs = [o for o in vs if o.status in (OrderStatus.PENDING, OrderStatus.PARTIAL)]
        return sorted(vs, key=lambda o: o.submitted_at, reverse=True)

    def query_positions(self) -> dict[str, dict[str, Any]]:
        """真实持仓从 QMT 拉取。未连接时返回空。"""
        if not self._connected:
            return {}
        pos_list = self._trader.query_stock_positions(self._stock_account) or []
        out = {}
        for p in pos_list:
            sym = _from_qmt_symbol(p.stock_code)
            out[sym] = {
                "shares": int(getattr(p, "volume", 0) or 0),
                "avg_cost": float(getattr(p, "open_price", 0.0) or 0.0),
                "last_price": float(getattr(p, "market_value", 0.0) or 0.0) /
                              (int(getattr(p, "volume", 1)) or 1),
                "open_date": "",  # QMT 没直接提供，可从 trade 历史反推
            }
        return out

    def query_cash(self) -> float:
        if not self._connected:
            return 0.0
        asset = self._trader.query_stock_asset(self._stock_account)
        if asset is None:
            return 0.0
        return float(getattr(asset, "cash", 0.0) or 0.0)


# ---- 辅助 -----------------------------------------------------------


def _to_qmt_symbol(symbol: str) -> str:
    """6 位代码 → QMT 格式（600519 → 600519.SH，000001 → 000001.SZ，688xxx → SH）。"""
    if symbol.startswith(("6", "9", "5")) or symbol.startswith("688"):
        return f"{symbol}.SH"
    return f"{symbol}.SZ"


def _from_qmt_symbol(qmt_symbol: str) -> str:
    return qmt_symbol.split(".")[0]


def _make_callback(broker: "QMTBroker"):
    """构造 XtQuantTraderCallback 实例，处理成交回报/委托状态变化。"""
    if "error" in broker._sdk:
        return None
    XtQuantTraderCallback = broker._sdk["XtQuantTraderCallback"]

    class _Cb(XtQuantTraderCallback):
        def on_stock_order(self, order):  # 委托状态变化
            local_id = broker._orders_by_qmt_id.get(order.order_id)
            if not local_id:
                return
            o = broker._orders.get(local_id)
            if not o:
                return
            # QMT order_status 常量：48=已报, 49=部分成交, 54=已成, 53=已撤, 51=废单
            sm = {48: OrderStatus.PENDING, 49: OrderStatus.PARTIAL,
                  54: OrderStatus.FILLED, 53: OrderStatus.CANCELLED,
                  51: OrderStatus.REJECTED, 52: OrderStatus.REJECTED}
            new_st = sm.get(order.order_status)
            if new_st:
                o.status = new_st
                if new_st in (OrderStatus.FILLED, OrderStatus.CANCELLED,
                              OrderStatus.REJECTED):
                    o.finished_at = datetime.now().isoformat(timespec="seconds")
            broker._save()

        def on_stock_trade(self, trade):  # 成交回报
            local_id = broker._orders_by_qmt_id.get(trade.order_id)
            if not local_id:
                return
            o = broker._orders.get(local_id)
            if not o:
                return
            o.filled_shares += int(getattr(trade, "traded_volume", 0) or 0)
            o.filled_avg_price = float(getattr(trade, "traded_price", 0.0) or 0.0)
            broker._save()

        def on_disconnected(self):
            broker._connected = False

    return _Cb()
