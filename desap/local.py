"""Where things are on this PC, for DeSAP's tools and tests (the .apworld never uses this).

Each path comes from an environment variable, else from local_paths.json at the repo root (git-ignored; copy
local_paths.example.json), else a default in the workspace: the folder that holds this repo, laid out as
docs/SETUP.md describes (work/, repos/, venv/, tools/, ...).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT.parent
LOCAL_FILE = ROOT / "local_paths.json"

DEFAULTS: dict[str, Path | None] = {
    "game": None,  # the Demon's Souls dump (the PPSA01341-app0 folder): no default, it is wherever you keep it
    "work": WORKSPACE / "work",  # scratch output (converted eboot, logs, live file, research)
    "archipelago": WORKSPACE / "repos" / "Archipelago",  # an Archipelago source checkout
    "paramdex": WORKSPACE / "repos" / "Paramdex",
    "python": WORKSPACE / "venv" / "Scripts" / "python.exe",  # the venv with Archipelago's requirements
    "emulator": WORKSPACE / "KytyPS5",  # a KytyPS5 build (for tools/live.py's live file)
}
ENVIRONMENT = {key: f"DESAP_{key.upper()}" for key in DEFAULTS}


def _file() -> dict:
    try:
        return json.loads(LOCAL_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def path(key: str) -> Path | None:
    value = os.environ.get(ENVIRONMENT[key]) or _file().get(key)
    return Path(value) if value else DEFAULTS[key]


def require(key: str) -> Path:
    found = path(key)
    if found is None:
        raise SystemExit(f"Where is '{key}'? Set {ENVIRONMENT[key]} or add \"{key}\" to {LOCAL_FILE} "
                         "(see local_paths.example.json).")
    return found
