"""
条件构建器策略
==============

从 JSON/YAML 规格生成策略。用户在 UI 上勾选/填写"如果 X 则买入"这样的规则，
后端保存为 YAML，运行时用 BuilderStrategy 加载。

规格示例：
    {
      "id": "my_ma_macd",
      "name": "我的均线+MACD",
      "buy": {
        "logic": "AND",
        "rules": [
          {"indicator": "MA", "params": {"fast": 5, "slow": 20}, "op": "cross_up"},
          {"indicator": "MACD", "params": {}, "op": "golden_cross"}
        ]
      },
      "sell": {
        "logic": "OR",
        "rules": [
          {"indicator": "MA", "params": {"fast": 5, "slow": 20}, "op": "cross_down"},
          {"indicator": "RSI", "params": {"n": 14}, "op": ">", "value": 75}
        ]
      }
    }
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from strategies.base import (
    TechnicalStrategy, BarSignal, SignalAction,
    StrategyKind, StrategyMeta,
)


# ---- 指标注册 ---------------------------------------------------


INDICATORS: dict[str, dict[str, Any]] = {
    "MA": {
        "label": "移动均线 MA",
        "params": [
            {"name": "fast", "label": "快线周期", "type": "int", "default": 5, "min": 2, "max": 60},
            {"name": "slow", "label": "慢线周期", "type": "int", "default": 20, "min": 5, "max": 250},
        ],
        "ops": [
            {"name": "cross_up", "label": "快线上穿慢线（金叉）", "value_type": "none"},
            {"name": "cross_down", "label": "快线下穿慢线（死叉）", "value_type": "none"},
            {"name": "price_above", "label": "股价高于慢线", "value_type": "none"},
            {"name": "price_below", "label": "股价低于慢线", "value_type": "none"},
        ],
    },
    "MACD": {
        "label": "MACD",
        "params": [
            {"name": "fast", "label": "快线", "type": "int", "default": 12, "min": 2, "max": 30},
            {"name": "slow", "label": "慢线", "type": "int", "default": 26, "min": 5, "max": 60},
            {"name": "signal", "label": "信号线", "type": "int", "default": 9, "min": 2, "max": 20},
        ],
        "ops": [
            {"name": "golden_cross", "label": "金叉（DIF 上穿 DEA）", "value_type": "none"},
            {"name": "death_cross", "label": "死叉（DIF 下穿 DEA）", "value_type": "none"},
            {"name": "dif_above_zero", "label": "DIF 上穿零轴", "value_type": "none"},
            {"name": "dif_below_zero", "label": "DIF 下穿零轴", "value_type": "none"},
        ],
    },
    "RSI": {
        "label": "RSI 相对强弱",
        "params": [
            {"name": "n", "label": "周期", "type": "int", "default": 14, "min": 5, "max": 30},
        ],
        "ops": [
            {"name": ">", "label": "大于", "value_type": "number", "value_default": 70},
            {"name": "<", "label": "小于", "value_type": "number", "value_default": 30},
            {"name": "cross_up", "label": "上穿数值", "value_type": "number", "value_default": 30},
            {"name": "cross_down", "label": "下穿数值", "value_type": "number", "value_default": 70},
        ],
    },
    "KDJ": {
        "label": "KDJ",
        "params": [
            {"name": "n", "label": "周期", "type": "int", "default": 9, "min": 5, "max": 30},
        ],
        "ops": [
            {"name": "golden_cross", "label": "金叉（K 上穿 D）", "value_type": "none"},
            {"name": "death_cross", "label": "死叉（K 下穿 D）", "value_type": "none"},
            {"name": "k>", "label": "K 大于", "value_type": "number", "value_default": 80},
            {"name": "k<", "label": "K 小于", "value_type": "number", "value_default": 20},
        ],
    },
    "BOLL": {
        "label": "布林带",
        "params": [
            {"name": "n", "label": "周期", "type": "int", "default": 20, "min": 5, "max": 60},
            {"name": "std_mult", "label": "标准差倍数", "type": "float", "default": 2.0, "min": 1.0, "max": 3.0},
        ],
        "ops": [
            {"name": "touch_lower", "label": "跌破下轨", "value_type": "none"},
            {"name": "touch_upper", "label": "突破上轨", "value_type": "none"},
        ],
    },
    "PRICE_PCT": {
        "label": "价格涨跌幅",
        "params": [
            {"name": "n", "label": "对比周期（日）", "type": "int", "default": 20, "min": 1, "max": 250},
        ],
        "ops": [
            {"name": ">", "label": "涨幅大于 %", "value_type": "number", "value_default": 5.0},
            {"name": "<", "label": "跌幅大于 %（数字为负）", "value_type": "number", "value_default": -3.0},
        ],
    },
    "VOLUME_RATIO": {
        "label": "量比",
        "params": [
            {"name": "n", "label": "对比周期", "type": "int", "default": 20, "min": 5, "max": 60},
        ],
        "ops": [
            {"name": ">", "label": "近 5 日均量 / 近 N 日均量 大于", "value_type": "number", "value_default": 1.5},
            {"name": "<", "label": "近 5 日均量 / 近 N 日均量 小于", "value_type": "number", "value_default": 0.7},
        ],
    },
}


def list_indicators() -> list[dict]:
    """给前端渲染用：所有可选指标和它们的 ops、参数。"""
    return [
        {"key": k, **v}
        for k, v in INDICATORS.items()
    ]


# ---- 规则求值 ---------------------------------------------------


def _eval_rule(bars: pd.DataFrame, rule: dict) -> pd.Series:
    """
    评估单条规则，返回一个 boolean Series（每根 K 线是否满足）。
    """
    ind = rule["indicator"]
    op = rule["op"]
    ps = rule.get("params", {}) or {}
    value = rule.get("value")

    close = bars["close"]

    if ind == "MA":
        fast = TechnicalStrategy.sma(close, int(ps.get("fast", 5)))
        slow = TechnicalStrategy.sma(close, int(ps.get("slow", 20)))
        if op == "cross_up":
            return TechnicalStrategy.cross_up(fast, slow)
        if op == "cross_down":
            return TechnicalStrategy.cross_down(fast, slow)
        if op == "price_above":
            return close > slow
        if op == "price_below":
            return close < slow

    elif ind == "MACD":
        dif, dea, _ = TechnicalStrategy.macd(close, int(ps.get("fast", 12)),
                                              int(ps.get("slow", 26)), int(ps.get("signal", 9)))
        if op == "golden_cross":
            return TechnicalStrategy.cross_up(dif, dea)
        if op == "death_cross":
            return TechnicalStrategy.cross_down(dif, dea)
        if op == "dif_above_zero":
            return TechnicalStrategy.cross_up(dif, pd.Series(0, index=dif.index))
        if op == "dif_below_zero":
            return TechnicalStrategy.cross_down(dif, pd.Series(0, index=dif.index))

    elif ind == "RSI":
        r = TechnicalStrategy.rsi(close, int(ps.get("n", 14)))
        if op == ">":
            return r > float(value)
        if op == "<":
            return r < float(value)
        if op == "cross_up":
            return (r > float(value)) & (r.shift() <= float(value))
        if op == "cross_down":
            return (r < float(value)) & (r.shift() >= float(value))

    elif ind == "KDJ":
        k, d, _ = TechnicalStrategy.kdj(bars["high"], bars["low"], close, int(ps.get("n", 9)))
        if op == "golden_cross":
            return TechnicalStrategy.cross_up(k, d)
        if op == "death_cross":
            return TechnicalStrategy.cross_down(k, d)
        if op == "k>":
            return k > float(value)
        if op == "k<":
            return k < float(value)

    elif ind == "BOLL":
        upper, mid, lower = TechnicalStrategy.bollinger(close, int(ps.get("n", 20)), float(ps.get("std_mult", 2.0)))
        if op == "touch_lower":
            return (close < lower) & (close.shift() >= lower.shift())
        if op == "touch_upper":
            return (close > upper) & (close.shift() <= upper.shift())

    elif ind == "PRICE_PCT":
        ret = close.pct_change(int(ps.get("n", 20))) * 100
        if op == ">":
            return ret > float(value)
        if op == "<":
            return ret < float(value)

    elif ind == "VOLUME_RATIO":
        vol = bars["volume"]
        ratio = vol.rolling(5).mean() / vol.rolling(int(ps.get("n", 20))).mean().replace(0, 1e-9)
        if op == ">":
            return ratio > float(value)
        if op == "<":
            return ratio < float(value)

    # 未知规则：全 False
    return pd.Series(False, index=close.index)


def _eval_group(bars: pd.DataFrame, group: dict) -> pd.Series:
    """求值一个规则组（AND/OR）。"""
    rules = group.get("rules", [])
    if not rules:
        return pd.Series(False, index=bars.index)
    results = [_eval_rule(bars, r) for r in rules]
    logic = group.get("logic", "AND").upper()
    if logic == "OR":
        out = results[0]
        for r in results[1:]:
            out = out | r
        return out
    else:  # AND
        out = results[0]
        for r in results[1:]:
            out = out & r
        return out


# ---- 策略类 -----------------------------------------------------


class BuilderStrategy(TechnicalStrategy):
    """从 JSON 规格生成的策略。"""

    def __init__(self, spec: dict):
        self.spec = spec
        self.meta = StrategyMeta(
            id=spec.get("id", "user_" + spec.get("name", "unnamed")),
            name=spec.get("name", "自定义策略"),
            kind=StrategyKind.BUILDER,
            category="自定义",
            description=spec.get("description", "用户在构建器中创建的策略"),
            long_description=self._render_description(),
            tags=["自定义", "条件构建"],
        )

    def _render_description(self) -> str:
        lines = ["**买入条件**：\n"]
        buy = self.spec.get("buy", {})
        lines.append(f"- 逻辑：{buy.get('logic', 'AND')}")
        for r in buy.get("rules", []):
            lines.append(f"  - {r.get('indicator')} {r.get('op')} {r.get('value','')}")
        lines.append("\n**卖出条件**：\n")
        sell = self.spec.get("sell", {})
        lines.append(f"- 逻辑：{sell.get('logic', 'OR')}")
        for r in sell.get("rules", []):
            lines.append(f"  - {r.get('indicator')} {r.get('op')} {r.get('value','')}")
        return "\n".join(lines)

    def generate_signals(self, bars: pd.DataFrame, params: dict | None = None) -> list[BarSignal]:
        buy_hits = _eval_group(bars, self.spec.get("buy", {}))
        sell_hits = _eval_group(bars, self.spec.get("sell", {}))
        signals = []
        for i, date in enumerate(bars["date"]):
            if bool(buy_hits.iloc[i]):
                signals.append(BarSignal(date, SignalAction.BUY, "自定义买入条件满足"))
            elif bool(sell_hits.iloc[i]):
                signals.append(BarSignal(date, SignalAction.SELL, "自定义卖出条件满足"))
            else:
                signals.append(BarSignal(date, SignalAction.HOLD, ""))
        return signals


def validate_spec(spec: dict) -> tuple[bool, str]:
    """校验规格 JSON 是否合法。返回 (ok, error_msg)。"""
    if not spec.get("id"):
        return False, "缺少 id"
    if not spec.get("name"):
        return False, "缺少 name"
    for side in ("buy", "sell"):
        g = spec.get(side)
        if not g:
            return False, f"缺少 {side} 条件"
        if g.get("logic") not in ("AND", "OR"):
            return False, f"{side}.logic 必须是 AND 或 OR"
        rules = g.get("rules", [])
        if not rules:
            return False, f"{side} 至少要一条规则"
        for r in rules:
            ind = r.get("indicator")
            if ind not in INDICATORS:
                return False, f"未知指标 {ind}"
            op = r.get("op")
            valid_ops = {o["name"] for o in INDICATORS[ind]["ops"]}
            if op not in valid_ops:
                return False, f"{ind} 不支持操作 {op}"
    return True, ""
