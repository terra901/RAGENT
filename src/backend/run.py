"""开发服务器启动脚本（带 reload）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT.parent / "frontend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

from data_agent.core.config import settings  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(
        "data_agent.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        reload_dirs=[str(ROOT / "data_agent"), str(FRONTEND)],
    )
