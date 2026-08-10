"""
FastAPI 路由
============

所有业务 API 都挂在 /api/* 下。
"""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = PROJECT_ROOT / "configs"
LOGS_DIR = PROJECT_ROOT / "logs"
USER_STRATEGY_DIR = CONFIGS_DIR / "user_strategies"


router = APIRouter()


# ================ 数据模型 =================


class ScoreRequest(BaseModel):
    symbol: str = Field(..., description="6 位股票代码")
    as_of: Optional[str] = Field(None, description="截止日期 YYYY-MM-DD")
    use_llm: bool = True
    preset: Optional[str] = Field(None, description="策略预设 key；若同时传 custom_weights 则以后者为准")
    custom_weights: Optional[dict] = Field(None, description="自定义四维权重，键：technical/fundamental/sentiment/moneyflow")


class RankRequest(BaseModel):
    symbols: list[str]
    as_of: Optional[str] = None
    top_n: Optional[int] = 10
    use_llm: bool = False


class ScreenRequest(BaseModel):
    """一站式股票筛选器：选池 → 筛选 → 打分 → 返回结果。"""
    pool: str = Field("000300", description="000300/000905/000852 指数成分股；all=全 A 可交易股票")
    pool_limit: int = Field(30, description="从池子取前 N 只（数量越大越慢）")
    preset: str = Field("balanced", description="策略预设：balanced/momentum/value/growth/dividend")
    min_score: float = Field(0, description="综合分下限（0-100）")
    top_n: int = Field(10, description="最终返回前 N 只")
    use_llm: bool = Field(False, description="是否用 LLM 分析情绪面（慢)")
    as_of: Optional[str] = None
    custom_weights: Optional[dict] = Field(None, description="覆盖 preset 的自定义四维权重")

    # 全 A 池 (pool="all") 时可用的粗过滤
    exchange: Optional[str] = Field(None, description="交易所过滤：sh/sz/bj/main/kcb/cyb/all")
    min_price: Optional[float] = Field(None, description="最低股价（元）")
    max_price: Optional[float] = Field(None, description="最高股价（元）")
    min_market_cap: Optional[float] = Field(None, description="最小总市值（亿元）")
    max_market_cap: Optional[float] = Field(None, description="最大总市值（亿元）")
    exclude_st: bool = Field(True, description="是否排除 ST/*ST/退市股票")


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


def _probe(fn, ok_check=lambda x: x is not None and hasattr(x, "empty") and not x.empty):
    """执行一个数据源探针，统一返回 (ok, detail, latency_ms, error)。"""
    import time
    t0 = time.time()
    try:
        result = fn()
        latency = int((time.time() - t0) * 1000)
        if ok_check(result):
            detail = f"{len(result)} 行" if hasattr(result, "__len__") else "OK"
            return True, detail, latency, None
        return False, "空", latency, None
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return False, str(e)[:80], latency, type(e).__name__


