"""
run_web.py — 启动 Web 控制台
============================

用法：
    python examples/run_web.py

    # 或直接：
    uvicorn web.server:app --reload --host 127.0.0.1 --port 8000
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from web.server import main

if __name__ == "__main__":
    main()
