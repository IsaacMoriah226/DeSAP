"""Read the true pickup flag of every treasure of the world being played from the game's own treasure records, and
compare with the MSB treasures (found 2026-11-21: the remake's flags are NOT 10240 + 512 * block + MSB index; they
follow another order, set from Bluepoint's level data).

A treasure record (one per corpse or chest of every block of the loaded world, looted ones included while the world
is loaded): +0x0 i32 ordinal, +0x4 u32 entity (0x20000000 + block << 24 | n), +0x8 i32 pickup flag, +0xc i32 number
of item slots, +0x10 5 x i32 lot ids, +0x24 the items it gives now; the qword 0x90260e038 (its allocator) at -0x30.

  python -I tools/map_treasures.py <out.json>      scan (about 40 s), save {map: [[flag, [lots]], ...]}, compare
"""

from __future__ import annotations

import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apworld" / "demons_souls"))
from client.memory import GameMemory  # noqa: E402
from desap import msb  # noqa: E402
from desap.gamedata import GameData  # noqa: E402

SIGNATURE = struct.pack("<Q", 0x90260E038)


def record(memory: GameMemory, address: int):
    """(entity, flag, lots) of a treasure record at `address`, or None."""
    try:
        data = memory.read(address, 0x24)
    except OSError:
        return None
    _ordinal, entity, flag, slots = struct.unpack_from("<iIii", data, 0)
    lots = [lot for lot in struct.unpack_from("<5i", data, 0x10) if lot > 0]
    if not (0 < slots <= 16 and lots and 0 <= flag < 18048 and 0x20 <= entity >> 24 < 0x30):
        return None
    return entity, flag, lots


def scan(memory: GameMemory) -> list[tuple[int, int, int, list[int]]]:
    """(area, block, flag, lots) of every treasure record in memory: the records behind the allocator signature,
    then every record in the object pointer lists that point at them (some records sit elsewhere)."""
    hits = memory.find_guest([SIGNATURE], limit=1_000_000)[SIGNATURE]
    found = {}
    for hit in hits:
        r = record(memory, hit + 0x30)
        if r:
            found[hit + 0x30] = r
    if found:
        sample = list(found)[:4]
        pointers = memory.find_guest([struct.pack("<Q", a) for a in sample], limit=16)
        for slot in {p for a in sample for p in pointers[struct.pack("<Q", a)]}:
            for direction in (-8, 8):
                at, misses = slot, 0
                while misses < 64:
                    at += direction
                    try:
                        target = memory.u64(at)
                    except OSError:
                        break
                    r = record(memory, target) if 0x10000 < target < 1 << 47 else None
                    if r:
                        found[target] = r
                        misses = 0
                    else:
                        misses += 1
    area = memory.u8(memory.u64(0x9027BF328) + 0x3CD3)
    unique = {(entity, flag): (entity >> 24) - 0x20 for entity, flag, _lots in found.values()}
    lots_of = {(entity, flag): lots for entity, flag, lots in found.values()}
    return [(area, block, flag, lots_of[(entity, flag)]) for (entity, flag), block in unique.items()]


def main() -> None:
    out_path = Path(sys.argv[1])
    with GameMemory() as memory:
        records = scan(memory)
    by_map: dict[str, list] = defaultdict(list)
    for area, block, flag, lots in records:
        by_map[f"m{area:02d}_{block:02d}_00_00"].append([flag, lots])
    out_path.write_text(json.dumps(by_map, indent=1), encoding="utf-8")
    game = GameData()
    for map_id, entries in sorted(by_map.items()):
        path = game.dvdroot / "map" / "mapstudio" / f"{map_id}.msb"
        treasures = msb.read_msb(path).treasures if path.exists() else []
        flags_by_lots: dict[tuple, list[int]] = defaultdict(list)
        for flag, lots in entries:
            flags_by_lots[tuple(lots)].append(flag)
        matched = sum(1 for t in treasures if tuple(t.item_lots) in flags_by_lots)
        extra = [e for e in entries if not any(tuple(e[1]) == tuple(t.item_lots) for t in treasures)]
        dup = {k: v for k, v in flags_by_lots.items() if len(v) > 1}
        print(f"{map_id}: {len(entries)} records, MSB {len(treasures)} treasures, {matched} matched by lots, "
              f"{len(extra)} not in the MSB {extra[:6]}, same lots twice: {dup}")
        missing = [(i, t.name, t.item_lots) for i, t in enumerate(treasures) if tuple(t.item_lots) not in flags_by_lots]
        for item in missing:
            print("   no record:", item)


if __name__ == "__main__":
    main()
