"""
AI Agent 循环：让 LLM 自主调用回测工具直到达成用户目标
======================================================

流程：
    1. 用户描述目标：如"半年内找一个累计收益 > 100% 的策略"
    2. Agent 每轮读上下文 → 返回 JSON action → 后端执行 → 结果回灌
    3. 循环直到 LLM 主动 finish 或到达上限
    4. 结果写入 logs/agent_tasks/{task_id}.json，前端轮询

设计原则：
    - 不依赖 LLM 原生 tool-calling API（Claude/OpenAI/DeepSeek 三家 SDK 都不同）
      用 JSON-only 输出让三家都能跑
    - 每一步都持久化，中途崩溃/停止不影响已完成的实验
    - 后台线程运行，前端 poll /api/agent/{task_id} 拿实时状态
"""

from __future__ import annotations

import json
import re
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Optional

from ai_analysis.llm_client import chat, current_provider


# 项目根：无论 CWD 如何都能定位到 logs / configs
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = PROJECT_ROOT / "logs" / "agent_tasks"
TASKS_DIR.mkdir(parents=True, exist_ok=True)
_LOCK = Lock()

_PROMPT_TMPL = (Path(__file__).parent / "prompts" / "agent_action.md").read_text(encoding="utf-8")


# ---- 数据结构 ------------------------------------------------------


@dataclass
class Step:
    """单轮：LLM 决策 → 工具结果。"""
    idx: int
    at: str
    action: str
    args: dict[str, Any]
    reason: str
    result: dict[str, Any] | None = None   # 成功时的 payload
    error: str | None = None               # 失败时的错误信息
    duration_ms: int = 0


@dataclass
class AgentTask:
    task_id: str
    goal: str
    max_iterations: int
    started_at: str
    status: str = "running"     # running | done | failed | cancelled
    steps: list[Step] = field(default_factory=list)
    finished_at: str | None = None
    final: dict[str, Any] | None = None
    error: str | None = None
    provider: str = "stub"

    def path(self) -> Path:
        return TASKS_DIR / f"{self.task_id}.json"

    def save(self):
        with _LOCK:
            data = {
                **asdict(self),
                "steps": [asdict(s) for s in self.steps],
            }
            self.path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, task_id: str) -> Optional["AgentTask"]:
        p = TASKS_DIR / f"{task_id}.json"
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        steps = [Step(**s) for s in d.pop("steps", [])]
        t = cls(**d)
        t.steps = steps
        return t


# ---- Action registry ----------------------------------------------


def _action_list_strategies(args: dict) -> dict:
    from strategies.registry import registry, bootstrap
    bootstrap()
    metas = registry.list_all()
    return {
        "strategies": [
            {
                "id": m.id,
                "name": m.name,
                "kind": m.kind.value,
                "category": m.category,
                "params": [
                    {"name": p.name, "default": p.default,
                     "min": p.min, "max": p.max}
                    for p in m.params
                ],
            }
            for m in metas
        ],
    }


def _action_backtest_score(args: dict) -> dict:
    from data_layer import universe as uni
    from backtest import engine
    from my_strategies import swing_v1
    from web.api.routes import PRESET_WEIGHTS, PRESET_LABELS

    fn_map = {
        "000300": uni.hs300_constituents,
        "000905": uni.csi500_constituents,
        "000852": uni.csi1000_constituents,
    }
    pool = args.get("pool", "000300")
    if pool not in fn_map:
        raise ValueError(f"unsupported pool: {pool}")
    df_idx = fn_map[pool]()
    code_col = next((c for c in df_idx.columns if "成分券代码" in c), None) \
        or next((c for c in df_idx.columns if "代码" in c and "指数" not in c), None)
    symbols = [str(x).zfill(6) for x in df_idx[code_col].tolist()]
    limit = int(args.get("limit", 20))
    symbols = symbols[:limit]

    preset = args.get("preset", "balanced")
    weights = PRESET_WEIGHTS.get(preset, PRESET_WEIGHTS["balanced"])

    result = engine.run(
        strategy_fn=swing_v1.generate_signals,
        universe=symbols,
        start=args["start"],
        end=args["end"],
        initial_cash=100_000,
        strategy_kwargs={
            "min_score": float(args.get("min_score", 60)),
            "use_llm": False,
            "weights": weights,
        },
    )
    return {
        "metrics": result["metrics"],
        "trades_count": len(result["portfolio"].trades),
        "config": {
            "strategy_type": "score", "preset": preset,
            "preset_name": PRESET_LABELS.get(preset, {}).get("name", preset),
            "start": args["start"], "end": args["end"],
            "pool": pool, "limit": limit, "min_score": args.get("min_score", 60),
            "weights": weights,
        },
    }


