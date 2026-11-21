"""Build the playtest kit: dist/DeSAP-<version>/ with the .apworld, an options template and the player guide,
zipped as dist/DeSAP-<version>.zip.

    python tools/build_apworld.py          (from DeSAP; the Archipelago checkout must have the world junctioned in)

The .apworld is a zip whose top folder is the world's package (demons_souls/), as Archipelago expects; caches and
the tests stay out. The template comes from Archipelago's own generator (Options.generate_yaml_templates).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORLD = ROOT / "apworld" / "demons_souls"
ARCHIPELAGO = Path(r"C:\Dev\DeSArchi\repos\Archipelago")
PYTHON = Path(r"C:\Dev\DeSArchi\venv\Scripts\python.exe")
GAME = "Demon's Souls Remake"
LEAVE_OUT = {"__pycache__", "test"}


def version() -> str:
    return json.loads((WORLD / "archipelago.json").read_text(encoding="utf-8"))["world_version"]


# What Archipelago's own packer (APWorldContainer) adds to a packed world's manifest; without them Archipelago reads
# no manifest at all (world version 0.0.0, so a template asking for this world's version is refused).
CONTAINER = {"version": 7, "compatible_version": 7}


def build_apworld(target: Path) -> None:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(WORLD.rglob("*")):
            relative = path.relative_to(WORLD)
            if path.is_dir() or LEAVE_OUT & set(relative.parts) or path.suffix == ".pyc":
                continue
            if relative == Path("archipelago.json"):
                manifest = json.loads(path.read_text(encoding="utf-8")) | CONTAINER
                archive.writestr("demons_souls/archipelago.json", json.dumps(manifest, indent=1))
                continue
            archive.write(path, Path("demons_souls") / relative)


def build_template(target: Path) -> None:
    script = (
        "import sys, Options\n"
        "Options.generate_yaml_templates(sys.argv[1], False)\n"
    )
    with tempfile.TemporaryDirectory() as folder:
        subprocess.run([str(PYTHON), "-c", script, folder], cwd=ARCHIPELAGO, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        text = (Path(folder) / f"{GAME}.yaml").read_text(encoding="utf-8")
    # the template asks for the generator it was made with; the world's own minimum is what it needs
    minimum = json.loads((WORLD / "archipelago.json").read_text(encoding="utf-8"))["minimum_ap_version"]
    text = re.sub(r"(?m)^(\s+version:\s*)\d+\.\d+\.\d+", lambda m: m.group(1) + minimum, text, count=1)
    target.write_text(text, encoding="utf-8")


def main() -> None:
    v = version()
    kit = ROOT / "dist" / f"DeSAP-{v}"
    if kit.exists():
        shutil.rmtree(kit)
    kit.mkdir(parents=True)
    build_apworld(kit / "demons_souls.apworld")
    build_template(kit / f"{GAME}.yaml")
    for name in ("PLAYER_GUIDE.md", "PLAYTEST.md"):
        shutil.copy(ROOT / "docs" / name, kit / name)
    shutil.copy(WORLD / "data" / "fonts" / "Jost-OFL.txt", kit / "Jost-OFL.txt")
    archive = shutil.make_archive(str(kit), "zip", kit.parent, kit.name)
    for path in sorted(kit.iterdir()):
        print(f"{path.name:32} {path.stat().st_size // 1024:6} KB")
    print(archive)


if __name__ == "__main__":
    main()
