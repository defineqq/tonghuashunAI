"""
SMTP 邮件发送
=============

配置（需 4 项都有值才启用）：
    SMTP_HOST=smtp.qq.com
    SMTP_PORT=465
    SMTP_USER=you@qq.com
    SMTP_PASS=授权码（不是登录密码）
    SMTP_TO=alice@example.com,bob@example.com
"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def is_configured() -> bool:
    return all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "SMTP_TO"))


def send(title: str, text: str, html: str | None = None) -> bool:
    if not is_configured():
        return False
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    pw = os.environ["SMTP_PASS"]
    to = [x.strip() for x in os.environ["SMTP_TO"].split(",") if x.strip()]

    msg = MIMEMultipart("alternative")
    msg["From"] = user
    msg["To"] = ", ".join(to)
    msg["Subject"] = title
    msg.attach(MIMEText(text, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as s:
                s.login(user, pw)
                s.sendmail(user, to, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=15) as s:
                s.starttls()
                s.login(user, pw)
                s.sendmail(user, to, msg.as_string())
        return True
    except Exception:
        return False