@router.get("/status/datasources", summary="数据接口情况")
def check_datasources():
    """
    实时探测各数据源。每一类接口尝试所有备选源，报告：
      - 主源当前可用性
      - 备选源可用性
      - 当前会真正使用哪个源
    结果被短时缓存（30 秒）。前端定时轮询。
    """
    import time
    from data_layer.cache import _data_dir
    import json as _json

    cache_file = _data_dir() / "_health.json"
    if cache_file.exists() and (time.time() - cache_file.stat().st_mtime) < 30:
        try:
            return _json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    test_symbol = "600519"
    checks = []

    # --- 1. 日线行情（多源）---
    import akshare as ak
    from data_layer.market import _try_eastmoney, _try_sina, _try_tencent
    daily_sources = []
    for name, fn in [("eastmoney", _try_eastmoney), ("sina", _try_sina), ("tencent", _try_tencent)]:
        ok, detail, lat, err = _probe(lambda fn=fn: fn(test_symbol, "2024-11-01", "2024-12-31", "qfq"))
        daily_sources.append({"source": name, "ok": ok, "latency_ms": lat, "detail": detail})
    active = next((s["source"] for s in daily_sources if s["ok"]), None)
    checks.append({
        "name": "日线行情", "key": "daily",
        "ok": active is not None,
        "active_source": active or "—",
        "sources": daily_sources,
        "note": "多源自动回退：东财 → 新浪 → 腾讯",
    })

    # --- 2. 全 A 快照（多源） ---
    snapshot_sources = []
    # 东财
    ok, detail, lat, err = _probe(lambda: ak.stock_zh_a_spot_em())
    snapshot_sources.append({"source": "eastmoney", "ok": ok, "latency_ms": lat, "detail": detail})
    # 新浪
    ok, detail, lat, err = _probe(lambda: ak.stock_zh_a_spot())
    snapshot_sources.append({"source": "sina", "ok": ok, "latency_ms": lat, "detail": detail})
    active = next((s["source"] for s in snapshot_sources if s["ok"]), None)
    if not active:
        # 试探分交易所是否可用（只 ping sh 主板一个当代表，避免探针本身太慢）
        ok, detail, lat, err = _probe(lambda: ak.stock_sh_a_spot_em())
        snapshot_sources.append({"source": "per_exchange(sh)", "ok": ok, "latency_ms": lat, "detail": detail})
        if ok:
            active = "per_exchange"
    checks.append({
        "name": "全 A 实时快照", "key": "snapshot",
        "ok": active is not None,
        "active_source": active or "—",
        "sources": snapshot_sources,
        "note": "供「股票池 = 全 A」使用。回退：东财 → 新浪 → 分交易所拼接",
    })

    # --- 3. 沪深 300 成分股 ---
    from data_layer import universe
    universe_sources = []
    ok, detail, lat, err = _probe(lambda: ak.index_stock_cons_csindex(symbol="000300"))
    universe_sources.append({"source": "csindex", "ok": ok, "latency_ms": lat, "detail": detail})
    active = "csindex" if ok else None
    checks.append({
        "name": "指数成分股", "key": "universe",
        "ok": ok, "active_source": active or "—",
        "sources": universe_sources,
        "note": "沪深 300 / 中证 500 / 中证 1000 成分股（中证指数官方）",
    })

    # --- 4. 北向资金 ---
    from data_layer import moneyflow
    nb_sources = []
    ok, detail, lat, err = _probe(lambda: moneyflow.northbound_daily())
    nb_sources.append({"source": "eastmoney", "ok": ok, "latency_ms": lat, "detail": detail})
    checks.append({
        "name": "北向资金", "key": "northbound",
        "ok": ok, "active_source": "eastmoney" if ok else "—",
        "sources": nb_sources,
        "note": "资金面维度打分需要",
    })

    # --- 5. 财务摘要 ---
    from data_layer import fundamental
    fin_sources = []
    ok, detail, lat, err = _probe(lambda: fundamental.financial_abstract(test_symbol))
    fin_sources.append({"source": "akshare_abstract", "ok": ok, "latency_ms": lat, "detail": detail})
    checks.append({
        "name": "财务摘要", "key": "fundamental",
        "ok": ok, "active_source": "akshare" if ok else "—",
        "sources": fin_sources,
        "note": "基本面 ROE / 增长率打分需要",
    })

    # --- 6. 财联社电报 ---
    from data_layer import sentiment as sent_data
    news_sources = []
    ok, detail, lat, err = _probe(lambda: sent_data.cls_news(limit=5))
    news_sources.append({"source": "cls", "ok": ok, "latency_ms": lat, "detail": detail})
    checks.append({
        "name": "财联社电报", "key": "cls_news",
        "ok": ok, "active_source": "cls" if ok else "—",
        "sources": news_sources,
        "note": "大盘情绪 / 日报生成用",
    })

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


@router.delete("/portfolio/{account}", summary="删除账户（含引擎、委托、状态一并清理）")
def delete_portfolio(account: str):
    from paper_trade import portfolio as pfolio
    from execution.runner import stop_runner, STATE_DIR
    from execution.broker import ORDERS_DIR

    p = pfolio.default_path(account)
    if not p.exists():
        raise HTTPException(404, f"账户 {account} 不存在")
    # 先停引擎（若有）
    stop_runner(account)
    # 账户文件
    p.unlink()
    # 引擎 state
    (STATE_DIR / f"{account}.json").unlink(missing_ok=True)
    # 委托簿
    orders_dir = ORDERS_DIR / account
    if orders_dir.exists():
        for f in orders_dir.glob("*"):
            f.unlink(missing_ok=True)
        orders_dir.rmdir()
    return {"ok": True, "account": account}


