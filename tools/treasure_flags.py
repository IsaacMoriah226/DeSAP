"""Merge the treasure-record scans (tools/map_treasures.py output, work/treasure_flags/*.json) into one table of
true pickup flags, keyed by (map, first lot), and compare it with the MSB-index rule the location table used.

Each record is placed by its first lot (unique within an area) on the MSB treasure that has it; the area comes from
the scan file. (The record's block byte is off by one in the Shrine of Storms, and the tutorial uses global flags
14050+, so neither the entity nor the flag gives the map.) Bluepoint's own collectibles (lots 99900+) match no MSB
treasure and are dropped.

  python -I tools/treasure_flags.py     writes data/treasure_flags.json and prints the differences
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from desap import msb  # noqa: E402
from desap.gamedata import GameData  # noqa: E402

from desap import local  # noqa: E402

SCANS = local.path("work") / "treasure_flags"
OUT = ROOT / "data" / "treasure_flags.json"
AREA_OF_SCAN = {"boletaria": 2, "boletaria_old": 2, "stonefang": 6, "latria": 4, "shrine": 3, "valley": 5,
                "nexus": 1, "tutorial": 8, "tutorial_outpost": 8, "tutorial_egress": 8}


def main() -> None:
    game = GameData()
    lot_maps: dict[int, dict[int, str]] = defaultdict(dict)  # area -> first lot -> map
    for path in sorted((game.dvdroot / "map" / "mapstudio").glob("m0*.msb")):
        if len(path.name) == 16:
            for treasure in msb.read_msb(path).treasures:
                if treasure.item_lots:
                    lot_maps[int(path.stem[1:3])][treasure.item_lots[0]] = path.stem
    flags: dict[str, dict[int, int]] = defaultdict(dict)  # map -> first lot -> flag
    for path in sorted(SCANS.glob("*.json")):
        area = AREA_OF_SCAN.get(path.stem)
        if area is None:
            continue
        for _label, entries in json.loads(path.read_text(encoding="utf-8")).items():
            for flag, lots in entries:
                map_id = lot_maps[area].get(lots[0])
                if map_id is None:
                    continue  # Bluepoint's collectibles (lots 99900+): not MSB treasures
                known = flags[map_id].get(lots[0])
                if known is not None and known != flag:
                    # RP 4-2's Makoto: the unreachable display copy (flag 1511) shares the lot with the real corpse
                    # (a pickup flag, 10240 and up): keep the pickup flag
                    if (known >= 10240) == (flag >= 10240):
                        raise ValueError(f"{map_id} lot {lots[0]}: flags {known} and {flag} in two scans")
                    flag = max(known, flag)
                flags[map_id][lots[0]] = flag
    report = []
    for path in sorted((game.dvdroot / "map" / "mapstudio").glob("m0*.msb")):
        if len(path.name) != 16:
            continue
        treasures = msb.read_msb(path).treasures
        if not treasures:
            continue
        sub = int(path.stem[4:6])
        table = flags.get(path.stem, {})
        differ = unknown = 0
        for index, treasure in enumerate(treasures):
            true = table.get(treasure.item_lots[0]) if treasure.item_lots else None
            rule = 10240 + 512 * sub + index
            if true is None:
                unknown += 1
            elif true != rule:
                differ += 1
        report.append(f"{path.stem}: {len(treasures)} treasures, {len(table)} known flags, {differ} differ from the "
                      f"index rule, {unknown} unknown")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({m: {str(k): v for k, v in sorted(t.items())} for m, t in sorted(flags.items())},
                              indent=1), encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
