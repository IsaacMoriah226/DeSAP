"""The launcher's saved settings (%LOCALAPPDATA%\\DemonsSoulsAP\\settings.json). No Archipelago imports."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields

from .profile import data_dir


@dataclass
class OverlaySettings:
    enabled: bool = True
    x: int = 40  # top-left corner on the screen, in pixels
    y: int = 120
    width: int = 520
    lines: int = 6  # messages shown at once
    font_size: int = 22
    background: str = "#101012"  # background colour
    background_alpha: int = 150  # 0 (clear) to 255 (solid)
    text_alpha: int = 255
    seconds: int = 12  # how long a message stays (0: until pushed out)


@dataclass
class LauncherSettings:
    kyty_launcher: str = ""  # path of KytyLauncher.exe
    server: str = "archipelago.gg:38281"
    slot: str = ""
    password: str = ""
    remember_password: bool = False
    backup_minutes: int = 10
    overlay: OverlaySettings = field(default_factory=OverlaySettings)

    @classmethod
    def load(cls) -> "LauncherSettings":
        path = data_dir() / "settings.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in raw.items() if k in known and k != "overlay"}
        overlay_known = {f.name for f in fields(OverlaySettings)}
        overlay = OverlaySettings(**{k: v for k, v in (raw.get("overlay") or {}).items() if k in overlay_known})
        return cls(**values, overlay=overlay)

    def save(self) -> None:
        path = data_dir() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        if not self.remember_password:
            data["password"] = ""
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")
