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
    # ---- 均线家族补充 ----
    "EMA": {
        "label": "指数均线 EMA",
        "params": [
            {"name": "fast", "label": "快线", "type": "int", "default": 5, "min": 2, "max": 60},
            {"name": "slow", "label": "慢线", "type": "int", "default": 20, "min": 5, "max": 250},
        ],
        "ops": [
            {"name": "cross_up", "label": "快线上穿慢线（金叉）", "value_type": "none"},
            {"name": "cross_down", "label": "快线下穿慢线（死叉）", "value_type": "none"},
            {"name": "price_above", "label": "股价高于慢线", "value_type": "none"},
            {"name": "price_below", "label": "股价低于慢线", "value_type": "none"},
        ],
    },
    "MA_ARRANGE": {
        "label": "均线排列",
        "params": [
            {"name": "short", "label": "短周期", "type": "int", "default": 5, "min": 2, "max": 60},
            {"name": "mid",   "label": "中周期", "type": "int", "default": 20, "min": 5, "max": 120},
            {"name": "long",  "label": "长周期", "type": "int", "default": 60, "min": 10, "max": 250},
        ],
        "ops": [
            {"name": "bull", "label": "多头排列（短>中>长）", "value_type": "none"},
            {"name": "bear", "label": "空头排列（短<中<长）", "value_type": "none"},
        ],
    },
    # ---- 成交量 / 成交额 / 换手 ----
    "VOLUME": {
        "label": "成交量",
        "params": [
            {"name": "n", "label": "对比均量周期", "type": "int", "default": 20, "min": 3, "max": 120},
        ],
        "ops": [
            {"name": "surge",    "label": "放量：当日量 > N 日均量 × 倍数", "value_type": "number", "value_default": 2.0},
            {"name": "shrink",   "label": "缩量：当日量 < N 日均量 × 倍数", "value_type": "number", "value_default": 0.5},
            {"name": "abs>",     "label": "当日绝对量（手）大于", "value_type": "number", "value_default": 1_000_000},
            {"name": "abs<",     "label": "当日绝对量（手）小于", "value_type": "number", "value_default": 100_000},
        ],
    },
    "AMOUNT": {
        "label": "成交额",
        "params": [
            {"name": "n", "label": "对比均额周期", "type": "int", "default": 20, "min": 3, "max": 120},
        ],
        "ops": [
            {"name": "abs>",     "label": "成交额（亿元）大于", "value_type": "number", "value_default": 5.0},
            {"name": "abs<",     "label": "成交额（亿元）小于", "value_type": "number", "value_default": 0.5},
            {"name": "ratio>",   "label": "成交额 / N 日均额 大于", "value_type": "number", "value_default": 1.5},
            {"name": "ratio<",   "label": "成交额 / N 日均额 小于", "value_type": "number", "value_default": 0.7},
        ],
    },
    "TURNOVER": {
        "label": "换手率",
        "params": [],
        "ops": [
            {"name": ">",  "label": "换手率（%）大于", "value_type": "number", "value_default": 5.0},
            {"name": "<",  "label": "换手率（%）小于", "value_type": "number", "value_default": 1.0},
            {"name": "in", "label": "换手率处于健康区（1%-8%）", "value_type": "none"},
        ],
    },
    # ---- 摆动指标 ----
    "WR": {
        "label": "威廉指标 WR",
        "params": [
            {"name": "n", "label": "周期", "type": "int", "default": 14, "min": 5, "max": 30},
        ],
        "ops": [
            {"name": ">",         "label": "WR 大于（超卖偏离，注意 WR 反向）", "value_type": "number", "value_default": -20},
            {"name": "<",         "label": "WR 小于（超买）", "value_type": "number", "value_default": -80},
            {"name": "cross_up",  "label": "WR 上穿数值", "value_type": "number", "value_default": -80},
            {"name": "cross_down","label": "WR 下穿数值", "value_type": "number", "value_default": -20},
        ],
    },
    "CCI": {
        "label": "顺势指标 CCI",
        "params": [
            {"name": "n", "label": "周期", "type": "int", "default": 14, "min": 5, "max": 30},
        ],
        "ops": [
            {"name": ">", "label": "CCI 大于（超买）", "value_type": "number", "value_default": 100},
            {"name": "<", "label": "CCI 小于（超卖）", "value_type": "number", "value_default": -100},
            {"name": "cross_up",   "label": "CCI 上穿数值", "value_type": "number", "value_default": -100},
            {"name": "cross_down", "label": "CCI 下穿数值", "value_type": "number", "value_default": 100},
        ],
    },
    # ---- 能量潮 / 趋势强度 ----
    "OBV": {
        "label": "能量潮 OBV",
        "params": [
            {"name": "n", "label": "对比均线周期", "type": "int", "default": 30, "min": 5, "max": 120},
        ],
        "ops": [
            {"name": "cross_up",   "label": "OBV 上穿均线（资金转多）", "value_type": "none"},
            {"name": "cross_down", "label": "OBV 下穿均线（资金转空）", "value_type": "none"},
        ],
    },
    "ADX": {
        "label": "趋势强度 ADX",
        "params": [
            {"name": "n", "label": "周期", "type": "int", "default": 14, "min": 5, "max": 30},
        ],
        "ops": [
            {"name": ">", "label": "ADX 大于（趋势明确）", "value_type": "number", "value_default": 25},
            {"name": "<", "label": "ADX 小于（震荡）", "value_type": "number", "value_default": 20},
        ],
    },
    # ---- 突破 / K 线形态 ----
    "HIGH_LOW_N": {
        "label": "N 日新高/新低",
        "params": [
            {"name": "n", "label": "回看天数", "type": "int", "default": 20, "min": 5, "max": 250},
        ],
        "ops": [
            {"name": "new_high", "label": "今收创 N 日新高", "value_type": "none"},
            {"name": "new_low",  "label": "今收创 N 日新低", "value_type": "none"},
        ],
    },
    "CONSEC": {
        "label": "连续阳/阴线",
        "params": [],
        "ops": [
            {"name": "up>=", "label": "连续阳线不少于 N 根", "value_type": "number", "value_default": 3},
            {"name": "dn>=", "label": "连续阴线不少于 N 根", "value_type": "number", "value_default": 3},
        ],
    },
    "GAP": {
        "label": "跳空缺口",
        "params": [],
        "ops": [
            {"name": "up>",   "label": "向上跳空幅度（%）大于", "value_type": "number", "value_default": 2.0},
            {"name": "down>", "label": "向下跳空幅度（%）大于", "value_type": "number", "value_default": 2.0},
        ],
    },
    "LIMIT": {
        "label": "涨跌停",
        "params": [],
        "ops": [
            {"name": "up",   "label": "涨停（涨幅 ≥ 9.5%）", "value_type": "none"},
            {"name": "down", "label": "跌停（跌幅 ≥ 9.5%）", "value_type": "none"},
        ],
    },
    # ---- 筹码分布（用 VWAP 代理） ----
    "CHIP": {
        "label": "筹码分布 (VWAP 代理)",
        "params": [
            {"name": "n", "label": "回看天数", "type": "int", "default": 60, "min": 20, "max": 250},
        ],
        "ops": [
            {"name": "profit>", "label": "获利盘（收盘价高于 N 日 VWAP 的天数比例）大于 %", "value_type": "number", "value_default": 80},
            {"name": "trap>",   "label": "套牢盘（收盘价低于 N 日 VWAP 的天数比例）大于 %", "value_type": "number", "value_default": 80},
            {"name": "concentration>", "label": "筹码集中度（当前价 ±5% 内 VWAP 天数比例）大于 %", "value_type": "number", "value_default": 30},
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


def _wr(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    """威廉指标 %R。取值 [-100, 0]，越靠 0 越超买。"""
    hh = high.rolling(n).max()
    ll = low.rolling(n).min()
    return (hh - close) / (hh - ll).replace(0, 1e-9) * -100


def _cci(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    tp = (high + low + close) / 3.0
    ma = tp.rolling(n).mean()
    md = (tp - ma).abs().rolling(n).mean()
    return (tp - ma) / (0.015 * md.replace(0, 1e-9))


def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (volume * direction).fillna(0).cumsum()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    up = high.diff()
    down = -low.diff()
    plus_dm  = ((up > down) & (up > 0)).astype(float) * up.clip(lower=0)
    minus_dm = ((down > up) & (down > 0)).astype(float) * down.clip(lower=0)
    tr = pd.concat([
        (high - low).abs(),
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(n).mean().replace(0, 1e-9)
    plus_di  = 100 * plus_dm.rolling(n).mean() / atr
    minus_di = 100 * minus_dm.rolling(n).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    return dx.rolling(n).mean()


def _pct_change_col(bars: pd.DataFrame) -> pd.Series:
    """优先用行情自带的涨跌幅，若无则从 close 差分计算。"""
    if "pct_change" in bars.columns:
        return pd.to_numeric(bars["pct_change"], errors="coerce")
    return bars["close"].pct_change() * 100


def _eval_rule(bars: pd.DataFrame, rule: dict) -> pd.Series:
    """
    评估单条规则，返回一个 boolean Series（每根 K 线是否满足）。
    """
    ind = rule["indicator"]
    op = rule["op"]
    ps = rule.get("params", {}) or {}
    value = rule.get("value")

    close = bars["close"]
    high  = bars.get("high", close)
    low   = bars.get("low", close)
    vol   = bars.get("volume", pd.Series(0, index=close.index))
    amt   = bars.get("amount", pd.Series(0, index=close.index))
    tor   = bars.get("turnover_rate", pd.Series(pd.NA, index=close.index))

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
        ratio = vol.rolling(5).mean() / vol.rolling(int(ps.get("n", 20))).mean().replace(0, 1e-9)
        if op == ">":
            return ratio > float(value)
        if op == "<":
            return ratio < float(value)

    elif ind == "EMA":
        fast = TechnicalStrategy.ema(close, int(ps.get("fast", 5)))
        slow = TechnicalStrategy.ema(close, int(ps.get("slow", 20)))
        if op == "cross_up":     return TechnicalStrategy.cross_up(fast, slow)
        if op == "cross_down":   return TechnicalStrategy.cross_down(fast, slow)
        if op == "price_above":  return close > slow
        if op == "price_below":  return close < slow

    elif ind == "MA_ARRANGE":
        short = TechnicalStrategy.sma(close, int(ps.get("short", 5)))
        mid   = TechnicalStrategy.sma(close, int(ps.get("mid", 20)))
        long_ = TechnicalStrategy.sma(close, int(ps.get("long", 60)))
        if op == "bull": return (short > mid) & (mid > long_)
        if op == "bear": return (short < mid) & (mid < long_)

    elif ind == "VOLUME":
        n = int(ps.get("n", 20))
        avg = vol.rolling(n).mean().replace(0, 1e-9)
        if op == "surge":  return vol > avg * float(value)
        if op == "shrink": return vol < avg * float(value)
        if op == "abs>":   return vol > float(value)
        if op == "abs<":   return vol < float(value)

    elif ind == "AMOUNT":
        n = int(ps.get("n", 20))
        # 数据里成交额单位是元；用户输入的绝对阈值是亿元，因此乘 1e8
        if op == "abs>":   return amt > float(value) * 1e8
        if op == "abs<":   return amt < float(value) * 1e8
        avg = amt.rolling(n).mean().replace(0, 1e-9)
        if op == "ratio>": return amt / avg > float(value)
        if op == "ratio<": return amt / avg < float(value)

    elif ind == "TURNOVER":
        t = pd.to_numeric(tor, errors="coerce")
        if op == ">":  return t > float(value)
        if op == "<":  return t < float(value)
        if op == "in": return (t >= 1.0) & (t <= 8.0)

    elif ind == "WR":
        w = _wr(high, low, close, int(ps.get("n", 14)))
        v = float(value) if value is not None else -50
        if op == ">":         return w > v
        if op == "<":         return w < v
        if op == "cross_up":  return (w > v) & (w.shift() <= v)
        if op == "cross_down":return (w < v) & (w.shift() >= v)

    elif ind == "CCI":
        c = _cci(high, low, close, int(ps.get("n", 14)))
        v = float(value) if value is not None else 100
        if op == ">":         return c > v
        if op == "<":         return c < v
        if op == "cross_up":  return (c > v) & (c.shift() <= v)
        if op == "cross_down":return (c < v) & (c.shift() >= v)

    elif ind == "OBV":
        obv = _obv(close, vol)
        obv_ma = obv.rolling(int(ps.get("n", 30))).mean()
        if op == "cross_up":   return TechnicalStrategy.cross_up(obv, obv_ma)
        if op == "cross_down": return TechnicalStrategy.cross_down(obv, obv_ma)

    elif ind == "ADX":
        a = _adx(high, low, close, int(ps.get("n", 14)))
        if op == ">": return a > float(value)
        if op == "<": return a < float(value)

    elif ind == "HIGH_LOW_N":
        n = int(ps.get("n", 20))
        hh = close.rolling(n).max()
        ll = close.rolling(n).min()
        if op == "new_high": return close >= hh
        if op == "new_low":  return close <= ll

    elif ind == "CONSEC":
        up = (close.diff() > 0).astype(int)
        dn = (close.diff() < 0).astype(int)
        # 累计连续为真的天数：break-on-zero cumsum trick
        def _run_length(flag: pd.Series) -> pd.Series:
            grp = (flag == 0).cumsum()
            return flag.groupby(grp).cumsum()
        if op == "up>=": return _run_length(up) >= int(float(value))
        if op == "dn>=": return _run_length(dn) >= int(float(value))

    elif ind == "GAP":
        prev_close = close.shift()
        open_ = bars.get("open", close)
        gap_pct = (open_ - prev_close) / prev_close.replace(0, 1e-9) * 100
        if op == "up>":   return gap_pct >  float(value)
        if op == "down>": return gap_pct < -float(value)

    elif ind == "LIMIT":
        pct = _pct_change_col(bars)
        if op == "up":   return pct >=  9.5
        if op == "down": return pct <= -9.5

    elif ind == "CHIP":
        # 用 VWAP 序列近似筹码分布：每天一个 VWAP，看 N 日窗口内各天 VWAP 相对今日价的分布
        n = int(ps.get("n", 60))
        vwap_day = (amt / vol.replace(0, 1e-9)).where(vol > 0, close)
        # 每一根 K 线求「过去 n 天 VWAP 中，位于阈值区间的比例」
        v = float(value) / 100 if value is not None else 0.5  # 用户输入是百分数
        cur = close
        # 用 rolling apply 太慢，用广播算比例
        # 构造滚动窗口的 VWAP 二维数据不划算，改为逐位置：小 n(≤250) 且 A 股序列不长，可接受
        def _ratio(mode: str) -> pd.Series:
            out = pd.Series(0.0, index=close.index)
            v_arr = vwap_day.values
            c_arr = cur.values
            for i in range(len(close)):
                if i < n:
                    out.iat[i] = 0.0
                    continue
                window = v_arr[i - n + 1: i + 1]
                total = len(window)
                if total == 0:
                    continue
                c = c_arr[i]
                if mode == "profit":
                    out.iat[i] = float((window < c).sum()) / total
                elif mode == "trap":
                    out.iat[i] = float((window > c).sum()) / total
                elif mode == "concentration":
                    lo, hi = c * 0.95, c * 1.05
                    out.iat[i] = float(((window >= lo) & (window <= hi)).sum()) / total
            return out
        if op == "profit>":         return _ratio("profit") > v
        if op == "trap>":           return _ratio("trap") > v
        if op == "concentration>":  return _ratio("concentration") > v

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