@router.post("/portfolio/new", summary="新建账户")
def new_portfolio(req: NewPortfolioRequest):
    from paper_trade import portfolio as pfolio
    p = pfolio.default_path(req.account_id)
    if p.exists():
        raise HTTPException(409, f"账户 {req.account_id} 已存在")
    port = pfolio.Portfolio.new(req.account_id, req.initial_cash)
    port.save(p)
    return {"ok": True, "path": str(p), "account": port.to_dict()}


@router.get("/portfolio", summary="列出所有账户（附余额、持仓、引擎状态）")
def list_portfolios():
    from paper_trade import portfolio as pfolio
    from execution.runner import RunnerState

    root = LOGS_DIR / "portfolio"
    if not root.exists():
        return {"accounts": []}

    items = []
    for f in sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            port = pfolio.Portfolio.load(f)
        except Exception:
            continue
        total = port.cash + sum(
            p.shares * (p.last_price or p.avg_cost) for p in port.positions.values()
        )
        pnl_pct = ((total - port.initial_cash) / port.initial_cash * 100) if port.initial_cash else 0.0
        state = RunnerState.load(port.account_id)
        items.append({
            "account_id": port.account_id,
            "initial_cash": port.initial_cash,
            "cash": round(port.cash, 2),
            "total_value": round(total, 2),
            "pnl_pct": round(pnl_pct, 2),
            "n_positions": len(port.positions),
            "n_trades": len(port.trades),
            "updated_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
            "engine": {
                "status": state.status if state else "never_started",
                "strategy_id": state.strategy_id if state else None,
                "tick_seconds": state.tick_seconds if state else None,
                "last_tick_at": state.last_tick_at if state else None,
            },
        })
    return {"accounts": items}


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
    # 权重来源优先级：custom_weights > preset > 默认（configs/strategy.yaml 里的 balanced）
    weights = None
    weights_source = "default"
    weights_source_name = "默认"
    if req.custom_weights:
        weights = req.custom_weights
        weights_source = "custom"
        weights_source_name = "自定义"
    elif req.preset and req.preset in PRESET_WEIGHTS:
        weights = PRESET_WEIGHTS[req.preset]
        weights_source = req.preset
        weights_source_name = PRESET_LABELS.get(req.preset, {}).get("name", req.preset)
    try:
        result = score_one(req.symbol, as_of=req.as_of, weights=weights, use_llm=req.use_llm)
        result["weights"] = weights or _default_weights()
        result["weights_source"] = weights_source
        result["weights_source_name"] = weights_source_name
        return result
    except Exception as e:
        raise HTTPException(500, f"评分失败: {e}")


def _default_weights() -> dict:
    """兜底：读 configs/strategy.yaml 里的 swing_v1 权重。"""
    import yaml
    try:
        with open(CONFIGS_DIR / "strategy.yaml", encoding="utf-8") as f:
            return yaml.safe_load(f)["swing_v1"]["weights"]
    except Exception:
        return PRESET_WEIGHTS["balanced"]


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


def _exchange_of(code: str) -> str:
    """按代码首位判断交易所/板块：sh/sz/bj + main/kcb/cyb。"""
    if code.startswith("60"):
        return "sh_main"
    if code.startswith("688"):
        return "kcb"          # 科创板
    if code.startswith("00"):
        return "sz_main"
    if code.startswith("30"):
        return "cyb"          # 创业板
    if code.startswith(("83", "87", "43")):
        return "bj"
    return "other"


