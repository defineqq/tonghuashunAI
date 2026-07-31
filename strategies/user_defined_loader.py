"""
用户 Python 策略加载器
======================

用户在 Web 编辑器写代码，保存到 strategies/user_defined/*.py，我们动态 import 并注册。

**安全说明**：这里我们不做真正的沙箱（Python 沙箱几乎做不到完全隔离）。
如果暴露到公网，请只允许可信用户，或者上 Docker/subprocess 隔离。
本地个人使用问题不大——用户是自己，等于自己在自己电脑上跑 Python。

约定：用户脚本必须定义 `strategy_meta` 字典 和 `generate_signals(bars, params)` 函数。

示例（放到 strategies/user_defined/my_strategy.py）：

    strategy_meta = {
        "id": "my_strategy",
        "name": "我的策略",
        "description": "5 日线上穿 20 日线时买入",
        "params": [
            {"name": "fast", "label": "快线", "type": "int", "default": 5},
            {"name": "slow", "label": "慢线", "type": "int", "default": 20},
        ],
    }

    def generate_signals(bars, params, tools):
        fast = tools.sma(bars["close"], params["fast"])
        slow = tools.sma(bars["close"], params["slow"])
        signals = []
        for i, date in enumerate(bars["date"]):
            if i > 0 and fast.iloc[i] > slow.iloc[i] and fast.iloc[i-1] <= slow.iloc[i-1]:
                signals.append({"date": date, "action": "buy", "reason": "金叉"})
            elif i > 0 and fast.iloc[i] < slow.iloc[i] and fast.iloc[i-1] >= slow.iloc[i-1]:
                signals.append({"date": date, "action": "sell", "reason": "死叉"})
            else:
                signals.append({"date": date, "action": "hold", "reason": ""})
        return signals
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pandas as pd

from strategies.base import (
    TechnicalStrategy, BarSignal, SignalAction,
    StrategyKind, StrategyMeta, StrategyParam,
)


class Tools:
    """暴露给用户脚本的工具函数集合。"""
    sma = staticmethod(TechnicalStrategy.sma)
    ema = staticmethod(TechnicalStrategy.ema)
    macd = staticmethod(TechnicalStrategy.macd)
    rsi = staticmethod(TechnicalStrategy.rsi)
    kdj = staticmethod(TechnicalStrategy.kdj)
    bollinger = staticmethod(TechnicalStrategy.bollinger)
    atr = staticmethod(TechnicalStrategy.atr)
    cross_up = staticmethod(TechnicalStrategy.cross_up)
    cross_down = staticmethod(TechnicalStrategy.cross_down)


class UserPythonStrategy(TechnicalStrategy):
    def __init__(self, module):
        self._module = module
        meta_dict = getattr(module, "strategy_meta", None)
        if not meta_dict:
            raise ValueError("用户脚本必须定义 strategy_meta 字典")

        params = [
            StrategyParam(
                name=p["name"], label=p.get("label", p["name"]),
                type=p.get("type", "float"), default=p["default"],
                min=p.get("min"), max=p.get("max"), step=p.get("step"),
                choices=p.get("choices"), help=p.get("help", ""),
            )
            for p in meta_dict.get("params", [])
        ]
        self.meta = StrategyMeta(
            id=meta_dict["id"],
            name=meta_dict.get("name", meta_dict["id"]),
            kind=StrategyKind.PYTHON,
            category="Python 自定义",
            description=meta_dict.get("description", ""),
            long_description=meta_dict.get("long_description", ""),
            params=params,
            tags=["Python", "自定义"],
        )
        if not hasattr(module, "generate_signals"):
            raise ValueError("用户脚本必须定义 generate_signals(bars, params, tools) 函数")

    def generate_signals(self, bars: pd.DataFrame, params: dict | None = None) -> list[BarSignal]:
        p = {**self.default_params(), **(params or {})}
        raw = self._module.generate_signals(bars, p, Tools)
        # 用户可能返回 list[dict] 或 list[BarSignal]
        signals = []
        for x in raw:
            if isinstance(x, BarSignal):
                signals.append(x)
                continue
            action = x.get("action", "hold")
            try:
                action_enum = SignalAction(action)
            except ValueError:
                action_enum = SignalAction.HOLD
            signals.append(BarSignal(
                date=pd.Timestamp(x["date"]),
                action=action_enum,
                reason=x.get("reason", ""),
            ))
        return signals


def load_user_python(path: str | Path) -> UserPythonStrategy | None:
    """从一个 .py 文件加载并实例化用户策略。"""
    path = Path(path)
    spec = importlib.util.spec_from_file_location(f"user_strategy_{path.stem}", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return UserPythonStrategy(module)


DEFAULT_TEMPLATE = '''"""
自定义 Python 策略模板

修改下面的 strategy_meta 和 generate_signals，保存后即可在回测中选择。
"""

strategy_meta = {
    "id": "my_new_strategy",
    "name": "我的新策略",
    "description": "在这里描述策略逻辑",
    "params": [
        {"name": "fast", "label": "快线周期", "type": "int", "default": 5, "min": 2, "max": 60},
        {"name": "slow", "label": "慢线周期", "type": "int", "default": 20, "min": 5, "max": 250},
    ],
}


def generate_signals(bars, params, tools):
    """
    Args:
        bars: DataFrame，列 date/open/high/low/close/volume，按日期升序
        params: dict，用户设置的参数
        tools: 工具类，可用：tools.sma / tools.ema / tools.macd / tools.rsi
               tools.kdj / tools.bollinger / tools.atr / tools.cross_up / tools.cross_down

    Returns:
        list of dict，每个 dict: {"date": ..., "action": "buy"|"sell"|"hold", "reason": ...}
        每根 K 线一条。
    """
    fast = tools.sma(bars["close"], params["fast"])
    slow = tools.sma(bars["close"], params["slow"])
    signals = []
    for i, date in enumerate(bars["date"]):
        if i > 0 and fast.iloc[i] > slow.iloc[i] and fast.iloc[i-1] <= slow.iloc[i-1]:
            signals.append({"date": date, "action": "buy", "reason": "金叉"})
        elif i > 0 and fast.iloc[i] < slow.iloc[i] and fast.iloc[i-1] >= slow.iloc[i-1]:
            signals.append({"date": date, "action": "sell", "reason": "死叉"})
        else:
            signals.append({"date": date, "action": "hold", "reason": ""})
    return signals
'''
