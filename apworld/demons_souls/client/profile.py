"""The Archipelago play profile: a mirror of the KytyPS5 folder with saves of its own, and how the launcher starts
the game in it. No Archipelago imports.

KytyPS5 keeps saves in `_SaveData` under the emulator's working folder, and run-windows.ps1 always runs the
emulator in its own folder. So the profile is a folder that looks like the emulator's: every file of the emulator
folder hard-linked (copied when the profile is on another drive), every folder a directory junction (the shader
cache, `_PipelineCache`, is shared), except the per-run folders (saves, logs, temporary data), which are the
profile's own. Running the profile's run-windows.ps1 then runs the same emulator with the same settings, with
Archipelago saves apart from the vanilla ones.

The command is KytyLauncher's own (`KytyLauncher.exe --dry-run`: the play command its saved settings make), with
the emulator folder replaced by the profile and live control added (`-Set KYTY_LIVE_FILE=live.txt`, relative to
the emulator's working folder, the profile).
"""

from __future__ import annotations

import _winapi
import datetime
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

TITLE_ID = "PPSA01341"
LIVE_FILE_NAME = "live.txt"  # in the profile (the emulator's working folder): no spaces, no commas in -Set
OWN_FOLDERS = {"_savedata", "logs", "_tempdata", "_devlog", "_downloaddata", "_textures", "_build"}
SKIP_FILES = {LIVE_FILE_NAME, "live.tmp"}
BACKUPS_KEPT = 40


def data_dir() -> Path:
    """%LOCALAPPDATA%\\DemonsSoulsAP: settings, the profile, backups."""
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "DemonsSoulsAP"


class ProfileError(RuntimeError):
    pass


@dataclass
class Emulator:
    launcher: Path  # KytyLauncher.exe

    @property
    def folder(self) -> Path:
        return self.launcher.parent

    def check(self) -> list[str]:
        """What is missing for the launcher to use this emulator (empty: ready)."""
        problems = []
        if not self.launcher.is_file():
            problems.append(f"{self.launcher} does not exist")
        for name in ("kyty_emulator.exe", "run-windows.ps1"):
            if not (self.folder / name).is_file():
                problems.append(f"{name} is not next to KytyLauncher.exe")
        return problems

    def settings(self) -> dict:
        import json
        path = self.folder / "launcher-settings.json"
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {}


def _same_file(a: Path, b: Path) -> bool:
    try:
        sa, sb = a.stat(), b.stat()
    except OSError:
        return False
    return (sa.st_ino, sa.st_dev) == (sb.st_ino, sb.st_dev) or (
        sa.st_size == sb.st_size and int(sa.st_mtime) == int(sb.st_mtime) and sa.st_dev != sb.st_dev)


def _is_junction(path: Path) -> bool:
    try:
        return path.is_junction()
    except AttributeError:  # Python < 3.12
        return os.path.isdir(path) and os.stat(path, follow_symlinks=False).st_file_attributes & 0x400 != 0