def _filter_all_a_pool(req: "ScreenRequest") -> list[dict]:
    """
    从全 A 实时快照拉数据并按用户条件过滤，返回 [{symbol, name}, ...]。
    过滤维度：交易所/板块、股价区间、总市值区间、是否排除 ST。
    """
    from data_layer import market
    try:
        df = market.snapshot()
    except Exception as e:
        raise HTTPException(503, f"全 A 快照数据源不可用：{e}")
    if df is None or df.empty:
        raise HTTPException(503, "全 A 快照为空")

    code_col = next((c for c in df.columns if c in ("代码", "symbol")), None)
    name_col = next((c for c in df.columns if c in ("名称", "name")), None)
    price_col = next((c for c in df.columns if c in ("最新价", "现价", "close")), None)
    mcap_col = next((c for c in df.columns if "总市值" in c), None)
    if not (code_col and name_col):
        raise HTTPException(500, f"快照数据列不识别：{list(df.columns)[:10]}")

    df = df.copy()
    df[code_col] = df[code_col].astype(str).str.zfill(6)

    # 交易所 / 板块过滤
    exch = (req.exchange or "all").lower()
    if exch != "all":
        loc = df[code_col].map(_exchange_of)
        mask_map = {
            "sh":   loc.isin({"sh_main", "kcb"}),
            "sz":   loc.isin({"sz_main", "cyb"}),
            "bj":   loc == "bj",
            "main": loc.isin({"sh_main", "sz_main"}),
            "kcb":  loc == "kcb",
            "cyb":  loc == "cyb",
        }
        if exch not in mask_map:
            raise HTTPException(400, f"不支持的 exchange: {exch}")
        df = df[mask_map[exch]]

    # 排除 ST/退市
    if req.exclude_st:
        df = df[~df[name_col].astype(str).str.contains("ST|退", case=False, regex=True, na=False)]

    # 股价过滤
    if price_col:
        pr = pd.to_numeric(df[price_col], errors="coerce")
        df = df[pr.notna() & (pr > 0)]
        if req.min_price is not None:
            df = df[pd.to_numeric(df[price_col], errors="coerce") >= req.min_price]
        if req.max_price is not None:
            df = df[pd.to_numeric(df[price_col], errors="coerce") <= req.max_price]

    # 市值过滤（用户输入是亿元；AkShare 总市值单位是元）
    if mcap_col:
        mv_yi = pd.to_numeric(df[mcap_col], errors="coerce") / 1e8
        df = df[mv_yi.notna()]
        if req.min_market_cap is not None:
            df = df[mv_yi.loc[df.index] >= req.min_market_cap]
        if req.max_market_cap is not None:
            df = df[mv_yi.loc[df.index] <= req.max_market_cap]
        # 按总市值降序，让大的先被评分（更快得到有意义结果）
        df = df.assign(_mv_sort=pd.to_numeric(df[mcap_col], errors="coerce")).sort_values("_mv_sort", ascending=False)

    # 截取前 pool_limit
    subset_df = df.head(req.pool_limit)
    return [
        {"symbol": str(row[code_col]).zfill(6), "name": str(row[name_col])}
        for _, row in subset_df.iterrows()
    ]


@router.post("/screen", summary="股票筛选器（首页核心 API）")
def screen(req: ScreenRequest):
    """
    一站式：
    1) 拉指定指数成分股（或全 A 快照），取前 pool_limit 只
    2) 按 preset 权重打四维分
    3) 过滤 total >= min_score
    4) 返回 top_n 只
    """
    from data_layer import universe as uni
    from analysis import scorer as _scorer

    fn_map = {
        "000300": uni.hs300_constituents,
        "000905": uni.csi500_constituents,
        "000852": uni.csi1000_constituents,
    }

    if req.pool == "all":
        # 全 A 池：拉实时快照，按用户过滤条件筛
        subset_items = _filter_all_a_pool(req)
    elif req.pool in fn_map:
        df_idx = fn_map[req.pool]()
        code_col = next((c for c in df_idx.columns if "成分券代码" in c), None) \
            or next((c for c in df_idx.columns if "代码" in c and "指数" not in c), None)
        name_col = next((c for c in df_idx.columns if "成分券名称" in c), None) \
            or next((c for c in df_idx.columns if "名称" in c and "指数" not in c and "英文" not in c and "交易所" not in c), None)
        subset_items = []
        for _, row in df_idx.head(req.pool_limit).iterrows():
            sym = str(row[code_col]).zfill(6)
            name = str(row[name_col]) if name_col else sym
            subset_items.append({"symbol": sym, "name": name})
    else:
        raise HTTPException(400, f"不支持的股票池: {req.pool}")

    weights = req.custom_weights if req.custom_weights else PRESET_WEIGHTS.get(req.preset, PRESET_WEIGHTS["balanced"])

    rows = []
    for it in subset_items:
        r = _scorer.score_one(it["symbol"], as_of=req.as_of, weights=weights, use_llm=req.use_llm)
        r["name"] = it["name"]
        rows.append(r)
    subset = subset_items  # 兼容后面的 pool_size

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
        save_to = LOGS_DIR / "reports" / f"{as_of}.md"

    md = daily_report.render(as_of=as_of, symbols=symbols, top_n=req.top_n, save_to=save_to)
    return {"as_of": as_of, "path": str(save_to) if save_to else None, "markdown": md}


