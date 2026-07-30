"""
LLM 统一调用接口
================

一层薄封装，屏蔽 Claude / OpenAI / DeepSeek 的差异。
关键设计：**没有 API key 时自动 stub**，返回可预测的中性输出，让下游流程不受阻塞。

用法：
    from ai_analysis.llm_client import chat
    resp = chat("请分析这段公告的利好利空", model="auto")

环境变量：
    LLM_PROVIDER  = claude | openai | deepseek | stub  (默认 auto，按 key 存在性决定)
    ANTHROPIC_API_KEY
    OPENAI_API_KEY
    DEEPSEEK_API_KEY
"""

from __future__ import annotations

import json
import os
from typing import Literal


Provider = Literal["claude", "openai", "deepseek", "stub", "auto"]


def _resolve_provider(explicit: Provider = "auto") -> Provider:
    if explicit != "auto":
        return explicit
    env = os.environ.get("LLM_PROVIDER")
    if env:
        return env  # type: ignore[return-value]
    # 按存在的 key 自动选，且要求对应 SDK 已安装
    if os.environ.get("ANTHROPIC_API_KEY") and _sdk_available("anthropic"):
        return "claude"
    if os.environ.get("DEEPSEEK_API_KEY") and _sdk_available("openai"):
        return "deepseek"
    if os.environ.get("OPENAI_API_KEY") and _sdk_available("openai"):
        return "openai"
    return "stub"


def _sdk_available(mod: str) -> bool:
    """检查一个模块能否 import（不真的加载）。"""
    import importlib.util
    return importlib.util.find_spec(mod) is not None


_DEFAULT_MODELS = {
    "claude": os.environ.get("ANTHROPIC_MODEL")
              or os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL")
              or "claude-sonnet-5",  # 环境变量优先，兼容公司代理
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
}


def chat(
    prompt: str,
    provider: Provider = "auto",
    model: str | None = None,
    system: str | None = None,
    max_tokens: int = 2000,
    json_mode: bool = False,
) -> str:
    """
    发一段 prompt 给 LLM 拿回复。

    Args:
        prompt: 用户输入
        provider: 'claude' | 'openai' | 'deepseek' | 'stub' | 'auto'
        model: 具体型号，不填用该 provider 的默认值
        system: system prompt
        max_tokens: 最长输出
        json_mode: 要求 LLM 返回 JSON（部分 provider 支持）

    Returns:
        LLM 的文本回复
    """
    prov = _resolve_provider(provider)

    if prov == "stub":
        return _stub_response(prompt, json_mode)

    model = model or _DEFAULT_MODELS[prov]
    if prov == "claude":
        return _call_claude(prompt, model, system, max_tokens, json_mode)
    if prov == "openai":
        return _call_openai(prompt, model, system, max_tokens, json_mode)
    if prov == "deepseek":
        return _call_deepseek(prompt, model, system, max_tokens, json_mode)
    raise ValueError(f"unsupported provider: {prov}")


# ---- stub -----------------------------------------------------------


def _stub_response(prompt: str, json_mode: bool) -> str:
    """无 API key 时的兜底返回，保持下游流程能跑。"""
    if json_mode:
        return json.dumps({
            "score": 50,
            "sentiment": "neutral",
            "reason": "[stub] 未配置 LLM API key，返回中性评分",
            "highlights": [],
        }, ensure_ascii=False)
    return "[stub] 未配置 LLM API key。请在 .env 中填入 ANTHROPIC_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY 之一。"


# ---- Claude ---------------------------------------------------------


def _call_claude(prompt: str, model: str, system: str | None, max_tokens: int, json_mode: bool) -> str:
    import anthropic  # 惰性 import

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system or "你是一个 A 股金融分析师，请客观、简洁地分析。",
        messages=[
            {"role": "user", "content": prompt + ("\n\n请仅返回 JSON，不要额外文字。" if json_mode else "")}
        ],
    )
    return msg.content[0].text  # type: ignore[union-attr]


# ---- OpenAI ---------------------------------------------------------


def _call_openai(prompt: str, model: str, system: str | None, max_tokens: int, json_mode: bool) -> str:
    from openai import OpenAI  # 惰性 import

    client = OpenAI()
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system or "你是一个 A 股金融分析师，请客观、简洁地分析。"},
            {"role": "user", "content": prompt},
        ],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


# ---- DeepSeek -------------------------------------------------------


def _call_deepseek(prompt: str, model: str, system: str | None, max_tokens: int, json_mode: bool) -> str:
    """DeepSeek 兼容 OpenAI SDK，只是 base_url 不同。"""
    from openai import OpenAI  # 惰性 import

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com/v1",
    )
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system or "你是一个 A 股金融分析师，请客观、简洁地分析。"},
            {"role": "user", "content": prompt},
        ],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def is_configured() -> bool:
    """是否配置了任何 LLM API key。"""
    return _resolve_provider("auto") != "stub"


def current_provider() -> str:
    """返回当前使用的 provider（用于日志/调试）。"""
    return _resolve_provider("auto")
