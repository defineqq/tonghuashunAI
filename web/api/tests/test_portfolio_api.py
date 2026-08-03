"""
账户 CRUD API 集成测试
======================

覆盖 M9.5 新增：
- GET /api/portfolio 列表带余额/持仓概览
- DELETE /api/portfolio/{name} 删除账户（含引擎清理）
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from web import server as web_server
from paper_trade import portfolio as pfolio


@pytest.fixture
def client(tmp_path, monkeypatch):
    # 把账户目录、引擎 state、委托目录都指向 tmp
    monkeypatch.setattr(pfolio, "_PROJECT_ROOT", tmp_path)
    (tmp_path / "logs" / "portfolio").mkdir(parents=True, exist_ok=True)

    from web.api import routes
    monkeypatch.setattr(routes, "LOGS_DIR", tmp_path / "logs")

    from execution import runner
    monkeypatch.setattr(runner, "STATE_DIR", tmp_path / "live_runner")
    (tmp_path / "live_runner").mkdir(exist_ok=True)

    from execution import broker
    monkeypatch.setattr(broker, "ORDERS_DIR", tmp_path / "live_orders")
    (tmp_path / "live_orders").mkdir(exist_ok=True)

    return TestClient(web_server.app)


def test_list_portfolios_empty(client):
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    assert r.json()["accounts"] == []


def test_new_then_list_shows_summary(client):
    r = client.post("/api/portfolio/new", json={"account_id": "acct1", "initial_cash": 50000})
    assert r.status_code == 200
    r = client.get("/api/portfolio")
    items = r.json()["accounts"]
    assert len(items) == 1
    a = items[0]
    assert a["account_id"] == "acct1"
    assert a["initial_cash"] == 50000
    assert a["cash"] == 50000
    assert a["total_value"] == 50000
    assert a["n_positions"] == 0
    assert a["engine"]["status"] == "never_started"


def test_list_shows_multiple_accounts_sorted(client):
    for name, cash in [("a1", 10000), ("a2", 20000), ("a3", 30000)]:
        client.post("/api/portfolio/new", json={"account_id": name, "initial_cash": cash})
    r = client.get("/api/portfolio")
    ids = [a["account_id"] for a in r.json()["accounts"]]
    assert set(ids) == {"a1", "a2", "a3"}


def test_delete_account_removes_it(client):
    client.post("/api/portfolio/new", json={"account_id": "gone", "initial_cash": 10000})
    r = client.delete("/api/portfolio/gone")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    r = client.get("/api/portfolio")
    assert r.json()["accounts"] == []


def test_delete_nonexistent_returns_404(client):
    r = client.delete("/api/portfolio/never_existed")
    assert r.status_code == 404


def test_delete_account_also_removes_engine_state(client, tmp_path):
    client.post("/api/portfolio/new", json={"account_id": "with_engine", "initial_cash": 10000})
    # 手动造一个 state 文件模拟引擎跑过
    state_file = tmp_path / "live_runner" / "with_engine.json"
    state_file.write_text(json.dumps({
        "account": "with_engine", "status": "stopped",
        "started_at": "2026-08-01T09:31:00",
        "tick_seconds": 15, "ticks_count": 100,
    }))
    client.delete("/api/portfolio/with_engine")
    assert not state_file.exists()