@router.get("/report/list", summary="历史报告列表")
def list_reports():
    root = LOGS_DIR / "reports"
    if not root.exists():
        return {"reports": []}
    reports = sorted([f.name for f in root.glob("*.md")], reverse=True)
    return {"reports": reports}


@router.get("/report/{name}", summary="读某份历史报告")
def read_report(name: str):
    p = LOGS_DIR / "reports" / name
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

    with open(CONFIGS_DIR / "strategy.yaml", encoding="utf-8") as f:
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


def _prepare_backtest(req: BacktestRequest):
    """
    共用逻辑：解析 pool → symbols、构造 strategy_fn/kwargs、display_meta。
    返回 (symbols, strategy_fn, strategy_kwargs, display_name, display_meta)。
    """
    from data_layer import universe as uni

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
    return symbols, strategy_fn, strategy_kwargs, display_name, display_meta


def _serialize_backtest_result(result: dict, display_name: str, display_meta: dict,
                                strategy_type: str, req: "BacktestRequest") -> dict:
    """把 engine.run 的返回值转成前端可用的 JSON 结构。"""
    from backtest import report
    md_path = report.render(result, strategy_name=display_name)
    snapshots = result["snapshots"].copy()
    snapshots["date"] = snapshots["date"].astype(str)
    return {
        "strategy_type": strategy_type,
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


@router.post("/backtest/run", summary="启动一次回测任务（后台运行，前端轮询）")
def backtest_run(req: BacktestRequest):
    from backtest import engine
    from backtest.tasks import start_task

    symbols, strategy_fn, strategy_kwargs, display_name, display_meta = _prepare_backtest(req)
    label = f"{display_name} · {req.pool} · {req.start}~{req.end}"

    def run_fn(progress_cb):
        result = engine.run(
            strategy_fn=strategy_fn,
            universe=symbols,
            start=req.start,
            end=req.end,
            initial_cash=req.initial_cash,
            strategy_kwargs=strategy_kwargs,
            progress_cb=progress_cb,
        )
        return _serialize_backtest_result(result, display_name, display_meta,
                                          req.strategy_type, req)

    task = start_task(label=label, request=req.model_dump(), run_fn=run_fn)
    return {
        "task_id": task.task_id,
        "status": task.status,
        "label": task.label,
        "started_at": task.started_at,
    }


@router.get("/backtest/tasks", summary="回测历史任务列表（含正在跑的）")
def backtest_task_list(limit: int = 30):
    from backtest.tasks import list_tasks
    return {"tasks": list_tasks(limit=limit)}


@router.get("/backtest/tasks/{task_id}", summary="查询单个回测任务（含结果或进度）")
def backtest_task_get(task_id: str):
    from backtest.tasks import BacktestTask
    t = BacktestTask.load(task_id)
    if t is None:
        raise HTTPException(404, "任务不存在")
    return {
        "task_id": t.task_id,
        "label": t.label,
        "status": t.status,
        "started_at": t.started_at,
        "finished_at": t.finished_at,
        "progress": t.progress,
        "request": t.request,
        "result": t.result,
        "error": t.error,
    }


@router.post("/backtest/tasks/{task_id}/cancel", summary="取消正在跑的回测")
def backtest_task_cancel(task_id: str):
    from backtest.tasks import cancel_task
    t = cancel_task(task_id)
    if t is None:
        raise HTTPException(404, "任务不存在")
    return {"task_id": t.task_id, "status": t.status}


# ================ Qbot 集成 =================


QBOT_STRATEGY_DIR = PROJECT_ROOT / "vendor" / "Qbot" / "qbot" / "strategies"
QBOT_DOCS_DIR = PROJECT_ROOT / "vendor" / "Qbot" / "docs"


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
    root = QBOT_DOCS_DIR
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
    p = QBOT_DOCS_DIR / path
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


@router.get("/strategies/builder/{strategy_id}/spec",
            summary="读取条件构建器策略的完整 spec（用于编辑）")
def get_builder_spec(strategy_id: str):
    """
    从 configs/user_strategies/{id}.yaml 读原始 spec，供前端「编辑」按钮回填表单。
    """
    import yaml as _yaml
    out = USER_STRATEGY_DIR / f"{strategy_id}.yaml"
    if out.exists():
        return _yaml.safe_load(out.read_text(encoding="utf-8"))
    # 兜底：如果不在磁盘（例如内存中的 BuilderStrategy），直接从 registry 里读
    from strategies.registry import registry
    s = registry.get(strategy_id)
    if s is None or not hasattr(s, "spec"):
        raise HTTPException(404, f"策略 {strategy_id} 不存在或不是条件构建器策略")
    return s.spec


class BuilderFromAIRequest(BaseModel):
    prompt: str = Field(..., description="中文自然语言描述你想要的策略")
    suggested_id: Optional[str] = None
    suggested_name: Optional[str] = None
    save: bool = Field(False, description="设为 true 时校验通过直接注册为策略")


@router.post("/strategies/builder/from_ai", summary="AI 版条件构建器：中文描述 → 策略 JSON")
def builder_from_ai(req: BuilderFromAIRequest):
    """
    调用 LLM 把用户的中文思路转成条件构建器 spec。
    - 未配置 LLM：走 stub 返回一个示例，`provider` 字段会标 `stub`
    - 校验失败：返回 400，附 LLM 原始回复
    - save=True：校验通过后立即写入 configs/user_strategies/*.yaml 并注册
    """
    from ai_analysis.builder_ai import generate_spec
    from strategies.builder import BuilderStrategy
    from strategies.registry import registry
    import yaml as _yaml

    try:
        result = generate_spec(
            user_prompt=req.prompt,
            suggested_id=req.suggested_id,
            suggested_name=req.suggested_name,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"AI 生成失败：{e}")

    if req.save:
        spec = result["spec"]
        out = USER_STRATEGY_DIR / f"{spec['id']}.yaml"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
        registry.register(BuilderStrategy(spec))
        result["saved_to"] = str(out)
        result["registered"] = True

    return result


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
    out = USER_STRATEGY_DIR / f"{spec['id']}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")

    # 立即注册（覆盖旧版）
    strat = BuilderStrategy(spec)
    registry.register(strat)

    return {"ok": True, "id": spec["id"]}


