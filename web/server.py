"""
FastAPI 服务端
==============

启动：
    python -m web.server                     # 默认 http://127.0.0.1:8000
    uvicorn web.server:app --reload           # 开发模式（自动重载）

页面：
    /              主控台（单页 HTML）
    /docs          OpenAPI 交互式文档（FastAPI 自动生成）

API：
    GET  /api/status                 系统状态（LLM/通知等配置情况）
    GET  /api/portfolio/{account}    读账户
    POST /api/portfolio/new          新建账户
    GET  /api/universe/{index}       某指数成分股（000300/000905/000852）
    GET  /api/market/daily           拉某只股票日线
    POST /api/score                  给一只股票打分
    POST /api/rank                   给一组股票打分并排序
    POST /api/report/daily           生成每日报告
    POST /api/paper/run              触发一次假想撮合
    POST /api/backtest/run           跑一段历史回测
    GET  /api/qbot/strategies        列出 Qbot 内置策略
    GET  /api/qbot/strategy/{name}   查看某个 Qbot 策略源码
    POST /api/notify/test            触发一次通知测试
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_dotenv():
    """把项目根的 .env 加载到 os.environ（简单实现，不依赖 python-dotenv）。"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:  # 不覆盖已有环境变量
            os.environ[k] = v


_load_dotenv()


from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web.api import routes


app = FastAPI(
    title="tonghuashunAI",
    description="A 股 AI 量化分析与自动化交易项目 · 浏览器控制台",
    version="1.0.0",
)

# 允许本地开发跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router, prefix="/api")

# 静态资源
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/healthz", include_in_schema=False)
def health():
    return {"status": "ok"}


def main():
    import uvicorn
    host = os.environ.get("WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("WEB_PORT", "8000"))
    print(f"\n🚀 tonghuashunAI Web 控制台\n   浏览器打开: http://{host}:{port}\n   API 文档: http://{host}:{port}/docs\n")
    uvicorn.run("web.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
