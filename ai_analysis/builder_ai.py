"""
条件构建器 AI 版：中文描述 → 策略 JSON
==========================================

流程：
    1. 组装带完整指标目录的 prompt
    2. 让 LLM 输出 builder spec
    3. 用 strategies.builder.validate_spec 校验
    4. 校验通过则返回 spec，让前端直接填入表单 / 保存

无 LLM key 时走 stub，返回一个简单的 MA 金叉示例，方便本地测试链路。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ai_analysis.llm_client import chat, current_provider
from strategies.builder import INDICATORS, validate_spec


_PROMPT = (Path(__file__).parent / "prompts" / "builder_ai.md").read_text(encoding="utf-8")


def _render_indicator_catalog() -> str:
    """把 INDICATORS 展开成给 LLM 看的紧凑目录，控制 token 用量。"""
    lines = []
    for key, ind in INDICATORS.items():
        params_desc = ", ".join(
            f'{p["name"]}({p.get("type","")}, default={p.get("default","")})'
            for p in ind.get("params", [])
        ) or "无"
        lines.append(f"### {key}  — {ind['label']}")
        lines.append(f"- params: {params_desc}")
        for op in ind.get("ops", []):
            vt = op.get("value_type", "none")
            if vt == "number":
                lines.append(f'- op `{op["name"]}` — {op["label"]}  (需要 value，默认 {op.get("value_default","?")})')
            else:
                lines.append(f'- op `{op["name"]}` — {op["label"]}')
        lines.append("")
    return "\n".join(lines)


def _slugify(s: str) -> str:
    """把中文/带空格的名字弄成合法 id 建议。"""
    s = re.sub(r"[^\w一-鿿]+", "_", s or "").strip("_").lower()
    return s or "ai_strategy"


def _extract_json(text: str) -> dict:
    """LLM 有时会带 markdown 代码块，做一层剥离。"""
    text = text.strip()
    if text.startswith("```"):
        # 去掉首尾三个反引号 + 可能的 json 语言标记
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text).rstrip("`").rstrip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 找第一个 { ... } 块
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def _stub_spec(user_prompt: str, suggested_id: str) -> dict:
    """无 LLM key 时的兜底：返回一个通用的 MA 金叉+放量示例。"""
    return {
        "id": suggested_id or "stub_ma_cross",
        "name": "示例：MA 金叉 + 放量",
        "description": "[stub 兜底] 未配置 LLM，返回一个通用示例。你可以在表单里手工改。",
        "buy": {
            "logic": "AND",
            "rules": [
                {"indicator": "MA", "op": "cross_up", "params": {"fast": 5, "slow": 20}},
                {"indicator": "VOLUME", "op": "surge", "params": {"n": 20}, "value": 1.5},
            ],
        },
        "sell": {
            "logic": "OR",
            "rules": [
                {"indicator": "MA", "op": "price_below", "params": {"fast": 5, "slow": 20}},
            ],
        },
        "notes": f"[stub] 未使用 LLM。用户原始描述：{user_prompt[:80]}",
    }


def generate_spec(
    user_prompt: str,
    suggested_id: str | None = None,
    suggested_name: str | None = None,
) -> dict:
    """
    把中文描述转成 builder spec。

    Returns:
      {
        "spec": <构建器规格>,
        "provider": <当前 LLM>,
        "notes": <LLM 的解释>,
        "raw": <LLM 原始回复，便于调试>,
      }

    Raises:
      ValueError: LLM 返回的 spec 校验失败
    """
    if not user_prompt or not user_prompt.strip():
        raise ValueError("用户描述不能为空")

    suggested_id = suggested_id or _slugify(suggested_name or user_prompt[:20])

    if current_provider() == "stub":
        spec = _stub_spec(user_prompt, suggested_id)
        return {"spec": spec, "provider": "stub", "notes": spec.get("notes"), "raw": "[stub]"}

    prompt = (
        _PROMPT
        .replace("{{indicator_count}}", str(len(INDICATORS)))
        .replace("{{indicator_catalog}}", _render_indicator_catalog())
        .replace("{{suggested_id}}", suggested_id)
        .replace("{{user_prompt}}", user_prompt.strip())
    )

    raw = chat(prompt, json_mode=True, max_tokens=2500)
    try:
        spec = _extract_json(raw)
    except Exception as e:
        raise ValueError(f"LLM 返回的不是合法 JSON：{e}；原始：{raw[:200]}")

    # 允许 LLM 没设 id，用建议值补
    if not spec.get("id"):
        spec["id"] = suggested_id
    if not spec.get("name"):
        spec["name"] = suggested_name or "AI 生成策略"

    ok, err = validate_spec(spec)
    if not ok:
        raise ValueError(f"AI 生成的策略未通过校验：{err}；spec={json.dumps(spec, ensure_ascii=False)[:300]}")

    return {
        "spec": spec,
        "provider": current_provider(),
        "notes": spec.get("notes") or spec.get("description"),
        "raw": raw,
    }