@router.delete("/strategies/builder/{strategy_id}", summary="删除条件构建器策略")
def delete_builder_strategy(strategy_id: str):
    from strategies.registry import registry
    out = USER_STRATEGY_DIR / f"{strategy_id}.yaml"
    if out.exists():
        out.unlink()
    registry.unregister(strategy_id)
    return {"ok": True}


# ================ 用户 Python 策略 =================


USER_PY_DIR = PROJECT_ROOT / "strategies" / "user_defined"


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


ENV_FILE = PROJECT_ROOT / ".env"
STRATEGY_FILE = CONFIGS_DIR / "strategy.yaml"

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


# ================ AI Agent（自主回测搜索） =================


class AgentRunRequest(BaseModel):
    goal: str = Field(..., description="用户给 AI 的目标，例如「半年内找到累计收益 >100% 的策略」")
    max_iterations: int = Field(10, ge=1, le=50, description="最多允许 AI 决策多少轮")
    reference_ids: list[str] = Field(
        default_factory=list,
        description="引用旧任务的 ID 列表（12 位 hex），旧任务的经验会被摘要注入 prompt，"
                    "让 AI 不用重复试错。可以从「历史 AI 任务」列表复制。",
    )


@router.post("/agent/run", summary="启动 AI 自主回测研究任务（后台运行）")
def agent_run(req: AgentRunRequest):
    from ai_analysis.agent_loop import start_agent, AgentTask
    if not req.goal.strip():
        raise HTTPException(400, "goal 不能为空")
    # 验证 reference_ids 至少有一个能找到，否则前端可能给错了
    missing = [rid for rid in req.reference_ids
               if rid.strip() and AgentTask.load(rid.strip()) is None]
    if missing:
        raise HTTPException(400, f"引用的任务 ID 不存在：{', '.join(missing)}")
    task = start_agent(
        req.goal,
        max_iterations=req.max_iterations,
        reference_ids=req.reference_ids,
    )
    return {
        "task_id": task.task_id,
        "status": task.status,
        "provider": task.provider,
        "started_at": task.started_at,
        "reference_ids": task.reference_ids,
    }


