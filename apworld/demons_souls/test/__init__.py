import json
import os
from pathlib import Path

from test.bases import WorldTestBase


def local_path(key: str) -> Path | None:
    """A path on this PC (DeSAP's desap/local.py, without importing it): DESAP_<KEY>, else DeSAP's local_paths.json,
    else the workspace default for "work". None when unknown (tests that need it skip)."""
    value = os.environ.get(f"DESAP_{key.upper()}")
    repo = Path(__file__).resolve().parents[3]
    if not value:
        try:
            value = json.loads((repo / "local_paths.json").read_text(encoding="utf-8")).get(key)
        except (OSError, ValueError):
            value = None
    if not value and key == "work":
        return repo.parent / "work"
    return Path(value) if value else None


class DemonsSoulsTestBase(WorldTestBase):
    game = "Demon's Souls Remake"
