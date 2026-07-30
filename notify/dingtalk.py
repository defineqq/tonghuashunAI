"""
钉钉群机器人
============

配置（同群机器人 URL 里已经包含 access_token 参数）：
    DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx
    DINGTALK_SECRET=（可选，如果开启了加签校验）
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
from urllib import request


def is_configured() -> bool:
    return bool(os.environ.get("DINGTALK_WEBHOOK"))


def _sign(secret: str) -> tuple[str, str]:
    ts = str(round(time.time() * 1000))
    string_to_sign = f"{ts}\n{secret}"
    hmac_code = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return ts, sign


def send(title: str, text: str) -> bool:
    url = os.environ.get("DINGTALK_WEBHOOK")
    if not url:
        return False
    secret = os.environ.get("DINGTALK_SECRET")
    if secret:
        ts, sign = _sign(secret)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}timestamp={ts}&sign={sign}"

    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": f"### {title}\n\n{text}"},
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return '"errcode":0' in body
    except Exception:
        return False