@router.get("/agent/{task_id}", summary="查询 AI 任务的完整日志和结果")
def agent_status(task_id: str):
    from ai_analysis.agent_loop import AgentTask
    t = AgentTask.load(task_id)
    if t is None:
        raise HTTPException(404, "任务不存在")
    return {
        "task_id": t.task_id,
        "goal": t.goal,
        "status": t.status,
        "provider": t.provider,
        "max_iterations": t.max_iterations,
        "started_at": t.started_at,
        "finished_at": t.finished_at,
        "reference_ids": t.reference_ids,
        "steps": [
            {
                "idx": s.idx, "at": s.at, "action": s.action,
                "args": s.args, "reason": s.reason,
                "result": s.result, "error": s.error,
                "duration_ms": s.duration_ms,
                "phase": s.phase, "raw_llm": s.raw_llm,
            }
            for s in t.steps
        ],
        "final": t.final,
        "error": t.error,
    }


@router.get("/agent", summary="列出最近的 AI 任务")
def agent_list(limit: int = 20):
    from ai_analysis.agent_loop import list_tasks
    return {"tasks": list_tasks(limit=limit)}


@router.post("/agent/{task_id}/cancel", summary="请求取消正在跑的 AI 任务")
def agent_cancel(task_id: str):
    from ai_analysis.agent_loop import cancel_task
    t = cancel_task(task_id)
    if t is None:
        raise HTTPException(404, "任务不存在")
    return {"task_id": t.task_id, "status": t.status}


@router.get("/agent/{task_id}/markdown", summary="读 AI 任务的 Markdown 复盘报告")
def agent_markdown(task_id: str):
    from ai_analysis.agent_loop import AgentTask
    t = AgentTask.load(task_id)
    if t is None:
        raise HTTPException(404, "任务不存在")
    p = t.markdown_path()
    if not p.exists():
        # 兜底：如果文件不在（老任务），实时生成一次
        return {"markdown": t.render_markdown(), "path": None}
    return {"markdown": p.read_text(encoding="utf-8"), "path": str(p)}


@router.get("/agent/{task_id}/download", summary="下载 AI 任务的 Markdown 报告")
def agent_markdown_download(task_id: str):
    from fastapi.responses import Response
    from ai_analysis.agent_loop import AgentTask
    t = AgentTask.load(task_id)
    if t is None:
        raise HTTPException(404, "任务不存在")
    p = t.markdown_path()
    if p.exists():
        content = p.read_text(encoding="utf-8")
    else:
        content = t.render_markdown()
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="agent_{task_id}.md"'},
    )


# ================ 实时模拟盘（M9 live_paper） =================


class LiveStartRequest(BaseModel):
    account: str = "live_default"
    watch_symbols: list[str] = Field(default_factory=list, description="要跑策略的股票池")
    strategy_id: Optional[str] = None
    strategy_params: Optional[dict] = None
    tick_seconds: int = 15
    broker_kind: str = Field("paper", description="paper=本地模拟 / qmt=国金QMT等实盘")
    broker_config: Optional[dict] = Field(None, description="qmt 模式需 {account_id, user_data_path}")


@router.post("/live/start", summary="启动实时引擎 runner（支持 paper / qmt）")
def live_start(req: LiveStartRequest):
    from execution.runner import start_runner
    if req.broker_kind not in ("paper", "qmt"):
        raise HTTPException(400, f"broker_kind 必须是 paper 或 qmt，收到 {req.broker_kind}")
    r = start_runner(
        account=req.account,
        watch_symbols=req.watch_symbols,
        strategy_id=req.strategy_id,
        strategy_params=req.strategy_params or {},
        tick_seconds=req.tick_seconds,
        broker_kind=req.broker_kind,
        broker_config=req.broker_config or {},
    )
    result = {"account": r.account, "status": r.state.status,
              "started_at": r.state.started_at, "broker_kind": r.broker_kind}
    # qmt 模式：立即上报连接状态
    if r.broker_kind == "qmt" and hasattr(r.broker, "is_available"):
        ok, msg = r.broker.is_available()
        result["qmt_ready"] = ok
        result["qmt_message"] = msg
    return result


