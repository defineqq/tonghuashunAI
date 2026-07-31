"""
FastAPI 路由
============

所有业务 API 都挂在 /api/* 下。
"""

from __future__ import annotations

import os
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


class ScreenRequest(BaseModel):
    """一站式股票筛选器：选池 → 筛选 → 打分 → 返回结果。"""
    pool: str = Field("000300", description="000300=沪深300, 000905=中证500, 000852=中证1000")
    pool_limit: int = Field(30, description="从池子取前 N 只（数量越大越慢）")
    preset: str = Field("balanced", description="策略预设：balanced/momentum/value/growth/dividend")
    min_score: float = Field(0, description="综合分下限（0-100）")
    top_n: int = Field(10, description="最终返回前 N 只")
    use_llm: bool = Field(False, description="是否用 LLM 分析情绪面（慢）")
    as_of: Optional[str] = None
    custom_weights: Optional[dict] = Field(None, description="覆盖 preset 的自定义四维权重")


# 策略预设 = 权重方案
PRESET_WEIGHTS = {
    "balanced":  {"technical": 0.35, "fundamental": 0.20, "sentiment": 0.20, "moneyflow": 0.25},
    "momentum":  {"technical": 0.55, "fundamental": 0.05, "sentiment": 0.15, "moneyflow": 0.25},
    "value":     {"technical": 0.15, "fundamental": 0.55, "sentiment": 0.10, "moneyflow": 0.20},
    "growth":    {"technical": 0.25, "fundamental": 0.40, "sentiment": 0.20, "moneyflow": 0.15},
    "dividend":  {"technical": 0.10, "fundamental": 0.60, "sentiment": 0.10, "moneyflow": 0.20},
}


PRESET_LABELS = {
    "balanced":  {"name": "均衡型", "desc": "四维等权，适合不了解自己偏好的用户"},
    "momentum":  {"name": "动量型", "desc": "重技术面，追涨强势股，短线波段"},
    "value":     {"name": "价值型", "desc": "重基本面，找低估、财务健康的股票"},
    "growth":    {"name": "成长型", "desc": "看重基本面 + 情绪，找业绩增长股"},
    "dividend":  {"name": "红利型", "desc": "重基本面 + 稳定资金流，适合长线持有"},
}


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
    preset: str = Field("balanced", description="打分权重预设（strategy_type=score 时）")

    # 新增：策略类型
    strategy_type: str = Field("score", description="score=四维打分策略 / technical=技术指标策略")
    strategy_id: Optional[str] = Field(None, description="strategy_type=technical 时指定策略 id")
    strategy_params: Optional[dict] = Field(None, description="策略参数（覆盖默认）")

    # 自定义打分权重（strategy_type=score 且 preset=custom 时用）
    custom_weights: Optional[dict] = None
    position_size: Optional[float] = None  # 单只仓位比例，覆盖 configs


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


