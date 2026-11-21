"""Build the 3D tracker's map shapes from the game's navmeshes (what enemies and the player walk on): one scene per
world, its parts tagged, into apworld/demons_souls/data/tracker/.

    python tools/build_tracker_maps.py

Sources (cp11demonssouls\\dvdroot\\map, the PS3 data the remake still runs on):
- mapstudio\\<map>.msb: navmesh parts (type 8) name an .nvm of the map's .nvmbnd and place it (position +0x20,
  rotation in degrees +0x2C, scale +0x38; applied scale, X, Z, Y, then translation, as SoulsFormats does).
- <map>\\<map>.nvmbnd: BND3 of NVM files (little-endian): +4 vertex count, +8 triangle count, +0x10 vertex offset
  (i64), +0x18 triangle offset (i64); vertices 3 x f32; triangles 28 bytes (3 vertex indices, 3 edges, flags).
The parts of a world share one coordinate system (1-1 to 1-4 run end to end), the MSB's: the same as treasure
positions and the player's position in memory, so markers and the player land on the mesh as they are.

Output: tracker/maps.json (areas, their parts, triangle ranges and bounds) and tracker/<area>.bin per area:
int16 x, y, z per triangle corner (metres * QUANTUM), triangles grouped by part in maps.json order.
"""

from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from desap import msb, souls  # noqa: E402
from desap.gamedata import GameData  # noqa: E402

OUT = ROOT / "apworld" / "demons_souls" / "data" / "tracker"
QUANTUM = 32  # int16 units per metre (3 cm; every map fits in +-1024 m)
PART_NAVMESH = 8

AREAS = (  # id, name, [(map, part code, part name)]
    ("nexus", "The Nexus", [("m01_00_00_00", "Nexus", "The Nexus")]),
    ("tutorial", "Tutorial", [(f"m08_0{i}_00_00", "Tutorial", "Tutorial") for i in range(3)]),
    ("w1", "Boletarian Palace", [("m02_00_00_00", "1-1", "Gates of Boletaria"), ("m02_01_00_00", "1-2", "The Lord's Path"),
                                 ("m02_02_00_00", "1-3", "Inner Ward"), ("m02_03_00_00", "1-4", "The King's Tower")]),
    ("w2", "Stonefang Tunnel", [("m06_00_00_00", "2-1", "Smithing Grounds"), ("m06_01_00_00", "2-2", "The Tunnel City"),
                                ("m06_02_00_00", "2-3", "Underground Temple")]),
    ("w3", "Tower of Latria", [("m04_00_00_00", "3-1", "Prison of Hope"), ("m04_01_00_00", "3-2", "Upper Latria"),
                               ("m04_02_00_00", "3-3", "The Ivory Tower")]),
    ("w4", "Shrine of Storms", [("m03_01_00_00", "4-1", "Island's Edge"), ("m03_02_00_00", "4-2", "The Ritual Path"),
                                ("m03_03_00_00", "4-3", "Altar of Storms")]),
    ("w5", "Valley of Defilement", [("m05_00_00_00", "5-1", "Depraved Chasm"), ("m05_01_00_00", "5-2", "Swamp of Sorrow"),
                                    ("m05_02_00_00", "5-3", "Rotting Haven")]),
)


def navmesh_parts(path: Path) -> list[tuple[str, tuple[float, ...]]]:
    data = path.read_bytes()
    out = []
    for entry in msb._params(data).get("PARTS_PARAM_ST", []):
        name_at, part_type = struct.unpack_from("<qi", data, entry)
        if part_type == PART_NAVMESH:
            out.append((msb._text(data, entry + name_at), struct.unpack_from("<9f", data, entry + 0x20)))
    return out


def read_nvm(data: bytes) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    vertex_count, triangle_count = struct.unpack_from("<ii", data, 4)
    vertices_at, triangles_at = struct.unpack_from("<qq", data, 0x10)
    vertices = [struct.unpack_from("<3f", data, vertices_at + 12 * i) for i in range(vertex_count)]
    triangles = [struct.unpack_from("<3i", data, triangles_at + 28 * i) for i in range(triangle_count)]
    return vertices, triangles


def transform(placement: tuple[float, ...]):
    px, py, pz, rx, ry, rz, sx, sy, sz = placement
    cx, snx = math.cos(math.radians(rx)), math.sin(math.radians(rx))
    cy, sny = math.cos(math.radians(ry)), math.sin(math.radians(ry))
    cz, snz = math.cos(math.radians(rz)), math.sin(math.radians(rz))

    def apply(v):
        x, y, z = v[0] * sx, v[1] * sy, v[2] * sz
        y, z = y * cx - z * snx, y * snx + z * cx  # X
        x, y = x * cz - y * snz, x * snz + y * cz  # Z
        x, z = x * cy + z * sny, -x * sny + z * cy  # Y
        return x + px, y + py, z + pz
    return apply


def build_area(game: GameData, maps) -> tuple[bytes, list[dict]]:
    parts: dict[str, dict] = {}
    triangles_by_part: dict[str, list] = {}
    for map_id, code, name in maps:
        folder = game.dvdroot / "map"
        nvms = {f.stem: f.data for f in souls.read_bnd3((folder / map_id / f"{map_id}.nvmbnd").read_bytes())}
        for part_name, placement in navmesh_parts(folder / "mapstudio" / f"{map_id}.msb"):
            if part_name not in nvms:
                continue
            vertices, triangles = read_nvm(nvms[part_name])
            place = transform(placement)
            moved = [place(v) for v in vertices]
            for a, b, c in triangles:
                triangles_by_part.setdefault(code, []).append((moved[a], moved[b], moved[c]))
        parts.setdefault(code, {"code": code, "name": name, "maps": []})["maps"].append(map_id)
    data = bytearray()
    out_parts = []
    start = 0
    for code, info in parts.items():
        triangles = triangles_by_part.get(code, [])
        points = [p for t in triangles for p in t]
        for p in points:
            data += struct.pack("<3h", *(max(-32768, min(32767, round(c * QUANTUM))) for c in p))
        lo = [round(min(p[i] for p in points), 1) for i in range(3)]
        hi = [round(max(p[i] for p in points), 1) for i in range(3)]
        out_parts.append({**info, "start": start, "count": len(triangles), "min": lo, "max": hi})
        start += len(triangles)
    return bytes(data), out_parts


def main() -> None:
    game = GameData()
    OUT.mkdir(parents=True, exist_ok=True)
    index = {"quantum": QUANTUM, "areas": []}
    for area_id, name, maps in AREAS:
        data, parts = build_area(game, maps)
        (OUT / f"{area_id}.bin").write_bytes(data)
        index["areas"].append({"id": area_id, "name": name, "file": f"{area_id}.bin", "parts": parts,
                               "maps": [m for m, _c, _n in maps]})
        print(f"{area_id}: {sum(p['count'] for p in parts)} triangles, {len(data) // 1024} KB")
    (OUT / "maps.json").write_text(json.dumps(index, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
