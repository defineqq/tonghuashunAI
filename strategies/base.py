"""
策略基类与信号定义
==================

设计原则：
- 策略 = **一个纯函数**：吃日线 DataFrame + 参数 → 吐买卖信号
- 不管账户状态、不管仓位管理（那些交给上层 broker + risk）
- 信号是**每根 K 线一个** buy/sell/hold，让回测引擎决定"要不要真的买"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import pandas as pd


class StrategyKind(str, Enum):
    PRESET = "preset"           # 预置库
    BUILDER = "builder"         # 条件构建器生成
    PYTHON = "python"           # 用户 Python 代码


class SignalAction(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class BarSignal:
    """每根 K 线的信号。"""
    date: pd.Timestamp
    action: SignalAction
    reason: str = ""


@dataclass
class StrategyParam:
    """策略参数元信息（前端渲染用）。"""
    name: str                       # 参数名（Python 变量名）
    label: str                      # 显示名（中文）
    type: str                       # int | float | select
    default: Any
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: list[Any] | None = None   # type == select 时
    help: str = ""                  # tooltip


@dataclass
class StrategyMeta:
    """策略元信息（列表页 + 详情页用）。"""
    id: str                         # 唯一 ID
    name: str                       # 显示名
    kind: StrategyKind
    category: str                   # 趋势 / 震荡 / 突破 / 均值回归 / 综合
    description: str                # 一句话描述
    long_description: str = ""      # 详细说明（Markdown）
    params: list[StrategyParam] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


class TechnicalStrategy:
    """
    技术指标策略抽象基类。子类必须实现 generate_signals()。

    使用方式（预置策略）：
        class MACrossStrategy(TechnicalStrategy):
            meta = StrategyMeta(...)
            def generate_signals(self, bars, params):
                ...
    """

    meta: StrategyMeta = None  # type: ignore

    def default_params(self) -> dict[str, Any]:
        """从 meta 里推导默认参数。"""
        if self.meta is None:
            return {}
        return {p.name: p.default for p in self.meta.params}

    def generate_signals(
        self,
        bars: pd.DataFrame,
        params: dict[str, Any] | None = None,
    ) -> list[BarSignal]:
        """
        对一段日线数据生成信号。

        Args:
            bars: 有 date/open/high/low/close/volume 列的 DataFrame，按日期升序
            params: 策略参数（覆盖 default_params）

        Returns:
            list[BarSignal]，每个元素对应一根 K 线的动作
        """
        raise NotImplementedError

    # ---- 便捷方法：让子类共享指标计算 ----

    @staticmethod
    def sma(series: pd.Series, n: int) -> pd.Series:
        return series.rolling(n, min_periods=1).mean()

    @staticmethod
    def ema(series: pd.Series, n: int) -> pd.Series:
        return series.ewm(span=n, adjust=False).mean()

    @staticmethod
    def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal, adjust=False).mean()
        macd_hist = 2 * (dif - dea)
        return dif, dea, macd_hist

    @staticmethod
    def rsi(close: pd.Series, n: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(n).mean()
        loss = (-delta.clip(upper=0)).rolling(n).mean()
        rs = gain / loss.replace(0, 1e-9)
        return 100 - 100 / (1 + rs)

    @staticmethod
    def kdj(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9):
        """9 日 KDJ。"""
        low_min = low.rolling(n).min()
        high_max = high.rolling(n).max()
        rsv = (close - low_min) / (high_max - low_min).replace(0, 1e-9) * 100
        k = rsv.ewm(alpha=1/3, adjust=False).mean()
        d = k.ewm(alpha=1/3, adjust=False).mean()
        j = 3 * k - 2 * d
        return k, d, j

    @staticmethod
    def bollinger(close: pd.Series, n: int = 20, std_mult: float = 2.0):
        mid = close.rolling(n).mean()
        std = close.rolling(n).std()
        upper = mid + std_mult * std
        lower = mid - std_mult * std
        return upper, mid, lower

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
        tr = pd.concat([
            (high - low).abs(),
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(n).mean()

    @staticmethod
    def cross_up(fast: pd.Series, slow: pd.Series) -> pd.Series:
        """fast 上穿 slow 的位置返回 True。"""
        return (fast > slow) & (fast.shift() <= slow.shift())

    @staticmethod
    def cross_down(fast: pd.Series, slow: pd.Series) -> pd.Series:
        return (fast < slow) & (fast.shift() >= slow.shift())
