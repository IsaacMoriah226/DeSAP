"""The map tracker's shapes, built on the player's PC from their own copy of the game (nothing from the game ships
with the .apworld): the navmeshes (what enemies and the player walk on), one scene per world, parts tagged.

Sources (<game folder>\\cp11demonssouls\\dvdroot\\map, the PS3 data the remake still runs on):
- mapstudio\\<map>.msb: navmesh parts (type 8) name an .nvm of the map's .nvmbnd and place it (position +0x20,
  rotation in degrees +0x2C, scale +0x38; applied scale, X, Z, Y, then translation, as SoulsFormats does).
- <map>\\<map>.nvmbnd: BND3 (format 0x74, little-endian) of NVM files: +4 vertex count, +8 triangle count, +0x10
  vertex offset (i64), +0x18 triangle offset (i64); vertices 3 x f32; triangles 28 bytes (3 vertex indices first).
The parts of a world share one coordinate system (1-1 to 1-4 run end to end), the MSB's: the same as location
positions and the player's position in memory, so markers and the player land on the mesh as they are.

Output, in %LOCALAPPDATA%\\DemonsSoulsAP\\maps: maps.json (areas, parts, triangle ranges and bounds) and <area>.bin
(int16 x, y, z per triangle corner, metres * QUANTUM; triangles grouped by part in maps.json order). About 2 s.
"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path

FORMAT = 1  # (bump when the output changes: shapes in the cache are rebuilt)
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
AREA_OF_MAP = {map_id: area_id for area_id, _name, maps in AREAS for map_id, _code, _part in maps}
AREA_OF_PART = {code: area_id for area_id, _name, maps in AREAS for _map, code, _part in maps}


class MapShapeError(RuntimeError):
    pass


def map_folder(game: Path) -> Path:
    return Path(game) / "cp11demonssouls" / "dvdroot" / "map"


# --- the file formats ----------------------------------------------------------------------------------------

def read_bnd3(data: bytes) -> dict[str, bytes]:
    """{file stem: data}."""
    if data[:4] != b"BND3" or data[0x0C] != 0x74 or data[0x0D] != 0:
        raise MapShapeError("not a BND3 archive this reader knows")
    count = struct.unpack_from("<i", data, 0x10)[0]
    out = {}
    for i in range(count):
        _flags, size, offset, _file_id, name_at, _usize = struct.unpack_from("<IiIiii", data, 0x20 + i * 24)
        name = data[name_at:data.index(b"\0", name_at)].decode("cp932")
        out[name.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]] = data[offset:offset + size]
    return out


def _text(data: bytes, at: int) -> str:
    end = data.find(b"\0", at)
    return data[at:end].decode("cp932", "replace") if 0 <= at < len(data) else ""


def _msb_params(data: bytes) -> dict[str, list[int]]:
    """An MSB's param lists (the remake's: 64-bit offsets): name -> entry offsets."""
    out: dict[str, list[int]] = {}
    at = 0
    for _ in range(64):
        if at + 24 > len(data):
            break
        name_at, count = struct.unpack_from("<qi", data, at + 8)
        if count <= 0 or count > 1 << 20:
            break
        offsets = list(struct.unpack_from(f"<{count}q", data, at + 24))
        out[_text(data, name_at)] = offsets[:-1]
        if offsets[-1] <= 0:
            break
        at = offsets[-1]
    return out


def navmesh_parts(msb: bytes) -> list[tuple[str, tuple[float, ...]]]:
    out = []
    for entry in _msb_params(msb).get("PARTS_PARAM_ST", []):
        name_at, part_type = struct.unpack_from("<qi", msb, entry)
        if part_type == PART_NAVMESH:
            out.append((_text(msb, entry + name_at), struct.unpack_from("<9f", msb, entry + 0x20)))
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


# --- building ------------------------------------------------------------------------------------------------

def build_area(folder: Path, maps) -> tuple[bytes, list[dict]]:
    parts: dict[str, dict] = {}
    triangles_by_part: dict[str, list] = {}
    for map_id, code, name in maps:
        nvms = read_bnd3((folder / map_id / f"{map_id}.nvmbnd").read_bytes())
        for part_name, placement in navmesh_parts((folder / "mapstudio" / f"{map_id}.msb").read_bytes()):
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
        if not points:
            raise MapShapeError(f"no navmesh for {code}")
        data += struct.pack(f"<{len(points) * 3}h", *(max(-32768, min(32767, round(c * QUANTUM)))
                                                      for p in points for c in p))
        lo = [round(min(p[i] for p in points), 1) for i in range(3)]
        hi = [round(max(p[i] for p in points), 1) for i in range(3)]
        out_parts.append({**info, "start": start, "count": len(triangles), "min": lo, "max": hi})
        start += len(triangles)
    return bytes(data), out_parts


def build(game: Path, out: Path) -> dict:
    """Build every area's shape from the game in folder `game` into `out`; returns the index (maps.json)."""
    folder = map_folder(game)
    if not (folder / "mapstudio").is_dir():
        raise MapShapeError(f"no Demon's Souls map data in {game}")
    out.mkdir(parents=True, exist_ok=True)
    index = {"format": FORMAT, "quantum": QUANTUM, "areas": []}
    try:
        for area_id, name, maps in AREAS:
            data, parts = build_area(folder, maps)
            (out / f"{area_id}.bin").write_bytes(data)
            index["areas"].append({"id": area_id, "name": name, "file": f"{area_id}.bin", "parts": parts,
                                   "maps": [m for m, _c, _n in maps]})
    except (OSError, struct.error, ValueError, IndexError) as error:
        raise MapShapeError(f"could not read the game's maps: {error}") from error
    (out / "maps.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    return index


def load(out: Path) -> dict | None:
    """The index of shapes already built in `out` (None: not built, or by an older client)."""
    try:
        index = json.loads((out / "maps.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if index.get("format") != FORMAT or not all((out / area["file"]).is_file() for area in index["areas"]):
        return None
    return index
