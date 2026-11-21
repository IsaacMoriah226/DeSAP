"""Which game sources use each location's item lot (the client rewrites a location's lot in memory, so a lot that
also feeds something that is not that location would change that drop too).

Users counted:
- MSB treasures (every map), by lot id;
- MSB enemies whose NpcParam row lists the lot in itemLotId_1..6, counted per placed enemy;
- Lua `GetRateItem(<lot>)` calls (comments stripped).

  python -I tools/check_lot_users.py        prints every location lot with a user that is not one of its locations
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from desap import msb, souls  # noqa: E402
from desap.events import read_script  # noqa: E402
from desap.gamedata import GameData  # noqa: E402


def lot_users(game: GameData) -> dict[int, list[str]]:
    users: dict[int, list[str]] = collections.defaultdict(list)
    for location in game.treasures():
        for lot in location.lots:
            users[lot].append(f"treasure {location.map} #{location.index}")
    npc_def = souls.load_paramdef("NpcParam")
    npcs = souls.read_param(game.params["NpcParam"].data, npc_def, extended=True).by_id()
    npc_lots = {row_id: [row[f"itemLotId_{i}"] for i in range(1, 7) if row[f"itemLotId_{i}"] > 0]
                for row_id, row in npcs.items()}
    for path in sorted((game.dvdroot / "map" / "mapstudio").glob("m0*.msb")):
        if len(path.name) != 16:
            continue
        for enemy in msb.read_enemies(path):
            for lot in npc_lots.get(enemy.npc_param, []):
                users[lot].append(f"enemy {path.stem} {enemy.name} (entity {enemy.entity_id}, npc {enemy.npc_param})")
    for path in sorted((game.dvdroot / "script").glob("*.lua")):
        for m in re.finditer(r"GetRateItem\(\s*(\d+)\s*\)", read_script(path)):
            users[int(m.group(1))].append(f"lua {path.stem}")
    return users


def main() -> None:
    game = GameData()
    users = lot_users(game)
    locations = json.loads((ROOT / "apworld" / "demons_souls" / "data" / "locations.json").read_text(encoding="utf-8"))
    by_lot: dict[int, list[dict]] = collections.defaultdict(list)
    for location in locations:
        if location["code"] and "lot" in location["game"]:
            by_lot[location["game"]["lot"]].append(location)
    problems = 0
    for lot, here in sorted(by_lot.items()):
        expected = len(here)
        found = users.get(lot, [])
        kinds = collections.Counter(u.split(" ", 1)[0] for u in found)
        mine = {location["kind"] for location in here}
        # one user per location is expected (a treasure per treasure location, an enemy or a script per drop)
        if len(found) > expected or not found:
            problems += 1
            shared = any(location["game"].get("shared_lot") for location in here)
            print(f"lot {lot}: {len(found)} users for {expected} location(s) {sorted(mine)}"
                  f"{' (marked shared)' if shared else ''}")
            for location in here:
                print(f"    location {location['name']}")
            for user in found[:12]:
                print(f"    user     {user}")
            if len(found) > 12:
                print(f"    ... {len(found) - 12} more ({dict(kinds)})")
    print(f"{problems} lots to look at")


if __name__ == "__main__":
    main()
