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
    # 生命周期：thinking（等 LLM）→ executing（工具跑）→ done | failed
    phase: str = "done"
    raw_llm: str | None = None             # LLM 原始回复（截断，用于复盘）


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
    # 引用旧任务作为经验（避免让 AI 从零摸索）；仅保留 12 字符 task_id
    reference_ids: list[str] = field(default_factory=list)

    def path(self) -> Path:
        return TASKS_DIR / f"{self.task_id}.json"

    def markdown_path(self) -> Path:
        return TASKS_DIR / f"{self.task_id}.md"

    def save(self):
        with _LOCK:
            data = {
                **asdict(self),
                "steps": [asdict(s) for s in self.steps],
            }
            self.path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            # 每次保存都同步生成 Markdown 报告，用户随时可以打开看
            try:
                self.markdown_path().write_text(self.render_markdown(), encoding="utf-8")
            except Exception:
                pass  # markdown 生成失败不阻塞主流程

    def render_markdown(self) -> str:
        status_icon = {
            "running": "🏃 进行中",
            "done": "✅ 完成",
            "failed": "❌ 失败",
            "cancelled": "⏹ 已取消",
        }.get(self.status, self.status)
        lines: list[str] = [
            f"# AI 研究报告 · {self.task_id}",
            "",
            f"- **用户目标**：{self.goal}",
            f"- **状态**：{status_icon}",
            f"- **LLM Provider**：{self.provider}",
            f"- **最大轮数**：{self.max_iterations}",
            f"- **开始时间**：{self.started_at}",
        ]
        if self.finished_at:
            lines.append(f"- **结束时间**：{self.finished_at}")
        lines.append(f"- **已跑轮数**：{len(self.steps)}")
        if self.reference_ids:
            ids_str = ", ".join(f"`{i}`" for i in self.reference_ids)
            lines.append(f"- **引用参考任务**：{ids_str}")
        lines.append("")

        # 最终结论（如果有）
        if self.final:
            lines += ["## 🎯 最终结论", ""]
            summary = self.final.get("summary")
            if summary:
                lines.append(summary)
                lines.append("")
            best = self.final.get("best")
            if best:
                lines += [
                    "### 推荐配置",
                    "",
                    "```json",
                    json.dumps(best, ensure_ascii=False, indent=2),
                    "```",
                    "",
                ]
            alts = self.final.get("alternatives") or []
            if alts:
                lines += ["### 备选方案", "", "```json",
                          json.dumps(alts, ensure_ascii=False, indent=2), "```", ""]

        if self.error:
            lines += ["## ⚠️ 错误", "", "```", self.error, "```", ""]

        # 每一步的详情
        lines += ["## 📜 决策 & 执行过程", ""]
        if not self.steps:
            lines.append("_（还没有步骤）_")
        for s in self.steps:
            phase_icon = {
                "thinking": "💭 正在思考...",
                "executing": "⚙️ 正在执行...",
                "done": "✅",
                "failed": "❌",
            }.get(s.phase, "•")
            lines.append(f"### 第 {s.idx} 轮 · `{s.action}` {phase_icon}")
            lines.append("")
            lines.append(f"- **时间**：{s.at}")
            if s.duration_ms:
                lines.append(f"- **耗时**：{s.duration_ms} ms")
            if s.reason:
                lines += ["", "> " + s.reason.replace("\n", "\n> "), ""]
            if s.args:
                lines += ["**参数**：", "", "```json",
                          json.dumps(s.args, ensure_ascii=False, indent=2), "```", ""]
            if s.error:
                lines += ["**错误**：", "", "```", s.error, "```", ""]
            elif s.result:
                lines.append("**执行结果**：")
                lines.append("")
                # 回测类结果特殊处理，其他直接 dump
                if s.action in ("backtest_score", "backtest_technical"):
                    m = s.result.get("metrics") or {}
                    cfg = s.result.get("config") or {}
                    lines += [
                        f"- 累计收益：**{m.get('cumulative_return', 0)*100:.2f}%**",
                        f"- 年化收益：**{m.get('annualized_return', 0)*100:.2f}%**",
                        f"- 最大回撤：{m.get('max_drawdown', 0)*100:.2f}%",
                        f"- 夏普：{m.get('sharpe', 0):.2f}",
                        f"- 成交笔数：{s.result.get('trades_count', 0)}",
                        "",
                        "配置：",
                        "",
                        "```json",
                        json.dumps(cfg, ensure_ascii=False, indent=2),
                        "```",
                        "",
                    ]
                elif s.action == "list_strategies":
                    strategies = s.result.get("strategies") or []
                    lines.append(f"拿到 **{len(strategies)}** 个策略：")
                    lines.append("")
                    for st in strategies[:20]:
                        lines.append(f"- `{st['id']}` — {st['name']} ({st.get('kind','?')} / {st.get('category','')})")
                    if len(strategies) > 20:
                        lines.append(f"- _...还有 {len(strategies)-20} 个_")
                    lines.append("")
                elif s.action == "create_strategy_from_text":
                    lines += [f"- 新策略 id：`{s.result.get('strategy_id')}`",
                              f"- 名称：{s.result.get('name')}",
                              f"- 说明：{s.result.get('notes') or '—'}", ""]
                else:
                    lines += ["```json",
                              json.dumps(s.result, ensure_ascii=False, indent=2)[:2000],
                              "```", ""]
            if s.raw_llm:
                lines += [
                    "<details><summary>LLM 原始回复</summary>",
                    "",
                    "```",
                    s.raw_llm[:2000],
                    "```",
                    "",
                    "</details>",
                    "",
                ]
            lines.append("")
        return "\n".join(lines)

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
    out = PROJECT_ROOT / "configs" / "user_strategies" / f"{spec['id']}.yaml"
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
    """
    从 LLM 回复里抽第一个合法 JSON 对象。容忍以下脏格式：
    - 代码块包裹 ```json\n{...}\n```
    - 前后有解释文字（"这是我的输出：\n{...}\n上面就是答案"）
    - JSON 后又跟了对象或散文（json.loads 会报 Extra data）
    """
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text).rstrip("`").rstrip()

    start = text.find("{")
    if start < 0:
        raise ValueError("回复里没有找到 JSON 对象起始 `{`")

    # raw_decode 只解一个对象，尾部剩余内容忽略——正好解决 Extra data
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        if isinstance(obj, dict):
            return obj
        raise ValueError(f"JSON 顶层不是对象而是 {type(obj).__name__}")
    except json.JSONDecodeError as e:
        # 兜底一：括号平衡扫第一个完整对象（能处理少量非法尾巴）
        depth, in_str, esc = 0, False, False
        for i, ch in enumerate(text[start:], start=start):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break

        # 兜底二：LLM 常把 summary 之类的值里嵌未转义的双引号，
        # 比如 `"summary": "本轮围绕"昨日涨停"策略..."` → 手动扫描 + 转义
        # 策略：找到每个 "key": " 后的开引号 → 匹配紧邻 , " 或 } " 或 ] "
        # 中间的所有裸 " 全部转义
        try:
            fixed = _repair_unescaped_quotes(text[start:])
            obj, _ = json.JSONDecoder().raw_decode(fixed)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        raise ValueError(f"无法从回复中解析 JSON：{e}")


