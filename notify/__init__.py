"""
notify — 通知推送
================

- feishu.py   飞书群机器人（webhook）
- dingtalk.py 钉钉群机器人（webhook）
- wechat.py   企业微信群机器人（webhook）
- email_.py   SMTP 邮件
- dispatch.py 统一 API：notify(text, title=None) 按 .env 配置分发

设计原则：
- 所有推送都通过 webhook / SMTP，不需要接管客户端
- 未配置对应密钥时静默跳过（不 crash）
"""

__all__ = ["dispatch"]
