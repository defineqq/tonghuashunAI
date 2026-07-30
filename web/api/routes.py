"""
FastAPI 路由
============

所有业务 API 都挂在 /api/* 下。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter()


# ================ 数据模型 =================


class ScoreRequest(BaseModel):
    symbol: str = Field(..., description="6 位股票代码")
    as_of: Optional[str] = Field(None, description="截止日期 YYYY-MM-DD")
    use_llm: bool = True


class RankRequest(BaseModel):
    symbols: list[str]
    as_of: Optional[str] = None
    top_n: Optional[int] = 10
    use_llm: bool = False


class DailyReportRequest(BaseModel):
    symbols: Optional[list[str]] = None
    as_of: Optional[str] = None
    top_n: int = 10
    save: bool = True


class PaperRunRequest(BaseModel):
    account: str = "swing_v1"
    initial_cash: float = 100_000
    date: Optional[str] = None
    limit: int = 50
    min_score: float = 65.0
    use_llm: bool = False


class BacktestRequest(BaseModel):
    start: str
    end: str
    pool: str = "000300"          # 000300 / 000905 / 000852
    limit: Optional[int] = 50
    initial_cash: float = 100_000
    min_score: float = 65.0


class NewPortfolioRequest(BaseModel):
    account_id: str
    initial_cash: float = 100_000


class NotifyTestRequest(BaseModel):
    title: str = "tonghuashunAI 测试通知"
    text: str = "这是一条测试消息，若收到说明通知渠道配置成功。"


# ================ 状态与配置 =================


@router.get("/status", summary="系统状态")
def get_status():
    from ai_analysis.llm_client import current_provider, is_configured as llm_ok
    from notify import feishu, dingtalk, wechat, email_

    return {
        "time": datetime.now().isoformat(),
        "llm": {
            "configured": llm_ok(),
            "provider": current_provider(),
        },
        "notify": {
            "feishu": feishu.is_configured(),
            "dingtalk": dingtalk.is_configured(),
            "wechat": wechat.is_configured(),
            "email": email_.is_configured(),
        },
        "python": {
            "version": f"{__import__('sys').version_info[:3]}",
        },
    }


# ================ 账户 =================


@router.get("/portfolio/{account}", summary="读账户")
def get_portfolio(account: str):
    from paper_trade import portfolio as pfolio
    p = pfolio.default_path(account)
    if not p.exists():
        raise HTTPException(404, f"账户 {account} 不存在")
    port = pfolio.Portfolio.load(p)
    return port.to_dict()


@router.post("/portfolio/new", summary="新建账户")
def new_portfolio(req: NewPortfolioRequest):
    from paper_trade import portfolio as pfolio
    p = pfolio.default_path(req.account_id)
    if p.exists():
        raise HTTPException(409, f"账户 {req.account_id} 已存在")
    port = pfolio.Portfolio.new(req.account_id, req.initial_cash)
    port.save(p)
    return {"ok": True, "path": str(p), "account": port.to_dict()}


@router.get("/portfolio", summary="列出所有账户")
def list_portfolios():
    root = Path("logs") / "portfolio"
    if not root.exists():
        return {"accounts": []}
    return {"accounts": [f.stem for f in root.glob("*.json")]}


# ================ 股票池 =================


@router.get("/universe/{index}", summary="获取指数成分股")
def get_universe(index: str, limit: Optional[int] = None):
    from data_layer import universe as uni
    fn_map = {
        "000300": uni.hs300_constituents,
        "000905": uni.csi500_constituents,
        "000852": uni.csi1000_constituents,
    }
    if index not in fn_map:
        raise HTTPException(400, f"不支持的指数: {index}")
    df = fn_map[index]()
    code_col = next((c for c in df.columns if "代码" in c and "指数" not in c), None)
    name_col = next((c for c in df.columns if "名称" in c or "简称" in c), None)
    items = []
    for _, row in df.iterrows():
        item = {"code": str(row[code_col]).zfill(6)}
        if name_col:
            item["name"] = str(row[name_col])
        items.append(item)
        if limit and len(items) >= limit:
            break
    return {"index": index, "count": len(items), "items": items}


# ================ 行情 =================


@router.get("/market/daily", summary="拉取股票日线")
def get_daily(symbol: str, start: str = "2024-01-01", end: Optional[str] = None):
    from data_layer import market
    end = end or datetime.now().strftime("%Y-%m-%d")
    df = market.daily(symbol, start=start, end=end)
    df = df.copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return {"symbol": symbol, "count": len(df), "data": df.to_dict(orient="records")}


# ================ 评分 =================


@router.post("/score", summary="给单只股票打分")
def score(req: ScoreRequest):
    from analysis.scorer import score_one
    try:
        return score_one(req.symbol, as_of=req.as_of, use_llm=req.use_llm)
    except Exception as e:
        raise HTTPException(500, f"评分失败: {e}")


@router.post("/rank", summary="给一组股票打分并排序")
def rank(req: RankRequest):
    from analysis.scorer import rank_universe
    df = rank_universe(req.symbols, as_of=req.as_of, top_n=req.top_n, use_llm=req.use_llm, verbose=False)
    return {"count": len(df), "data": df.to_dict(orient="records")}


# ================ 每日报告 =================


@router.post("/report/daily", summary="生成每日分析报告")
def gen_daily_report(req: DailyReportRequest):
    from ai_analysis import daily_report
    from data_layer import universe as uni

    symbols = req.symbols or uni.load_pool()[:50]
    as_of = req.as_of or datetime.now().strftime("%Y-%m-%d")

    save_to = None
    if req.save:
        save_to = Path("logs") / "reports" / f"{as_of}.md"

    md = daily_report.render(as_of=as_of, symbols=symbols, top_n=req.top_n, save_to=save_to)
    return {"as_of": as_of, "path": str(save_to) if save_to else None, "markdown": md}


@router.get("/report/list", summary="历史报告列表")
def list_reports():
    root = Path("logs") / "reports"
    if not root.exists():
        return {"reports": []}
    reports = sorted([f.name for f in root.glob("*.md")], reverse=True)
    return {"reports": reports}


@router.get("/report/{name}", summary="读某份历史报告")
def read_report(name: str):
    p = Path("logs") / "reports" / name
    if not p.exists() or ".." in name:
        raise HTTPException(404, "报告不存在")
    return {"name": name, "markdown": p.read_text(encoding="utf-8")}


# ================ 假想撮合 =================


@router.post("/paper/run", summary="执行一次假想撮合")
def paper_run(req: PaperRunRequest):
    from data_layer import universe as uni, market
    from paper_trade import portfolio as pfolio
    from paper_trade.broker import execute_day, FeeConfig
    from paper_trade.risk import RiskConfig
    from my_strategies import swing_v1
    import yaml

    date = req.date or datetime.now().strftime("%Y-%m-%d")
    port = pfolio.load_or_create(req.account, initial_cash=req.initial_cash)

    symbols = uni.load_pool()[: req.limit]
    buys, sells = swing_v1.generate_signals(port, symbols, as_of=date,
                                             min_score=req.min_score, use_llm=req.use_llm)

    close_prices = {}
    all_syms = set(list(port.positions.keys()) + [b.symbol for b in buys])
    for s in all_syms:
        try:
            df = market.daily(s, start="2020-01-01", end=date)
            if not df.empty:
                close_prices[s] = float(df["close"].iloc[-1])
        except Exception:
            pass

    with open("configs/strategy.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)["swing_v1"]

    result = execute_day(
        port, date, close_prices,
        buy_signals=buys, sell_signals=sells,
        risk_cfg=RiskConfig(
            stop_loss_pct=cfg.get("stop_loss_pct", 0.05),
            take_profit_pct=cfg.get("take_profit_pct", 0.15),
            max_hold_days=cfg.get("max_hold_days", 10),
        ),
        fee_cfg=FeeConfig(),
        max_positions=cfg.get("max_positions", 5),
    )
    port.save(pfolio.default_path(req.account))
    return {
        "account": req.account,
        "date": date,
        "snapshot": result["snapshot"].__dict__,
        "trades": [t.__dict__ for t in result["trades"]],
        "portfolio": port.to_dict(),
    }


# ================ 回测 =================


@router.post("/backtest/run", summary="跑一段历史回测")
def backtest_run(req: BacktestRequest):
    from data_layer import universe as uni
    from my_strategies import swing_v1
    from backtest import engine, report

    fn_map = {
        "000300": uni.hs300_constituents,
        "000905": uni.csi500_constituents,
        "000852": uni.csi1000_constituents,
    }
    if req.pool not in fn_map:
        raise HTTPException(400, f"不支持的指数: {req.pool}")

    df_idx = fn_map[req.pool]()
    code_col = next((c for c in df_idx.columns if "代码" in c and "指数" not in c), None)
    symbols = [str(x).zfill(6) for x in df_idx[code_col].tolist()]
    if req.limit:
        symbols = symbols[: req.limit]

    result = engine.run(
        strategy_fn=swing_v1.generate_signals,
        universe=symbols,
        start=req.start,
        end=req.end,
        initial_cash=req.initial_cash,
        strategy_kwargs={"min_score": req.min_score, "use_llm": False},
    )
    md_path = report.render(result, strategy_name="swing_v1")
    snapshots = result["snapshots"].copy()
    snapshots["date"] = snapshots["date"].astype(str)
    return {
        "metrics": result["metrics"],
        "snapshots": snapshots.to_dict(orient="records"),
        "trades_count": len(result["portfolio"].trades),
        "report_path": str(md_path),
    }


# ================ Qbot 集成 =================


QBOT_STRATEGY_DIR = Path("vendor/Qbot/qbot/strategies")


@router.get("/qbot/strategies", summary="Qbot 内置策略列表")
def qbot_strategies():
    if not QBOT_STRATEGY_DIR.exists():
        return {"strategies": []}
    items = []
    for f in QBOT_STRATEGY_DIR.glob("*.py"):
        if f.name.startswith("__"):
            continue
        # 从文件顶部读一小段做摘要
        head = f.read_text(encoding="utf-8", errors="replace")[:2000]
        desc = ""
        for line in head.splitlines():
            if "Description:" in line or "描述:" in line:
                desc = line.split(":", 1)[-1].strip()
                break
        items.append({"name": f.stem, "file": f.name, "description": desc, "size": f.stat().st_size})
    return {"count": len(items), "strategies": sorted(items, key=lambda x: x["name"])}


@router.get("/qbot/strategy/{name}", summary="查看 Qbot 策略源码")
def qbot_strategy_source(name: str):
    if "/" in name or ".." in name:
        raise HTTPException(400, "非法名称")
    p = QBOT_STRATEGY_DIR / f"{name}.py"
    if not p.exists():
        raise HTTPException(404, f"未找到策略: {name}")
    return {"name": name, "source": p.read_text(encoding="utf-8", errors="replace")}


@router.get("/qbot/docs", summary="Qbot 文档目录")
def qbot_docs():
    root = Path("vendor/Qbot/docs")
    if not root.exists():
        return {"docs": []}
    items = []
    for md in sorted(root.rglob("*.md")):
        rel = md.relative_to(root)
        items.append({"path": str(rel), "size": md.stat().st_size})
    return {"count": len(items), "docs": items}


@router.get("/qbot/doc", summary="读一份 Qbot 文档")
def qbot_doc(path: str):
    if ".." in path:
        raise HTTPException(400, "非法路径")
    p = Path("vendor/Qbot/docs") / path
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "文档不存在")
    return {"path": path, "markdown": p.read_text(encoding="utf-8", errors="replace")}


# ================ 通知 =================


@router.post("/notify/test", summary="发一条测试通知")
def notify_test(req: NotifyTestRequest):
    from notify.dispatch import notify, summary_line
    result = notify(req.title, req.text)
    return {"result": result, "summary": summary_line(result)}