@router.get("/status/datasources", summary="数据源健康检查")
def check_datasources():
    """
    实时探测各数据源是否可用。用一只测试股（贵州茅台）跑一遍关键接口。
    结果被短时缓存（1 分钟）。
    """
    import time
    from data_layer.cache import _data_dir
    from pathlib import Path
    import json as _json

    # 简单文件缓存 1 分钟
    cache_file = _data_dir() / "_health.json"
    if cache_file.exists() and (time.time() - cache_file.stat().st_mtime) < 60:
        try:
            return _json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    checks = []
    test_symbol = "600519"

    # 1) 日线（多源回退）
    t0 = time.time()
    try:
        from data_layer import market
        df = market.daily(test_symbol, start="2024-11-01", end="2024-12-31")
        checks.append({
            "name": "日线行情", "key": "daily",
            "ok": not df.empty,
            "latency_ms": int((time.time() - t0) * 1000),
            "detail": f"{len(df)} 行" if not df.empty else "空",
        })
    except Exception as e:
        checks.append({"name": "日线行情", "key": "daily", "ok": False,
                       "latency_ms": int((time.time() - t0) * 1000), "detail": str(e)[:80]})

    # 2) 成分股
    t0 = time.time()
    try:
        from data_layer import universe
        df = universe.hs300_constituents()
        checks.append({"name": "沪深300 成分股", "key": "universe",
                       "ok": len(df) > 200, "latency_ms": int((time.time() - t0) * 1000),
                       "detail": f"{len(df)} 只"})
    except Exception as e:
        checks.append({"name": "沪深300 成分股", "key": "universe", "ok": False,
                       "latency_ms": int((time.time() - t0) * 1000), "detail": str(e)[:80]})

    # 3) 北向资金（比主力资金流轻量）
    t0 = time.time()
    try:
        from data_layer import moneyflow
        df = moneyflow.northbound_daily()
        checks.append({"name": "北向资金", "key": "northbound", "ok": not df.empty,
                       "latency_ms": int((time.time() - t0) * 1000),
                       "detail": f"{len(df)} 行" if not df.empty else "空"})
    except Exception as e:
        checks.append({"name": "北向资金", "key": "northbound", "ok": False,
                       "latency_ms": int((time.time() - t0) * 1000), "detail": str(e)[:80]})

    # 4) 财报
    t0 = time.time()
    try:
        from data_layer import fundamental
        df = fundamental.financial_abstract(test_symbol)
        checks.append({"name": "财务摘要", "key": "fundamental", "ok": not df.empty,
                       "latency_ms": int((time.time() - t0) * 1000),
                       "detail": f"{len(df)} 行" if not df.empty else "空"})
    except Exception as e:
        checks.append({"name": "财务摘要", "key": "fundamental", "ok": False,
                       "latency_ms": int((time.time() - t0) * 1000), "detail": str(e)[:80]})

    # 5) 财联社新闻（大盘情绪源）
    t0 = time.time()
    try:
        from data_layer import sentiment
        df = sentiment.cls_news(limit=5)
        checks.append({"name": "财联社电报", "key": "cls_news", "ok": not df.empty,
                       "latency_ms": int((time.time() - t0) * 1000),
                       "detail": f"{len(df)} 条"})
    except Exception as e:
        checks.append({"name": "财联社电报", "key": "cls_news", "ok": False,
                       "latency_ms": int((time.time() - t0) * 1000), "detail": str(e)[:80]})

    ok_count = sum(1 for c in checks if c["ok"])
    result = {
        "checked_at": datetime.now().isoformat(),
        "healthy": ok_count == len(checks),
        "ok_count": ok_count,
        "total": len(checks),
        "checks": checks,
    }

    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(_json.dumps(result, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    return result


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
    # 优先匹配"成分券"相关列，避免拿到"指数代码/名称"
    code_col = next((c for c in df.columns if "成分券代码" in c), None) \
        or next((c for c in df.columns if "代码" in c and "指数" not in c), None)
    name_col = next((c for c in df.columns if "成分券名称" in c), None) \
        or next((c for c in df.columns if ("名称" in c or "简称" in c) and "指数" not in c and "英文" not in c and "交易所" not in c), None)
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


@router.get("/market/search", summary="搜股票（按代码或名称）")
def market_search(q: str, limit: int = 10):
    """
    从沪深300+中证500 里搜索。q 支持代码前缀或名称片段。
    """
    from data_layer import universe as uni
    q = q.strip()
    if not q:
        return {"items": []}

    matches = []
    seen = set()
    for fn in (uni.hs300_constituents, uni.csi500_constituents):
        try:
            df = fn()
        except Exception:
            continue
        code_col = next((c for c in df.columns if "成分券代码" in c), None)
        name_col = next((c for c in df.columns if "成分券名称" in c), None)
        if not (code_col and name_col):
            continue
        for _, row in df.iterrows():
            code = str(row[code_col]).zfill(6)
            name = str(row[name_col])
            if code in seen:
                continue
            if q in code or q in name:
                matches.append({"code": code, "name": name})
                seen.add(code)
                if len(matches) >= limit:
                    return {"items": matches}
    return {"items": matches}


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


@router.get("/screen/presets", summary="策略预设列表（首页用）")
def screen_presets():
    return {
        "presets": [
            {"key": k, "weights": PRESET_WEIGHTS[k], **PRESET_LABELS[k]}
            for k in ("balanced", "momentum", "value", "growth", "dividend")
        ]
    }


@router.post("/screen", summary="股票筛选器（首页核心 API）")
def screen(req: ScreenRequest):
    """
    一站式：
    1) 拉指定指数成分股，取前 pool_limit 只
    2) 按 preset 权重打四维分
    3) 过滤 total >= min_score
    4) 返回 top_n 只
    """
    from data_layer import universe as uni
    from analysis import scorer as _scorer
    from analysis import technical, fundamental_score, moneyflow_score
    import pandas as pd

    fn_map = {
        "000300": uni.hs300_constituents,
        "000905": uni.csi500_constituents,
        "000852": uni.csi1000_constituents,
    }
    if req.pool not in fn_map:
        raise HTTPException(400, f"不支持的指数: {req.pool}")

    df_idx = fn_map[req.pool]()
    code_col = next((c for c in df_idx.columns if "成分券代码" in c), None) \
        or next((c for c in df_idx.columns if "代码" in c and "指数" not in c), None)
    name_col = next((c for c in df_idx.columns if "成分券名称" in c), None) \
        or next((c for c in df_idx.columns if "名称" in c and "指数" not in c and "英文" not in c and "交易所" not in c), None)

    subset = df_idx.head(req.pool_limit)
    weights = req.custom_weights if req.custom_weights else PRESET_WEIGHTS.get(req.preset, PRESET_WEIGHTS["balanced"])

    rows = []
    for _, row in subset.iterrows():
        sym = str(row[code_col]).zfill(6)
        name = str(row[name_col]) if name_col else sym
        r = _scorer.score_one(sym, as_of=req.as_of, weights=weights, use_llm=req.use_llm)
        r["name"] = name
        rows.append(r)

    # 过滤 + 排序
    filtered = [r for r in rows if r["total"] >= req.min_score]
    filtered.sort(key=lambda x: x["total"], reverse=True)
    top = filtered[: req.top_n]

    return {
        "preset": "custom" if req.custom_weights else req.preset,
        "preset_name": "自定义" if req.custom_weights else PRESET_LABELS.get(req.preset, {}).get("name", req.preset),
        "weights": weights,
        "pool_size": len(subset),
        "matched": len(filtered),
        "results": [
            {
                "symbol": r["symbol"],
                "name": r["name"],
                "total": r["total"],
                "technical": r["technical"],
                "fundamental": r["fundamental"],
                "sentiment": r["sentiment"],
                "moneyflow": r["moneyflow"],
                "detail": r["detail"],
            }
            for r in top
        ],
    }


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
    from backtest import engine, report

    fn_map = {
        "000300": uni.hs300_constituents,
        "000905": uni.csi500_constituents,
        "000852": uni.csi1000_constituents,
    }
    if req.pool not in fn_map:
        raise HTTPException(400, f"不支持的指数: {req.pool}")

    try:
        df_idx = fn_map[req.pool]()
    except Exception as e:
        raise HTTPException(503, f"股票池数据源暂时不可用：{e}")

    code_col = next((c for c in df_idx.columns if "成分券代码" in c), None) \
        or next((c for c in df_idx.columns if "代码" in c and "指数" not in c), None)
    symbols = [str(x).zfill(6) for x in df_idx[code_col].tolist()]
    if req.limit:
        symbols = symbols[: req.limit]

    # 根据 strategy_type 选择策略函数
    if req.strategy_type == "technical":
        if not req.strategy_id:
            raise HTTPException(400, "strategy_type=technical 时必须指定 strategy_id")
        from strategies.adapter import make_strategy_fn
        from strategies.registry import bootstrap
        bootstrap()
        strategy_fn = make_strategy_fn(
            req.strategy_id,
            params=req.strategy_params or {},
            position_size=req.position_size or 0.18,
        )
        strategy_kwargs = {}
        display_name = req.strategy_id
        display_meta = {"strategy_id": req.strategy_id, "params": req.strategy_params or {}}
    else:
        from my_strategies import swing_v1
        # 权重来源：custom > preset
        if req.custom_weights:
            weights = req.custom_weights
        else:
            weights = PRESET_WEIGHTS.get(req.preset, PRESET_WEIGHTS["balanced"])
        strategy_fn = swing_v1.generate_signals
        strategy_kwargs = {
            "min_score": req.min_score,
            "use_llm": False,
            "weights": weights,
        }
        display_name = f"swing_v1_{req.preset}"
        display_meta = {
            "preset": req.preset,
            "preset_name": PRESET_LABELS.get(req.preset, {}).get("name", req.preset),
            "weights": weights,
        }

    try:
        result = engine.run(
            strategy_fn=strategy_fn,
            universe=symbols,
            start=req.start,
            end=req.end,
            initial_cash=req.initial_cash,
            strategy_kwargs=strategy_kwargs,
        )
    except Exception as e:
        raise HTTPException(503, f"回测执行失败：{e}")

    md_path = report.render(result, strategy_name=display_name)
    snapshots = result["snapshots"].copy()
    snapshots["date"] = snapshots["date"].astype(str)
    return {
        "strategy_type": req.strategy_type,
        "strategy": display_name,
        **display_meta,
        "metrics": result["metrics"],
        "snapshots": snapshots.to_dict(orient="records"),
        "trades_count": len(result["portfolio"].trades),
        "trades_sample": [
            {"date": t.date, "symbol": t.symbol, "side": t.side,
             "shares": t.shares, "price": t.price, "reason": t.reason}
            for t in result["portfolio"].trades[-10:]
        ],
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


# ================ 策略库 =================


@router.get("/strategies", summary="所有可用策略")
def list_strategies(kind: Optional[str] = None):
    from strategies.registry import registry, bootstrap
    bootstrap()
    metas = registry.list_all()
    if kind:
        metas = [m for m in metas if m.kind.value == kind]
    result = []
    for m in metas:
        result.append({
            "id": m.id, "name": m.name, "kind": m.kind.value,
            "category": m.category, "description": m.description,
            "tags": m.tags,
            "params": [
                {"name": p.name, "label": p.label, "type": p.type,
                 "default": p.default, "min": p.min, "max": p.max,
                 "step": p.step, "choices": p.choices, "help": p.help}
                for p in m.params
            ],
        })
    return {"count": len(result), "strategies": result}


@router.get("/strategies/{strategy_id}", summary="策略详情")
def get_strategy(strategy_id: str):
    from strategies.registry import registry, bootstrap
    bootstrap()
    s = registry.get(strategy_id)
    if s is None:
        raise HTTPException(404, f"策略未找到: {strategy_id}")
    m = s.meta
    return {
        "id": m.id, "name": m.name, "kind": m.kind.value,
        "category": m.category, "description": m.description,
        "long_description": m.long_description, "tags": m.tags,
        "params": [
            {"name": p.name, "label": p.label, "type": p.type,
             "default": p.default, "min": p.min, "max": p.max,
             "step": p.step, "choices": p.choices, "help": p.help}
            for p in m.params
        ],
    }


@router.get("/strategies/builder/indicators", summary="条件构建器可用指标")
def builder_indicators():
    from strategies.builder import list_indicators
    return {"indicators": list_indicators()}


class BuilderSaveRequest(BaseModel):
    id: str
    name: str
    description: str = ""
    buy: dict = Field(default_factory=dict)
    sell: dict = Field(default_factory=dict)


@router.post("/strategies/builder", summary="保存条件构建器策略")
def save_builder_strategy(req: BuilderSaveRequest):
    from strategies.builder import validate_spec, BuilderStrategy
    from strategies.registry import registry
    import yaml as _yaml

    spec = req.model_dump()
    ok, err = validate_spec(spec)
    if not ok:
        raise HTTPException(400, err)

    # 保存到 configs/user_strategies/{id}.yaml
    out = Path("configs/user_strategies") / f"{spec['id']}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")

    # 立即注册（覆盖旧版）
    strat = BuilderStrategy(spec)
    registry.register(strat)

    return {"ok": True, "id": spec["id"]}


@router.delete("/strategies/builder/{strategy_id}", summary="删除条件构建器策略")
def delete_builder_strategy(strategy_id: str):
    from strategies.registry import registry
    out = Path("configs/user_strategies") / f"{strategy_id}.yaml"
    if out.exists():
        out.unlink()
    registry.unregister(strategy_id)
    return {"ok": True}


# ================ 用户 Python 策略 =================


USER_PY_DIR = Path("strategies/user_defined")


@router.get("/strategies/python/template", summary="Python 策略模板")
def python_template():
    from strategies.user_defined_loader import DEFAULT_TEMPLATE
    return {"template": DEFAULT_TEMPLATE}


@router.get("/strategies/python/list", summary="用户 Python 策略文件列表")
def list_python_strategies():
    if not USER_PY_DIR.exists():
        return {"files": []}
    items = []
    for f in sorted(USER_PY_DIR.glob("*.py")):
        if f.name.startswith("__"):
            continue
        items.append({"filename": f.name, "size": f.stat().st_size,
                      "mtime": f.stat().st_mtime})
    return {"files": items}


@router.get("/strategies/python/{filename}", summary="读取用户 Python 策略源码")
def read_python_strategy(filename: str):
    if "/" in filename or ".." in filename or not filename.endswith(".py"):
        raise HTTPException(400, "非法文件名")
    p = USER_PY_DIR / filename
    if not p.exists():
        raise HTTPException(404, "文件不存在")
    return {"filename": filename, "source": p.read_text(encoding="utf-8")}


class PythonSaveRequest(BaseModel):
    filename: str
    source: str


@router.post("/strategies/python", summary="保存用户 Python 策略")
def save_python_strategy(req: PythonSaveRequest):
    if "/" in req.filename or ".." in req.filename or not req.filename.endswith(".py"):
        raise HTTPException(400, "文件名必须是纯文件名且以 .py 结尾")

    USER_PY_DIR.mkdir(parents=True, exist_ok=True)
    p = USER_PY_DIR / req.filename
    p.write_text(req.source, encoding="utf-8")

    # 尝试加载并注册
    try:
        from strategies.user_defined_loader import load_user_python
        from strategies.registry import registry
        strat = load_user_python(p)
        if strat:
            registry.register(strat)
        return {"ok": True, "filename": req.filename, "registered": bool(strat),
                "strategy_id": strat.meta.id if strat else None}
    except Exception as e:
        raise HTTPException(400, f"策略保存但注册失败：{e}。请检查语法。")


@router.delete("/strategies/python/{filename}", summary="删除用户 Python 策略")
def delete_python_strategy(filename: str):
    if "/" in filename or ".." in filename or not filename.endswith(".py"):
        raise HTTPException(400, "非法文件名")
    p = USER_PY_DIR / filename
    if p.exists():
        p.unlink()
    return {"ok": True}


# ================ 设置 =================


ENV_FILE = Path(".env")
STRATEGY_FILE = Path("configs/strategy.yaml")

# 允许通过设置页读写的环境变量白名单（避免用户误改敏感/系统变量）
ENV_KEYS = [
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "LLM_PROVIDER",
    "TUSHARE_TOKEN", "DATA_DIR",
    "FEISHU_WEBHOOK", "DINGTALK_WEBHOOK", "DINGTALK_SECRET", "WECHAT_WEBHOOK",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_TO",
]

SENSITIVE_KEYS = {
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY",
    "TUSHARE_TOKEN", "SMTP_PASS", "DINGTALK_SECRET",
}


def _mask(val: str) -> str:
    if not val:
        return ""
    if len(val) <= 8:
        return "***"
    return val[:4] + "***" + val[-4:]


def _read_env_file() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    result = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        result[k.strip()] = v.strip().strip('"').strip("'")
    return result


@router.get("/settings", summary="读所有设置")
def get_settings():
    """敏感值（API key 等）会脱敏，只显示头尾 4 位。"""
    env_file = _read_env_file()
    env_data = {}
    for k in ENV_KEYS:
        val = env_file.get(k) or os.environ.get(k, "")
        if k in SENSITIVE_KEYS and val:
            env_data[k] = {"value": _mask(val), "set": True, "masked": True}
        else:
            env_data[k] = {"value": val, "set": bool(val), "masked": False}

    # 策略配置
    strategy = {}
    if STRATEGY_FILE.exists():
        import yaml
        strategy = yaml.safe_load(STRATEGY_FILE.read_text(encoding="utf-8")) or {}

    return {"env": env_data, "strategy": strategy}


class SaveSettingsRequest(BaseModel):
    env: dict[str, str] = Field(default_factory=dict)
    strategy: Optional[dict] = None


@router.post("/settings", summary="保存设置")
def save_settings(req: SaveSettingsRequest):
    """
    - env：只更新白名单里的 key；空字符串表示不修改（避免误覆盖已存在的敏感值）
    - strategy：整体覆写 configs/strategy.yaml
    """
    env_file = _read_env_file()
    for k, v in req.env.items():
        if k not in ENV_KEYS:
            continue
        # 空字符串 = 不修改（如果用户想清空，前端传 "__CLEAR__"）
        if v == "__CLEAR__":
            env_file.pop(k, None)
        elif v == "" or v.startswith("***"):
            # 空 或 仍是脱敏后的显示值 → 视为未修改
            continue
        else:
            env_file[k] = v
            os.environ[k] = v  # 立即生效

    # 重写 .env 文件
    lines = ["# tonghuashunAI 配置文件（Web 设置页自动生成/维护）", ""]
    lines.append("# ============ LLM API ============")
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "LLM_PROVIDER"):
        lines.append(f'{k}={env_file.get(k, "")}')
    lines += ["", "# ============ 数据源 ============"]
    for k in ("TUSHARE_TOKEN", "DATA_DIR"):
        lines.append(f'{k}={env_file.get(k, "")}')
    lines += ["", "# ============ 通知 ============"]
    for k in ("FEISHU_WEBHOOK", "DINGTALK_WEBHOOK", "DINGTALK_SECRET", "WECHAT_WEBHOOK",
              "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_TO"):
        lines.append(f'{k}={env_file.get(k, "")}')
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if req.strategy is not None:
        import yaml
        STRATEGY_FILE.parent.mkdir(parents=True, exist_ok=True)
        STRATEGY_FILE.write_text(
            yaml.safe_dump(req.strategy, allow_unicode=True, sort_keys=False),
            encoding="utf-8"
        )

    return {"ok": True}