def _action_backtest_technical(args: dict) -> dict:
    from data_layer import universe as uni
    from backtest import engine
    from strategies.adapter import make_strategy_fn
    from strategies.registry import bootstrap
    bootstrap()

    fn_map = {
        "000300": uni.hs300_constituents,
        "000905": uni.csi500_constituents,
        "000852": uni.csi1000_constituents,
    }
    pool = args.get("pool", "000300")
    if pool not in fn_map:
        raise ValueError(f"unsupported pool: {pool}")
    df_idx = fn_map[pool]()
    code_col = next((c for c in df_idx.columns if "成分券代码" in c), None) \
        or next((c for c in df_idx.columns if "代码" in c and "指数" not in c), None)
    symbols = [str(x).zfill(6) for x in df_idx[code_col].tolist()]
    limit = int(args.get("limit", 20))
    symbols = symbols[:limit]

    strategy_id = args["strategy_id"]
    strategy_params = args.get("strategy_params", {}) or {}
    strategy_fn = make_strategy_fn(strategy_id, params=strategy_params,
                                    position_size=float(args.get("position_size", 0.18)))
    result = engine.run(
        strategy_fn=strategy_fn,
        universe=symbols,
        start=args["start"],
        end=args["end"],
        initial_cash=100_000,
        strategy_kwargs={},
    )
    return {
        "metrics": result["metrics"],
        "trades_count": len(result["portfolio"].trades),
        "config": {
            "strategy_type": "technical", "strategy_id": strategy_id,
            "strategy_params": strategy_params,
            "start": args["start"], "end": args["end"],
            "pool": pool, "limit": limit,
        },
    }


def _action_create_strategy(args: dict) -> dict:
    from ai_analysis.builder_ai import generate_spec
    from strategies.builder import BuilderStrategy
    from strategies.registry import registry
    import yaml as _yaml

    r = generate_spec(
        user_prompt=args["prompt"],
        suggested_id=args.get("suggested_id"),
        suggested_name=args.get("suggested_name"),
    )
    spec = r["spec"]
    out = Path("configs/user_strategies") / f"{spec['id']}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    registry.register(BuilderStrategy(spec))
    return {
        "strategy_id": spec["id"],
        "name": spec["name"],
        "provider": r["provider"],
        "notes": r.get("notes"),
    }


ACTIONS = {
    "list_strategies": _action_list_strategies,
    "backtest_score": _action_backtest_score,
    "backtest_technical": _action_backtest_technical,
    "create_strategy_from_text": _action_create_strategy,
}


# ---- LLM prompt / JSON 抽取 ---------------------------------------


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text).rstrip("`").rstrip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def _render_history(steps: list[Step]) -> str:
    if not steps:
        return "(还没有跑过实验)"
    lines = []
    for s in steps:
        head = f"- 第 {s.idx} 轮 · action={s.action}"
        if s.error:
            lines.append(f"{head} · ❌ 错误：{s.error[:200]}")
            continue
        if s.action in ("backtest_score", "backtest_technical") and s.result:
            m = s.result.get("metrics", {})
            cfg = s.result.get("config", {})
            summary = (
                f"累计 {m.get('cumulative_return', 0)*100:.1f}% · "
                f"年化 {m.get('annualized_return', 0)*100:.1f}% · "
                f"回撤 {m.get('max_drawdown', 0)*100:.1f}% · "
                f"夏普 {m.get('sharpe', 0):.2f} · 成交 {s.result.get('trades_count', 0)} 笔"
            )
            cfg_summary = json.dumps({k: v for k, v in cfg.items() if k != "weights"},
                                     ensure_ascii=False)
            lines.append(f"{head} · config={cfg_summary} → {summary}")
        elif s.action == "list_strategies" and s.result:
            names = [x["id"] for x in s.result.get("strategies", [])]
            lines.append(f"{head} → 拿到 {len(names)} 个策略: {', '.join(names[:8])}...")
        elif s.action == "create_strategy_from_text" and s.result:
            lines.append(f"{head} → 新建了策略 {s.result.get('strategy_id')}")
        else:
            lines.append(f"{head}")
    return "\n".join(lines)


