"""Send commands to a running KytyPS5 through its live-control file and print the replies.

The emulator has to be started with the live file set, e.g. in KytyLauncher's extra options (Advanced page):
    -Set KYTY_LIVE_FILE=C:\\Dev\\DeSArchi\\work\\live.txt
It polls that file every 100 ms and runs the lines under a new "id N" first line once; it prints LIVE_* replies
to its stdout, which run-windows.ps1 saves as logs\\<stamp>.out.log next to the emulator.

Usage:
    python -I live.py "where"
    python -I live.py "gamecmd +cp11_unlockAllArchstones"
    python -I live.py "warp m02_00_00_00 c0000_0001" "where"

Options (environment): DESAP_LIVE_FILE (default C:\\Dev\\DeSArchi\\work\\live.txt),
DESAP_EMU_DIR (default C:\\Dev\\DeSArchi\\KytyPS5-v20261120).
"""

import os
import sys
import time
from pathlib import Path

LIVE_FILE = Path(os.environ.get("DESAP_LIVE_FILE", r"C:\Dev\DeSArchi\work\live.txt"))
EMU_DIR = Path(os.environ.get("DESAP_EMU_DIR", r"C:\Dev\DeSArchi\KytyPS5-v20261120"))


def latest_log() -> Path:
    logs = sorted((EMU_DIR / "logs").glob("*.out.log"), key=lambda p: p.stat().st_mtime)
    if not logs:
        raise SystemExit(f"no *.out.log under {EMU_DIR / 'logs'}: is the emulator running from there?")
    return logs[-1]


def send(commands: list[str], timeout: float = 10.0) -> list[str]:
    command_id = time.time_ns() // 1_000_000  # newer than any earlier id
    log = latest_log()
    start = log.stat().st_size
    LIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = LIVE_FILE.with_suffix(".tmp")
    tmp.write_text(f"id {command_id}\n" + "\n".join(commands) + "\n", encoding="ascii")
    os.replace(tmp, LIVE_FILE)  # the emulator never reads half a file
    tag = f"id={command_id}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.1)
        with open(log, "rb") as f:
            f.seek(start)
            lines = f.read().decode("utf-8", "replace").splitlines()
        if any(line.startswith("LIVE_DONE") and tag in line for line in lines):
            return [line for line in lines if line.startswith("LIVE_") or line.startswith("Game ")]
    raise SystemExit(f"no LIVE_DONE {tag} in {log} after {timeout} s (KYTY_LIVE_FILE set to {LIVE_FILE}?)")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for line in send(sys.argv[1:]):
        print(line)


if __name__ == "__main__":
    main()
