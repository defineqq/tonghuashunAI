"""
strategies — 技术指标策略库
==========================

三档策略能力，都注册到同一个引擎：

1. `preset/`       预置策略：MA 交叉、MACD 金叉等，代码写死
2. 条件构建器      从 JSON 定义（configs/user_strategies/*.yaml）动态生成
3. `user_defined/` 用户提交的 Python 代码，动态 import 后注册

统一接口 TechnicalStrategy：
    - name / description / kind
    - default_params -> dict
    - generate_signals(bars_df, params) -> list of BarSignal
"""

from strategies.base import (  # noqa: F401
    TechnicalStrategy, BarSignal, StrategyKind, StrategyMeta,
)
from strategies.registry import registry  # noqa: F401

__all__ = ["TechnicalStrategy", "BarSignal", "StrategyKind", "StrategyMeta", "registry"]
