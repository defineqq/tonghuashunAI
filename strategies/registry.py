"""
策略注册中心
============

一个进程内的单例，按 id 索引所有可用策略（预置 + 用户自定义）。

预置策略：模块被 import 时自动注册（用 @register 装饰器或 class-init）
用户策略：从 configs/user_strategies/*.yaml 或 strategies/user_defined/*.py 动态加载
"""

from __future__ import annotations

from typing import Callable

from strategies.base import TechnicalStrategy, StrategyMeta


class StrategyRegistry:
    def __init__(self):
        self._strategies: dict[str, TechnicalStrategy] = {}

    def register(self, strategy: TechnicalStrategy) -> None:
        if strategy.meta is None:
            raise ValueError(f"策略缺少 meta: {strategy.__class__.__name__}")
        self._strategies[strategy.meta.id] = strategy

    def get(self, strategy_id: str) -> TechnicalStrategy | None:
        return self._strategies.get(strategy_id)

    def list_all(self) -> list[StrategyMeta]:
        return [s.meta for s in self._strategies.values()]

    def list_by_kind(self, kind) -> list[StrategyMeta]:
        return [s.meta for s in self._strategies.values() if s.meta.kind == kind]

    def unregister(self, strategy_id: str) -> None:
        self._strategies.pop(strategy_id, None)

    def __contains__(self, strategy_id: str) -> bool:
        return strategy_id in self._strategies

    def __len__(self) -> int:
        return len(self._strategies)


registry = StrategyRegistry()


def load_all_presets() -> None:
    """import 一次预置模块，触发它们的自注册。幂等。"""
    from strategies.preset import (  # noqa: F401
        ma_cross,
        macd_golden,
        bollinger_bands,
        rsi_reverse,
        kdj_golden,
        turtle_breakout,
        dual_thrust,
        mean_reversion,
        momentum_20,
        triple_screen,
    )


def load_user_strategies() -> None:
    """加载 configs/user_strategies/ 下的 YAML 定义 + strategies/user_defined/ 下的 Python 文件。"""
    from pathlib import Path
    import yaml

    project_root = Path(__file__).resolve().parents[1]
    # YAML 定义（条件构建器产出）
    yaml_dir = project_root / "configs" / "user_strategies"
    if yaml_dir.exists():
        from strategies.builder import BuilderStrategy
        for f in yaml_dir.glob("*.yaml"):
            try:
                spec = yaml.safe_load(f.read_text(encoding="utf-8"))
                strat = BuilderStrategy(spec)
                registry.register(strat)
            except Exception as e:
                print(f"加载 YAML 策略失败 {f.name}: {e}")

    # Python 用户策略
    py_dir = project_root / "strategies" / "user_defined"
    if py_dir.exists():
        from strategies.user_defined_loader import load_user_python
        for f in py_dir.glob("*.py"):
            if f.name.startswith("__"):
                continue
            try:
                strat = load_user_python(f)
                if strat:
                    registry.register(strat)
            except Exception as e:
                print(f"加载 Python 策略失败 {f.name}: {e}")


def bootstrap() -> None:
    """启动时调一次：加载所有策略。"""
    if len(registry) == 0:
        load_all_presets()
    load_user_strategies()
