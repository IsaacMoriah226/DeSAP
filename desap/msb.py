"""Reader for the remake's MSB map files (map\\mapstudio\\*.msb): the PS3 Demon's Souls layout (SoulsFormats'
MSBD) with 64-bit offsets. Only what the location table needs: parts (name, type, position) and treasure events.

Param: +8 name offset (i64), +16 entry count + 1 (i32), +24 entry offsets (i64), the last one the next param's.
Event: +0 name offset (i64), +8 event id, +12 type, +16 id, +20 -1, +24 base data offset (i64),
       +32 type data offset (i64). Base data: part index, region index, entity id, 0.
Treasure type data (type 4): 0, 0, part index, -1, then 5 x (item lot id, -1) (the PS3 layout has one 0 and
no -1 after the part index).
Part: +0 name offset (i64), +8 type, position at +0x20 (3 x f32).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

EVENT_TREASURE = 4


@dataclass
class Part:
    index: int
    name: str
    type: int
    position: tuple[float, float, float]


@dataclass
class Treasure:
    name: str
    event_id: int
    entity_id: int
    part: Part | None
    item_lots: list[int] = field(default_factory=list)


@dataclass
class Msb:
    map: str
    parts: list[Part]
    treasures: list[Treasure]


def _text(data: bytes, at: int) -> str:
    end = data.find(b"\0", at)
    return data[at:end].decode("cp932", "replace") if 0 <= at < len(data) else ""


def _params(data: bytes) -> dict[str, list[int]]:
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


@dataclass
class Enemy:
    name: str
    entity_id: int
    npc_param: int
    talk_id: int
    position: tuple[float, float, float]


PART_ENEMY = 2


def read_enemies(path: Path) -> list[Enemy]:
    """Enemy parts (type 2): +0x68 entity data offset (i64; entity id first), +0x70 type data offset (i64);
    type data +0xc NpcParam id, +0x10 talk id (the PS3 layout's)."""
    data = path.read_bytes()
    out = []
    for entry in _params(data).get("PARTS_PARAM_ST", []):
        name_at, part_type = struct.unpack_from("<qi", data, entry)
        if part_type != PART_ENEMY:
            continue
        entity_at, type_at = struct.unpack_from("<qq", data, entry + 0x68)
        entity_id = struct.unpack_from("<i", data, entry + entity_at)[0]
        npc_param, talk_id = struct.unpack_from("<ii", data, entry + type_at + 0xC)
        out.append(Enemy(_text(data, entry + name_at), entity_id, npc_param, talk_id,
                         struct.unpack_from("<3f", data, entry + 0x20)))
    return out


def read_msb(path: Path) -> Msb:
    data = path.read_bytes()
    params = _params(data)
    parts = []
    for i, entry in enumerate(params.get("PARTS_PARAM_ST", [])):
        name_at, part_type = struct.unpack_from("<qi", data, entry)
        parts.append(Part(i, _text(data, entry + name_at), part_type, struct.unpack_from("<3f", data, entry + 0x20)))
    treasures = []
    for entry in params.get("EVENT_PARAM_ST", []):
        name_at, event_id, event_type = struct.unpack_from("<qii", data, entry)
        if event_type != EVENT_TREASURE:
            continue
        base_at, type_at = struct.unpack_from("<qq", data, entry + 24)
        _part, _region, entity_id = struct.unpack_from("<iii", data, entry + base_at)
        part_index = struct.unpack_from("<i", data, entry + type_at + 8)[0]
        lots = []
        for i in range(5):
            lot, _minus_one = struct.unpack_from("<ii", data, entry + type_at + 16 + i * 8)
            if lot > 0:
                lots.append(lot)
        part = parts[part_index] if 0 <= part_index < len(parts) else None
        treasures.append(Treasure(_text(data, entry + name_at), event_id, entity_id, part, lots))
    return Msb(path.stem, parts, treasures)
