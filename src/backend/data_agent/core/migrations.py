"""Runtime data layout migrations."""
from __future__ import annotations

from .config import Settings


def migrate_db_layout(settings: Settings) -> None:
    """No-op for MySQL/external database deployments."""
    return None
