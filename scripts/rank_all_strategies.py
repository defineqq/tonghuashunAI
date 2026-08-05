"""
按实盘约束批量回测所有策略 —— 找出真赚钱的
============================================

约束：
- 打分/技术策略均用信号 T+1 成交（消除未来函数）
- 涨停日不买、跌停日不卖（引擎硬约束已生效）
- 沪深 300，2024 全年，limit=30，初始 10 万

用法：
    python scripts/rank_all_strategies.py [--limit 30] [--pool 000300]
"""

from __future__ import annotations

import argparse
import sys
import time
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests


API = "http://127.0.0.1:8000/api"


def list_strategies() -> list[dict]:
    r = requests.get(f"{API}/strategies", timeout=10).json()
    return [s for s in r["strategies"] if s["kind"] in ("preset", "builder")]


def start_backtest(strat: dict, pool: str, limit: int, start: str, end: str) -> str | None:
    body = {
        "start": start, "end": end,
        "pool": pool, "limit": limit,
        "strategy_type": "technical",
        "strategy_id": strat["id"],
        "initial_cash": 100_000,
    }
    try:
        r = requests.post(f"{API}/backtest/run", json=body, timeout=15).json()
        return r.get("task_id")
    except Exception as e:
        print(f"    ! 启动失败 {strat['id']}: {e}")
        return None


def wait_backtest(task_id: str, timeout: int = 300) -> dict | None:
    """轮询到完成，返回 result 或 None（超时/失败）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{API}/backtest/tasks/{task_id}", timeout=10).json()
        except Exception:
            time.sleep(3)
            continue
        st = r.get("status")
        if st == "done":
            return r.get("result")
        if st in ("failed", "cancelled"):
            return None
        time.sleep(3)
    return None


def run_one(strat: dict, args) -> dict:
    t0 = time.time()
    tid = start_backtest(strat, args.pool, args.limit, args.start, args.end)
    if not tid:
        return {"id": strat["id"], "name": strat["name"], "status": "启动失败"}
    result = wait_backtest(tid, timeout=args.timeout)
    dur = time.time() - t0
    if not result:
        return {"id": strat["id"], "name": strat["name"], "status": "超时/失败",
                "dur": round(dur, 1)}
    m = result.get("metrics", {})
    return {
        "id": strat["id"],
        "name": strat["name"],
        "kind": strat["kind"],
        "status": "done",
        "cumulative_return": m.get("cumulative_return", 0),
        "annualized_return": m.get("annualized_return", 0),
        "max_drawdown": m.get("max_drawdown", 0),
        "sharpe": m.get("sharpe", 0),
        "trades_count": result.get("trades_count", 0),
        "dur": round(dur, 1),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default="000300", help="000300 / 000905 / 000852")
    parser.add_argument("--limit", type=int, default=30, help="池子大小")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--workers", type=int, default=1,
                        help="并发跑几个（默认串行 1；服务器 CPU 强可以调 2-4）")
    parser.add_argument("--out", default="logs/rank_all.json")
    args = parser.parse_args()

    strats = list_strategies()
    print(f"待跑策略 {len(strats)} 个 · 池 {args.pool} · limit {args.limit} · "
          f"{args.start} ~ {args.end} · 并发 {args.workers}")
    print()

    results = []
    if args.workers == 1:
        for i, s in enumerate(strats, 1):
            print(f"[{i}/{len(strats)}] {s['id']} ...")
            r = run_one(s, args)
            results.append(r)
            _print_row(r)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(run_one, s, args): s for s in strats}
            for i, fut in enumerate(futs, 1):
                r = fut.result()
                results.append(r)
                print(f"[{i}/{len(strats)}] ", end="")
                _print_row(r)

    # 排序：先按累计收益降序，失败的放末尾
    done = [r for r in results if r.get("status") == "done"]
    failed = [r for r in results if r.get("status") != "done"]
    done.sort(key=lambda x: x.get("cumulative_return") or -999, reverse=True)

    print()
    print("=" * 90)
    print(f"排名（按累计收益降序） · 共 {len(done)} 只成功")
    print("=" * 90)
    print(f"{'排名':<4}{'ID':<38}{'累计':<10}{'年化':<10}{'回撤':<10}{'夏普':<8}{'笔数':<6}")
    print("-" * 90)
    for i, r in enumerate(done, 1):
        cum = r["cumulative_return"] * 100
        ann = r["annualized_return"] * 100
        mdd = r["max_drawdown"] * 100
        shr = r["sharpe"]
        marker = "🏆" if i <= 3 else "  "
        print(f"{marker}{i:<2} {r['id']:<38}{cum:>+7.2f}%  {ann:>+7.2f}%  "
              f"{mdd:>7.2f}%  {shr:>6.2f}  {r['trades_count']:<6}")

    if failed:
        print()
        print(f"失败/超时 {len(failed)} 只：")
        for r in failed:
            print(f"  · {r['id']:<38} {r.get('status')}")

    # 落地
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({
        "args": vars(args), "results": results, "done_ranked": done,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"完整结果保存到 {args.out}")


def _print_row(r):
    if r.get("status") == "done":
        cum = r["cumulative_return"] * 100
        print(f"  ✓ {r['id']} · 累计 {cum:+.2f}% · 夏普 {r['sharpe']:.2f} · "
              f"笔数 {r['trades_count']} · {r['dur']}s")
    else:
        print(f"  ✗ {r['id']} · {r.get('status')} · {r.get('dur', '?')}s")


if __name__ == "__main__":
    sys.exit(main() or 0)