@router.get("/live/qmt/status", summary="检查 QMT 环境（是否装了 xtquant / 配了账号）")
def live_qmt_status():
    """给前端一个"实盘按钮能不能亮"的判断依据。"""
    from execution.qmt_broker import _try_import_xtquant, _load_config
    sdk = _try_import_xtquant()
    cfg = _load_config(None)
    return {
        "sdk_installed": "error" not in sdk,
        "sdk_error": sdk.get("error"),
        "account_id_configured": bool(cfg.get("account_id")),
        "user_data_path_configured": bool(cfg.get("user_data_path")),
        "config_source_hint": "环境变量 QMT_ACCOUNT_ID / QMT_USER_DATA_PATH 或 configs/qmt.yaml",
    }


class LiveUpdateRequest(BaseModel):
    strategy_id: Optional[str] = Field(None, description="新策略 id；空串 = 清空策略只走手动下单")
    strategy_params: Optional[dict] = None
    watch_symbols: Optional[list[str]] = None
    tick_seconds: Optional[int] = None


@router.post("/live/{account}/update", summary="热更新引擎的策略/池子/tick，不需要停引擎")
def live_update(account: str, req: LiveUpdateRequest):
    from execution.runner import update_runner
    r = update_runner(
        account=account,
        strategy_id=req.strategy_id,
        strategy_params=req.strategy_params,
        watch_symbols=req.watch_symbols,
        tick_seconds=req.tick_seconds,
    )
    if r is None:
        raise HTTPException(404, f"引擎 {account} 未在运行，请先启动")
    return {"account": account, "strategy_id": r.strategy_id,
            "watch_symbols": r.watch_symbols, "tick_seconds": r.tick_seconds}


@router.post("/live/{account}/stop", summary="停止实时模拟盘 runner")
def live_stop(account: str):
    from execution.runner import stop_runner
    ok = stop_runner(account)
    if not ok:
        raise HTTPException(404, "runner 不存在或已停止")
    return {"account": account, "status": "stopped"}


@router.get("/live", summary="列出所有实时模拟盘 runner")
def live_list():
    from execution.runner import list_runners
    return {"runners": list_runners()}


@router.get("/live/{account}", summary="查询单个 runner 的状态 + 账户 + 挂单")
def live_status(account: str):
    from execution.runner import RunnerState, get_runner
    from paper_trade import portfolio as pfolio
    from execution.broker import PaperBroker
    state = RunnerState.load(account)
    port_path = pfolio.default_path(account)
    port = None
    orders = []
    if port_path.exists():
        port = pfolio.Portfolio.load(port_path)
        broker = PaperBroker(port, account=account)
        orders = [
            {
                "order_id": o.order_id, "symbol": o.symbol,
                "side": o.side.value if hasattr(o.side, "value") else o.side,
                "shares": o.shares, "filled_shares": o.filled_shares,
                "limit_price": o.limit_price,
                "filled_avg_price": o.filled_avg_price,
                "status": o.status.value if hasattr(o.status, "value") else o.status,
                "reason": o.reason,
                "submitted_at": o.submitted_at, "finished_at": o.finished_at,
                "reject_reason": o.reject_reason,
            }
            for o in broker.query_orders()
        ]
    return {
        "state": asdict(state) if state else None,
        "portfolio": port.to_dict() if port else None,
        "orders": orders,
    }


class LiveOrderRequest(BaseModel):
    account: str
    symbol: str
    side: str = Field(..., description="buy | sell")
    shares: int
    limit_price: float
    reason: str = "手动下单"


@router.post("/live/order", summary="实时模拟盘：手动下一笔委托")
def live_submit_order(req: LiveOrderRequest):
    from execution.broker import PaperBroker, OrderSide
    from paper_trade import portfolio as pfolio
    port = pfolio.load_or_create(req.account)
    broker = PaperBroker(port, account=req.account)
    side = OrderSide(req.side)
    order = broker.submit_order(
        symbol=req.symbol, side=side, shares=req.shares,
        limit_price=req.limit_price, reason=req.reason,
    )
    port.save(pfolio.default_path(req.account))
    return {"order_id": order.order_id, "status": order.status.value}


@router.post("/live/order/{order_id}/cancel", summary="实时模拟盘：撤单")
def live_cancel_order(order_id: str, account: str):
    from execution.broker import PaperBroker
    from paper_trade import portfolio as pfolio
    port = pfolio.load_or_create(account)
    broker = PaperBroker(port, account=account)
    ok = broker.cancel_order(order_id)
    if not ok:
        raise HTTPException(404, "订单不存在或已终态")
    return {"order_id": order_id, "status": "cancelled"}