def _ask_llm(task: AgentTask) -> dict:
    """让 LLM 决定下一步动作。"""
    if current_provider() == "stub":
        # stub 兜底：跑一次 balanced 打分策略后 finish
        if not task.steps:
            return {"action": "backtest_score", "reason": "[stub] 示例调用",
                    "args": {"start": "2024-01-01", "end": "2024-06-30",
                             "pool": "000300", "limit": 15, "preset": "balanced",
                             "min_score": 60}}
        return {"action": "finish", "reason": "[stub] LLM 未配置，示例结束",
                "args": {
                    "best": {"strategy": "stub_example",
                             "metrics": task.steps[-1].result.get("metrics", {}) if task.steps[-1].result else {}},
                    "summary": "[stub] 未配置 LLM，只跑了一次示例回测",
                    "alternatives": [],
                }}

    prompt = (
        _PROMPT_TMPL
        .replace("{{user_goal}}", task.goal)
        .replace("{{max_iterations}}", str(task.max_iterations))
        .replace("{{iter_count}}", str(len(task.steps)))
        .replace("{{history}}", _render_history(task.steps))
    )
    raw = chat(prompt, json_mode=True, max_tokens=1500)
    try:
        return _extract_json(raw)
    except Exception as e:
        raise ValueError(f"LLM 返回不是合法 JSON：{e}；raw={raw[:200]}")


# ---- 主循环 -------------------------------------------------------


def _reload_from_disk(task: AgentTask) -> AgentTask:
    """从磁盘再读一次，看看 status 有没有被别人改成 cancelled。"""
    fresh = AgentTask.load(task.task_id)
    if fresh and fresh.status == "cancelled":
        task.status = "cancelled"
    return task


def _run_loop(task: AgentTask):
    try:
        while task.status == "running" and len(task.steps) < task.max_iterations:
            # 每轮开始前检查是否被外部要求取消
            _reload_from_disk(task)
            if task.status != "running":
                break
            t0 = time.time()
            try:
                decision = _ask_llm(task)
            except Exception as e:
                task.error = f"LLM 决策失败: {e}\n{traceback.format_exc()[-800:]}"
                task.status = "failed"
                break

            action = decision.get("action")
            args = decision.get("args", {}) or {}
            reason = decision.get("reason", "")

            step = Step(
                idx=len(task.steps) + 1,
                at=datetime.now().isoformat(timespec="seconds"),
                action=action or "?",
                args=args,
                reason=reason,
            )
            task.steps.append(step)
            task.save()

            if action == "finish":
                task.final = args
                task.status = "done"
                task.finished_at = datetime.now().isoformat(timespec="seconds")
                step.result = {"finished": True}
                step.duration_ms = int((time.time() - t0) * 1000)
                task.save()
                break

            if action not in ACTIONS:
                step.error = f"未知 action: {action}"
                step.duration_ms = int((time.time() - t0) * 1000)
                task.save()
                continue

            try:
                step.result = ACTIONS[action](args)
            except Exception as e:
                step.error = f"{type(e).__name__}: {str(e)[:200]}"
            step.duration_ms = int((time.time() - t0) * 1000)
            task.save()
        else:
            if task.status == "running":
                # 到达 max_iterations 强制结束
                task.status = "done"
                task.finished_at = datetime.now().isoformat(timespec="seconds")
                task.final = {
                    "summary": f"到达最大轮数 {task.max_iterations}，未主动 finish。请查看 steps 里各次回测的结果。",
                    "alternatives": [],
                }
                task.save()
    except Exception as e:
        task.error = f"内部错误: {e}\n{traceback.format_exc()[-800:]}"
        task.status = "failed"
        task.finished_at = datetime.now().isoformat(timespec="seconds")
        task.save()


def cancel_task(task_id: str) -> Optional[AgentTask]:
    """把任务标记为 cancelled；后台线程下一轮会自行退出。已完成的任务原样返回。"""
    t = AgentTask.load(task_id)
    if t is None:
        return None
    if t.status == "running":
        t.status = "cancelled"
        t.finished_at = datetime.now().isoformat(timespec="seconds")
        t.save()
    return t


def start_agent(goal: str, max_iterations: int = 10) -> AgentTask:
    """创建任务并启动后台线程。返回可查询的 AgentTask（初始 status=running）。"""
    max_iterations = max(1, min(int(max_iterations or 10), 50))
    task = AgentTask(
        task_id=uuid.uuid4().hex[:12],
        goal=goal.strip(),
        max_iterations=max_iterations,
        started_at=datetime.now().isoformat(timespec="seconds"),
        provider=current_provider(),
    )
    task.save()
    Thread(target=_run_loop, args=(task,), daemon=True).start()
    return task


def list_tasks(limit: int = 20) -> list[dict]:
    files = sorted(TASKS_DIR.glob("*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for f in files[:limit]:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({
                "task_id": d["task_id"],
                "goal": d["goal"],
                "status": d["status"],
                "started_at": d["started_at"],
                "step_count": len(d.get("steps", [])),
                "provider": d.get("provider"),
            })
        except Exception:
            continue
    return out
