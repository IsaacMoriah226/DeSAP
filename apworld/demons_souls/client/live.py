"""Commands to a running KytyPS5 through its live-control file (src/local/live-control.h in the chenxiao07 fork).

The emulator polls the file named by its KYTY_LIVE_FILE environment variable every 100 ms and runs the lines
under a new "id N" first line once (N must grow). The client only needs `gamecmd <console command>`, which runs a
dev console command on the game's pad thread. The emulator runs one queued console command at a time, so
commands are spaced (MIN_SPACING).
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

MIN_SPACING = 0.25  # seconds between two commands (the emulator's single console slot)


class LiveControl:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.last_id = 0
        self.last_sent = 0.0
        self.lock = threading.Lock()

    def send(self, *lines: str) -> None:
        with self.lock:
            wait = self.last_sent + MIN_SPACING - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            command_id = max(time.time_ns() // 1_000_000, self.last_id + 1)
            self.last_id = command_id
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(f"id {command_id}\n" + "\n".join(lines) + "\n", encoding="ascii")
            os.replace(tmp, self.path)  # the emulator never reads half a file
            self.last_sent = time.monotonic()

    def gamecmd(self, command: str) -> None:
        self.send(f"gamecmd {command}")