class Profile:
    def __init__(self, root: Path | None = None):
        self.root = root or data_dir() / "profile"

    @property
    def save_dir(self) -> Path:
        return self.root / "_SaveData"

    @property
    def live_file(self) -> Path:
        return self.root / LIVE_FILE_NAME

    @property
    def backup_dir(self) -> Path:
        return self.root.parent / "backups"

    def sync(self, emulator: Emulator) -> None:
        """Make the profile mirror the emulator folder (cheap when nothing changed)."""
        problems = emulator.check()
        if problems:
            raise ProfileError("; ".join(problems))
        self.root.mkdir(parents=True, exist_ok=True)
        source = emulator.folder
        wanted = set()
        for entry in source.iterdir():
            name = entry.name
            if name.lower() in OWN_FOLDERS or name in SKIP_FILES or name.lower().startswith("_savedata"):
                continue
            wanted.add(name)
            target = self.root / name
            if entry.is_dir():
                if _is_junction(target):
                    if os.path.normcase(os.path.realpath(target)) == os.path.normcase(os.path.realpath(entry)):
                        continue
                    os.rmdir(target)  # a junction to an older emulator folder
                elif target.exists():
                    raise ProfileError(f"{target} is a real folder where a link to {entry} belongs")
                _winapi.CreateJunction(str(entry), str(target))
            else:
                if _same_file(entry, target):
                    continue
                if target.exists() or target.is_symlink():
                    target.unlink()
                try:
                    os.link(entry, target)
                except OSError:  # another drive: a copy (re-copied when the emulator's file changes)
                    shutil.copy2(entry, target)
        for target in self.root.iterdir():  # links to what the emulator no longer has
            if target.name not in wanted and target.name.lower() not in OWN_FOLDERS and target.name not in SKIP_FILES:
                if _is_junction(target):
                    os.rmdir(target)
                elif target.is_file() and target.name.lower() != "launch-archipelago.txt":
                    target.unlink()
        self.save_dir.mkdir(exist_ok=True)

    # --- saves -----------------------------------------------------------------------------------------------

    def save_files(self) -> list[Path]:
        folder = self.save_dir / TITLE_ID
        return sorted(p for p in folder.rglob("*") if p.is_file()) if folder.is_dir() else []

    def backup(self, reason: str = "") -> Path | None:
        """Copy the profile's saves to backups/<time>[ reason]; nothing when there are none or nothing changed since
        the last backup. Keeps the newest BACKUPS_KEPT."""
        files = self.save_files()
        if not files:
            return None
        signature = "".join(f"{p.relative_to(self.save_dir)}:{p.stat().st_size}:{int(p.stat().st_mtime)};"
                            for p in files)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        marker = self.backup_dir / "last.txt"
        if marker.exists() and marker.read_text(encoding="utf-8") == signature:
            return None
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.backup_dir / (stamp + (f" {reason}" if reason else ""))
        shutil.copytree(self.save_dir / TITLE_ID, target / TITLE_ID)
        marker.write_text(signature, encoding="utf-8")
        for old in self.backups()[BACKUPS_KEPT:]:
            shutil.rmtree(old, ignore_errors=True)
        return target

    def backups(self) -> list[Path]:
        if not self.backup_dir.is_dir():
            return []
        return sorted((p for p in self.backup_dir.iterdir() if p.is_dir()), reverse=True)

    def restore(self, backup: Path) -> None:
        """Put a backup's saves back (the current ones are backed up first). Only while the game is not running."""
        self.backup("before restore")
        target = self.save_dir / TITLE_ID
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(backup / TITLE_ID, target)

    # --- starting the game -----------------------------------------------------------------------------------

    def play_command(self, emulator: Emulator) -> str:
        """The `cmd` arguments that start the game in the profile, from KytyLauncher's own play command."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dry-run.txt"
            subprocess.run([str(emulator.launcher), "--dry-run", str(out)], cwd=emulator.folder, timeout=60,
                           check=False, creationflags=subprocess.CREATE_NO_WINDOW)
            if not out.exists():
                raise ProfileError("KytyLauncher.exe --dry-run wrote no command (an older KytyLauncher?)")
            lines = out.read_text(encoding="utf-8-sig").splitlines()
        play = next((line for line in lines if line.startswith("play:")), None)
        if play is None or " cmd " not in play:
            raise ProfileError("KytyLauncher.exe --dry-run gave no play command")
        arguments = play.split(" cmd ", 1)[1].strip()
        # the emulator folder -> the profile (paths as KytyLauncher wrote them, any case)
        arguments = re.sub(re.escape(str(emulator.folder)), str(self.root).replace("\\", "\\\\"), arguments,
                           flags=re.IGNORECASE)
        if str(self.root) not in arguments:
            raise ProfileError("the play command does not name the emulator folder")
        live = f"KYTY_LIVE_FILE={LIVE_FILE_NAME}"
        match = re.search(r"(-Set\s+)(\"?)([^\s\"]+)", arguments)
        if match:  # one -Set with comma-separated pairs: add ours (replacing any live file the settings name)
            pairs = [p for p in match.group(3).split(",") if not p.upper().startswith("KYTY_LIVE_FILE=")]
            pairs.append(live)
            arguments = arguments[:match.start(3)] + ",".join(pairs) + arguments[match.end(3):]
        else:  # before the closing quote of /c "..."
            if not arguments.endswith('"'):
                raise ProfileError("unexpected play command shape")
            arguments = arguments[:-1] + f" -Set {live}\""
        return arguments

    def start(self, emulator: Emulator) -> subprocess.Popen:
        arguments = self.play_command(emulator)
        (self.root / "launch-archipelago.txt").write_text("cmd " + arguments + "\n", encoding="utf-8")
        cmd = os.environ.get("ComSpec") or str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe")
        return subprocess.Popen(f'"{cmd}" {arguments}', cwd=self.root, creationflags=subprocess.CREATE_NEW_CONSOLE)