_STRING_START = re.compile(r'"\s*:\s*"')


def _repair_unescaped_quotes(text: str) -> str:
    """
    修复 JSON 字符串值里未转义的双引号。
    做法：从每个 `"key": "` 后开始扫，一直找到"引号 + 紧跟 , 或 } 或 ]"作为结束标记，
    中间所有裸 " 都转义为 \\"。
    对结构清晰、只是值里带引号的错误非常有效。
    """
    out = []
    i = 0
    n = len(text)
    while i < n:
        m = _STRING_START.search(text, i)
        if not m:
            out.append(text[i:])
            break
        # 输出到值开引号之后
        out.append(text[i:m.end()])
        i = m.end()
        # 从此处开始找"合法结尾"引号
        while i < n:
            if text[i] == "\\" and i + 1 < n:
                out.append(text[i:i + 2])
                i += 2
                continue
            if text[i] == '"':
                # 看下一个非空白字符
                j = i + 1
                while j < n and text[j] in " \t\r\n":
                    j += 1
                # 合法结尾：, } ] 或 EOF
                if j >= n or text[j] in ",}]":
                    out.append('"')
                    i += 1
                    break
                # 否则是"值里裸引号"，转义掉
                out.append('\\"')
                i += 1
                continue
            out.append(text[i])
            i += 1
    return "".join(out)


