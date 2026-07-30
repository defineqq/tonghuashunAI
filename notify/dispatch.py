"""
通知分发器
==========

统一入口 notify(title, text)：把消息发到**所有已配置**的渠道。
没配置的渠道静默跳过。返回一个 dict 显示每个渠道的成功/失败。
"""

from __future__ import annotations

from notify import feishu, dingtalk, wechat, email_


def notify(title: str, text: str) -> dict[str, bool | None]:
    """
    发消息到所有已配置的渠道。

    Returns:
        {"feishu": True/False/None, "dingtalk": ..., "wechat": ..., "email": ...}
        None 表示该渠道未配置（未尝试发送）
    """
    result: dict[str, bool | None] = {}

    result["feishu"] = feishu.send(title, text) if feishu.is_configured() else None
    result["dingtalk"] = dingtalk.send(title, text) if dingtalk.is_configured() else None
    result["wechat"] = wechat.send(title, text) if wechat.is_configured() else None
    result["email"] = email_.send(title, text) if email_.is_configured() else None

    return result


def summary_line(result: dict[str, bool | None]) -> str:
    """把 result 转成一行人类可读的摘要。"""
    parts = []
    for ch, status in result.items():
        if status is None:
            parts.append(f"{ch}:未配置")
        elif status:
            parts.append(f"{ch}:✓")
        else:
            parts.append(f"{ch}:✗")
    return "  ".join(parts)
