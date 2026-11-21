"""List the player spawn points (MSB player parts named c0000_*) of every remake map: the destinations the
emulator's live `warp MAP SPAWN` accepts. Same reading as KytyPS5's src/loader/demonsSoulsWarp.cpp ReadMsb.

Usage: python -I list_spawns.py [<game folder>]   (default: the dump on the Desktop)
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from desap import local  # noqa: E402

DEFAULT_GAME = local.path("game")


def text(data: bytes, at: int) -> str:
    end = data.find(b"\0", at)
    return data[at:end].decode("ascii", "replace") if 0 <= at < len(data) else ""


def read_msb(path: Path) -> list[tuple[str, float, float, float, float]]:
    data = path.read_bytes()
    out, at = [], 0
    for _ in range(64):
        if at + 24 > len(data):
            break
        name_at, count = struct.unpack_from("<qi", data, at + 8)
        if count <= 0 or count > 1 << 20:
            break
        offsets = struct.unpack_from(f"<{count}q", data, at + 24)
        if text(data, name_at) == "PARTS_PARAM_ST":
            for entry in offsets[:-1]:
                part_name, part_type = struct.unpack_from("<qi", data, entry)
                if part_type == 4:
                    x, y, z = struct.unpack_from("<3f", data, entry + 0x20)
                    yaw = struct.unpack_from("<f", data, entry + 0x30)[0]
                    name = text(data, entry + part_name)
                    if name.startswith("c0000_"):
                        out.append((name, x, y, z, yaw))
        if offsets[-1] <= 0:
            break
        at = offsets[-1]
    return out


def main() -> None:
    game = Path(sys.argv[1]) if len(sys.argv) > 1 else local.require("game")
    folder = game / "cp11demonssouls" / "dvdroot" / "map" / "mapstudio"
    for msb in sorted(folder.glob("m0*.msb")):
        if len(msb.name) != 16:
            continue
        for name, x, y, z, yaw in read_msb(msb):
            print(f"{msb.stem} {name}  x={x:.1f} y={y:.1f} z={z:.1f} yaw={yaw:.2f}")


if __name__ == "__main__":
    main()
