"""
回测任务管理器
==============

把 /api/backtest/run 从同步阻塞升级为后台任务：
- 提交后立即返回 task_id
- 前端轮询 /api/backtest/tasks/{task_id} 拿进度/结果
- 页面刷新后仍能通过任务列表恢复
- 未完成的任务可以取消（把 status 置为 cancelled，引擎每天检查一次退出）
"""

from __future__ import annotations

import json
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = PROJECT_ROOT / "logs" / "backtest_tasks"
TASKS_DIR.mkdir(parents=True, exist_ok=True)
_LOCK = Lock()


@dataclass
class BacktestTask:
    task_id: str
    label: str                        # 展示给用户看的：如 "swing_v1 · balanced · 沪深300"
    request: dict[str, Any]           # 原始请求（回放/比较用）
    status: str = "running"           # running | done | failed | cancelled
    started_at: str = ""
    finished_at: str | None = None
    progress: dict[str, Any] = field(default_factory=dict)   # {done, total, day}
    result: dict[str, Any] | None = None   # 最终 metrics + snapshots
    error: str | None = None

    def path(self) -> Path:
        return TASKS_DIR / f"{self.task_id}.json"

    def save(self):
        with _LOCK:
            self.path().write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    @classmethod
    def load(cls, task_id: str) -> Optional["BacktestTask"]:
        p = TASKS_DIR / f"{task_id}.json"
        if not p.exists():
            return None
        return cls(**json.loads(p.read_text(encoding="utf-8")))


def cancel_task(task_id: str) -> Optional[BacktestTask]:
    t = BacktestTask.load(task_id)
    if t is None:
        return None
    if t.status == "running":
        t.status = "cancelled"
        t.finished_at = datetime.now().isoformat(timespec="seconds")
        t.save()
    return t


def _make_progress_cb(task: BacktestTask):
    """给 engine 用的进度回调：写到 task.progress 并存盘。"""
    def cb(done: int, total: int, day: str):
        task.progress = {"done": done, "total": total, "day": day}
        # 每 10 天存一次，减少磁盘 IO
        if done % 10 == 0 or done == total:
            task.save()
        # 检查是否被取消
        fresh = BacktestTask.load(task.task_id)
        if fresh and fresh.status == "cancelled":
            raise BacktestCancelled(task.task_id)
    return cb


class BacktestCancelled(Exception):
    """引擎循环里抛这个来响应取消。"""


def _run_task(task: BacktestTask, run_fn):
    """后台线程主函数：执行 run_fn(progress_cb)，捕获结果。"""
    try:
        result = run_fn(_make_progress_cb(task))
        task.result = result
        task.status = "done"
    except BacktestCancelled:
        task.status = "cancelled"
    except Exception as e:
        task.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}"
        task.status = "failed"
    finally:
        task.finished_at = datetime.now().isoformat(timespec="seconds")
        task.save()


def start_task(label: str, request: dict, run_fn) -> BacktestTask:
    """
    启动一个后台回测任务。

    Args:
        label: UI 上展示的名字
        request: 原始请求 dict（存进 task 便于回放）
        run_fn: callable(progress_cb) → dict —— 真正的回测执行；
                执行时应定期调 progress_cb(done, total, day)

    Returns:
        BacktestTask（status=running）
    """
    task = BacktestTask(
        task_id=uuid.uuid4().hex[:12],
        label=label,
        request=request,
        started_at=datetime.now().isoformat(timespec="seconds"),
    )
    task.save()
    Thread(target=_run_task, args=(task, run_fn), daemon=True).start()
    return task


def list_tasks(limit: int = 30) -> list[dict]:
    files = sorted(TASKS_DIR.glob("*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for f in files[:limit]:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            r = d.get("result") or {}
            metrics = r.get("metrics") or {}
            out.append({
                "task_id": d["task_id"],
                "label": d.get("label"),
                "status": d["status"],
                "started_at": d.get("started_at"),
                "finished_at": d.get("finished_at"),
                "progress": d.get("progress") or {},
                "metrics_summary": {
                    "cumulative_return": metrics.get("cumulative_return"),
                    "annualized_return": metrics.get("annualized_return"),
                    "max_drawdown": metrics.get("max_drawdown"),
                    "sharpe": metrics.get("sharpe"),
                } if metrics else None,
                "error": (d.get("error") or "")[:200] if d.get("error") else None,
            })
        except Exception:
            continue
    return out
