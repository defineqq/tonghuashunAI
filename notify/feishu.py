"""
飞书群机器人
============

配置：
    FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx-yyy-zzz

用法：
    from notify.feishu import send
    send("A股每日选股", "今日 Top 3: 600519, 000858, 300750")
"""

from __future__ import annotations

import json
import os
from urllib import request


def is_configured() -> bool:
    return bool(os.environ.get("FEISHU_WEBHOOK"))


def send(title: str, text: str) -> bool:
    """
    发一条富文本消息到飞书群。返回是否成功。
    """
    url = os.environ.get("FEISHU_WEBHOOK")
    if not url:
        return False

    payload = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": [[{"tag": "text", "text": text}]],
                }
            }
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return '"code":0' in body or '"StatusCode":0' in body
    except Exception:
        return False
