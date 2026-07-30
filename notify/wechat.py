"""
企业微信群机器人
================

配置：
    WECHAT_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
"""

from __future__ import annotations

import json
import os
from urllib import request


def is_configured() -> bool:
    return bool(os.environ.get("WECHAT_WEBHOOK"))


def send(title: str, text: str) -> bool:
    url = os.environ.get("WECHAT_WEBHOOK")
    if not url:
        return False

    payload = {
        "msgtype": "markdown",
        "markdown": {"content": f"## {title}\n\n{text}"},
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return '"errcode":0' in body
    except Exception:
        return False
