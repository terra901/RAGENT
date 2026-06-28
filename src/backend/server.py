"""生产/单进程启动脚本：使用 settings.host / settings.port，自动开浏览器。"""
from __future__ import annotations

import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

from data_agent.core.config import settings  # noqa: E402


def _open_browser() -> None:
    """延迟打开本地 UI，避免浏览器早于 Uvicorn 监听端口。"""
    time.sleep(2)
    host = "127.0.0.1" if settings.host in ("0.0.0.0", "127.0.0.1") else settings.host
    webbrowser.open(f"http://{host}:{settings.port}/")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(
        "data_agent.api.main:app",
        host=settings.host,
        port=settings.port,
    )
