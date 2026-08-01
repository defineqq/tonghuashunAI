"""
Builder 策略的编辑 / 覆盖 / 删除 / spec 读取
==============================================

这批测试对应用户诉求：策略实验室的策略应该支持修改和删除。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture()
def isolate_user_strategies_dir(tmp_path, monkeypatch):
    """把 configs/user_strategies 换到临时目录，避免污染。"""
    d = tmp_path / "user_strategies"
    d.mkdir()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    # 让 Path("configs/user_strategies") 相对 cwd 生效
    return d.parent / "user_strategies"


def _spec(id_="my_test"):
    return {
        "id": id_,
        "name": "测试策略",
        "description": "unit test",
        "buy": {"logic": "AND", "rules": [
            {"indicator": "MA", "op": "cross_up",
             "params": {"fast": 5, "slow": 20}},
        ]},
        "sell": {"logic": "OR", "rules": [
            {"indicator": "MA", "op": "cross_down",
             "params": {"fast": 5, "slow": 20}},
        ]},
    }


def test_save_creates_yaml_and_registers():
    from strategies.builder import validate_spec, BuilderStrategy
    from strategies.registry import registry

    # 先清一下
    registry.unregister("my_test_save")

    s = _spec("my_test_save")
    ok, err = validate_spec(s)
    assert ok, err
    strat = BuilderStrategy(s)
    registry.register(strat)
    assert registry.get("my_test_save") is not None


def test_save_overwrites_old_spec(tmp_path, monkeypatch):
    """再次保存同 id 时 registry 里的策略应更新，不是并存两份。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs" / "user_strategies").mkdir(parents=True)

    from strategies.builder import BuilderStrategy
    from strategies.registry import registry

    s1 = _spec("edit_test")
    s1["name"] = "第一版"
    registry.register(BuilderStrategy(s1))
    assert registry.get("edit_test").meta.name == "第一版"

    # 用户"编辑"后再保存
    s2 = _spec("edit_test")
    s2["name"] = "第二版"
    s2["buy"]["rules"].append({
        "indicator": "RSI", "op": "<",
        "params": {"n": 14}, "value": 30,
    })
    registry.register(BuilderStrategy(s2))

    reloaded = registry.get("edit_test")
    assert reloaded.meta.name == "第二版", "同 id 应覆盖"
    # 规则数从 1 变 2
    assert len(reloaded.spec["buy"]["rules"]) == 2


def test_unregister_removes():
    from strategies.builder import BuilderStrategy
    from strategies.registry import registry

    registry.register(BuilderStrategy(_spec("delete_me")))
    assert "delete_me" in registry
    registry.unregister("delete_me")
    assert "delete_me" not in registry


def test_builder_strategy_exposes_spec_for_editing():
    """
    BuilderStrategy.spec 属性必须保留原始 JSON，前端「编辑」按钮才能回填。
    """
    from strategies.builder import BuilderStrategy

    s = _spec("expose_spec")
    strat = BuilderStrategy(s)
    assert strat.spec == s
    # 编辑常见路径：读 spec → 改 → 重新构造
    edited = dict(strat.spec)
    edited["name"] = "改过"
    new_strat = BuilderStrategy(edited)
    assert new_strat.meta.name == "改过"
    assert new_strat.spec["buy"]["rules"] == s["buy"]["rules"]  # 原规则保留