def _render_reference_summary(task_id: str) -> str | None:
    """
    读一个旧任务，摘一段精简摘要给新任务的 prompt 用。
    只包含：目标、状态、每轮的关键 config→metrics、最终结论。
    过滤掉 raw_llm 等占体积的字段。
    """
    ref = AgentTask.load(task_id)
    if ref is None:
        return f"⚠️ 引用任务 {task_id} 不存在，已忽略。"
    parts = [
        f"### 参考任务 `{ref.task_id}`",
        f"- **原目标**：{ref.goal[:200]}",
        f"- **状态**：{ref.status} · 共 {len(ref.steps)} 步",
    ]
    if ref.final:
        summary = ref.final.get("summary")
        if summary:
            parts.append(f"- **最终结论**：{summary[:500]}")
        best = ref.final.get("best")
        if best:
            parts.append("- **推荐配置**：```json\n"
                         + json.dumps(best, ensure_ascii=False)[:500] + "\n```")
    # 每轮回测的关键结果（精简）
    bt_lines = []
    for s in ref.steps:
        if s.action in ("backtest_score", "backtest_technical") and s.result:
            m = s.result.get("metrics") or {}
            cfg = s.result.get("config") or {}
            cfg_str = json.dumps({k: v for k, v in cfg.items() if k != "weights"},
                                  ensure_ascii=False)
            bt_lines.append(
                f"  · [#{s.idx}] {cfg_str} → 累计 {m.get('cumulative_return',0)*100:.1f}%"
                f" 回撤 {m.get('max_drawdown',0)*100:.1f}% 夏普 {m.get('sharpe',0):.2f}"
            )
    if bt_lines:
        parts.append("- **已跑过的回测**（避免重复）：\n" + "\n".join(bt_lines))
    return "\n".join(parts)


def _render_reference_block(reference_ids: list[str]) -> str:
    """把所有引用任务拼成一段 prompt 内容。空列表时返回空串。"""
    if not reference_ids:
        return ""
    blocks = []
    for tid in reference_ids:
        s = _render_reference_summary(tid)
        if s:
            blocks.append(s)
    if not blocks:
        return ""
    return (
        "\n\n## 📚 参考此前的实验结果（不要重复相同 config）\n\n"
        + "\n\n".join(blocks)
        + "\n\n**基于以上参考决定下一步**：可以复用其结论、进一步微调，或换角度探索。\n"
    )


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


