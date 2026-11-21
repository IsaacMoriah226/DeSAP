"""Merge the treasure-record scans (tools/map_treasures.py output, work/treasure_flags/*.json) into one table of
true pickup flags, keyed by (map, first lot), and compare it with the MSB-index rule the location table used.

The map comes from the flag itself (10240 + 512 * block + n; the entity's block byte is off by one in the Shrine of
Storms, whose maps start at m03_01), the area from the scan file. Records of Bluepoint's own collectibles (lots
99900+, flags below 10240) are dropped.

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

SCANS = Path(r"C:\Dev\DeSArchi\work\treasure_flags")
OUT = ROOT / "data" / "treasure_flags.json"
AREA_OF_SCAN = {"boletaria": 2, "boletaria_old": 2, "stonefang": 6, "latria": 4, "shrine": 3, "valley": 5,
                "nexus": 1}


def main() -> None:
    game = GameData()
    flags: dict[str, dict[int, int]] = defaultdict(dict)  # map -> first lot -> flag
    for path in sorted(SCANS.glob("*.json")):
        area = AREA_OF_SCAN.get(path.stem)
        if area is None:
            continue
        for _label, entries in json.loads(path.read_text(encoding="utf-8")).items():
            for flag, lots in entries:
                if not 10240 <= flag < 12288 or lots[0] >= 99900:
                    continue
                map_id = f"m{area:02d}_{(flag - 10240) // 512:02d}_00_00"
                known = flags[map_id].get(lots[0])
                if known is not None and known != flag:
                    raise ValueError(f"{map_id} lot {lots[0]}: flags {known} and {flag} in two scans")
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