def _ask_llm(task: AgentTask, retry_hint: str | None = None) -> tuple[dict, str]:
    """
    让 LLM 决定下一步动作。返回 (decision_dict, raw_llm_reply)。

    retry_hint: 上一轮的错误摘要（如"JSON 语法错误：Extra data..."）。
    若非空，会作为额外系统提示塞进 prompt，让 LLM 自愈。
    """
    if current_provider() == "stub":
        # 判断是否已跑过一次回测（忽略当前占位 thinking step）
        last_bt = next(
            (s for s in reversed(task.steps)
             if s.action in ("backtest_score", "backtest_technical") and s.result),
            None,
        )
        if last_bt is None:
            d = {"action": "backtest_score", "reason": "[stub] 示例调用",
                 "args": {"start": "2024-01-01", "end": "2024-06-30",
                          "pool": "000300", "limit": 15, "preset": "balanced",
                          "min_score": 60}}
            return d, "[stub reply]"
        d = {"action": "finish", "reason": "[stub] LLM 未配置，示例结束",
             "args": {
                 "best": {"strategy": "stub_example",
                          "metrics": last_bt.result.get("metrics", {})},
                 "summary": "[stub] 未配置 LLM，只跑了一次示例回测",
                 "alternatives": [],
             }}
        return d, "[stub reply]"

    # 引用旧任务作为经验（如果有）
    ref_block = _render_reference_block(task.reference_ids)
    prompt = (
        _PROMPT_TMPL
        .replace("{{user_goal}}", task.goal + ref_block)
        .replace("{{max_iterations}}", str(task.max_iterations))
        .replace("{{iter_count}}", str(len(task.steps)))
        .replace("{{history}}", _render_history(task.steps))
    )
    # 重试自愈提示：告诉 LLM 上次犯了什么错
    if retry_hint:
        prompt += (
            "\n\n---\n⚠️ **重要**：你上一次的回复被系统拒收，错误如下：\n\n"
            f"```\n{retry_hint[:300]}\n```\n\n"
            "常见原因：字符串值里出现了未转义的双引号（如 `\"summary\": \"...\"xxx\"...\"`）。\n"
            "**修复策略**：\n"
            "1. 中文字符串里想引用某段内容时，用中文引号「」或 『』，不要用英文 \" \n"
            "2. 严格返回单个合法 JSON 对象，不要加任何 markdown 代码块\n"
            "3. 如果长文本让你为难，把 summary 里的引号全部删掉或用中文符号替代\n"
            "现在请重新给出上一步的决策 JSON："
        )
    raw = chat(prompt, json_mode=True, max_tokens=1500)
    try:
        return _extract_json(raw), raw
    except Exception as e:
        err = ValueError(f"LLM 返回不是合法 JSON：{e}；raw={raw[:200]}")
        err.raw_reply = raw  # type: ignore[attr-defined]  外层可保留完整 raw 用于复盘
        raise err


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

            # 立刻插入一个 "thinking" 占位 step，前端能马上看到 AI 在动
            step = Step(
                idx=len(task.steps) + 1,
                at=datetime.now().isoformat(timespec="seconds"),
                action="thinking",
                args={},
                reason="正在向 LLM 请求下一步决策...",
                phase="thinking",
            )
            task.steps.append(step)
            task.save()
            t0 = time.time()

            decision, raw_reply, last_err, retries = None, None, None, 0
            MAX_LLM_RETRIES = 2  # 首次失败后再重试 2 次，共 3 次
            for attempt in range(MAX_LLM_RETRIES + 1):
                try:
                    decision, raw_reply = _ask_llm(task, retry_hint=last_err)
                    break
                except Exception as e:
                    last_err = f"{type(e).__name__}: {str(e)[:300]}"
                    retries = attempt + 1
                    # 每次重试都在 UI 上更新 step，让用户看到"正在自愈"
                    step.reason = f"LLM 返回不合法，第 {retries} 次重试... ({last_err[:150]})"
                    raw_from_exc = getattr(e, "raw_reply", None)
                    if raw_from_exc:
                        step.raw_llm = (step.raw_llm or "") + f"\n\n--- 第 {retries} 次失败 raw ---\n" + raw_from_exc[:2000]
                    task.save()
                    time.sleep(1)  # 稍等 1s 再打 LLM，避免瞬时抖动

            if decision is None:
                # 3 次都失败才真放弃
                step.action = "llm_error"
                step.phase = "failed"
                step.error = f"LLM 连续 {MAX_LLM_RETRIES+1} 次返回不合法 JSON，放弃本轮。最后错误：{last_err}"
                step.duration_ms = int((time.time() - t0) * 1000)
                task.error = step.error
                task.status = "failed"
                task.save()
                break

            action = decision.get("action") or "?"
            args = decision.get("args", {}) or {}
            reason = decision.get("reason", "")

            # 把占位 step 更新为真正的决策 + 执行状态
            step.action = action
            step.args = args
            step.reason = reason
            step.raw_llm = raw_reply
            step.phase = "executing"
            task.save()  # LLM 返回后立刻再存一次，前端能看到决策内容

            if action == "finish":
                task.final = args
                task.status = "done"
                task.finished_at = datetime.now().isoformat(timespec="seconds")
                step.result = {"finished": True}
                step.phase = "done"
                step.duration_ms = int((time.time() - t0) * 1000)
                task.save()
                break

            if action not in ACTIONS:
                step.error = f"未知 action: {action}"
                step.phase = "failed"
                step.duration_ms = int((time.time() - t0) * 1000)
                task.save()
                continue

            try:
                step.result = ACTIONS[action](args)
                step.phase = "done"
            except Exception as e:
                step.error = f"{type(e).__name__}: {str(e)[:200]}"
                step.phase = "failed"
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


def start_agent(goal: str, max_iterations: int = 10,
                reference_ids: list[str] | None = None) -> AgentTask:
    """
    创建任务并启动后台线程。返回可查询的 AgentTask（初始 status=running）。

    Args:
        goal: 用户目标
        max_iterations: 上限轮数（1~50）
        reference_ids: 引用的旧任务 ID 列表；旧任务的目标 / 结论 / 已跑回测
                       会被摘要后注入到 prompt，让 AI 复用经验，不重复劳动
    """
    max_iterations = max(1, min(int(max_iterations or 10), 50))
    refs = [rid.strip() for rid in (reference_ids or []) if rid and rid.strip()]
    task = AgentTask(
        task_id=uuid.uuid4().hex[:12],
        goal=goal.strip(),
        max_iterations=max_iterations,
        started_at=datetime.now().isoformat(timespec="seconds"),
        provider=current_provider(),
        reference_ids=refs,
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
                "reference_ids": d.get("reference_ids", []),
            })
        except Exception:
            continue
    return out
