"""Write every known location, with the event flag that marks it, as JSON from the game dump:
treasures (map pickups), event rewards (boss souls, key items), limited shop stock, one-time enemy drops.

Usage: python -I build_locations.py [<out.json>] [<game folder>]   (default C:\\Dev\\DeSArchi\\work\\locations.json)
"""

import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from desap import souls  # noqa: E402
from desap.events import enemy_kills, event_rewards  # noqa: E402
from desap.gamedata import DEFAULT_GAME, GameData  # noqa: E402

SHOP_CATEGORIES = {0: 0x00000000, 1: 0x10000000, 2: 0x20000000, 3: 0x40000000}
ENEMY_DROP_MIN_CHANCE = 1000  # only guaranteed drops (chances are out of 1000)
ENDING_CHOICE = {"OnEvent_GoodSoul", "OnEvent_BadSoul"}  # the final soul choice in the Nexus


def shops(game: GameData) -> list[dict]:
    rows = souls.read_param(game.params["ShopLineupParam"].data, souls.load_paramdef("ShopLineupParam")).rows
    out = []
    for row in rows:
        v = row.values
        if v["sellQuantity"] <= 0 or v["eventFlag"] <= 0:
            continue  # unlimited stock: not a location
        category = SHOP_CATEGORIES.get(v["equipType"], -1)
        out.append({"type": "shop", "shop_row": row.id, "shop": row.name, "item": game.item_name(category, v["equipId"]),
                    "item_id": v["equipId"], "category": v["equipType"], "price": v["value"],
                    "quantity": v["sellQuantity"],
                    # an 8-bit purchase counter: bought when the byte at flag // 8 is not 0
                    "flag": v["eventFlag"], "flag_kind": "counter8"})
    return out


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:\Dev\DeSArchi\work\locations.json")
    game = GameData(Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_GAME)
    rows: list[dict] = []
    for t in game.treasures():
        if not any(t.lots.values()):
            continue
        row = {"type": "treasure", **asdict(t), "flag_kind": "bit"}
        row["lots"] = {str(lot): items for lot, items in row["lots"].items()}
        rows.append(row)
    for e in event_rewards(game):
        if e.flag is None or e.function in ENDING_CHOICE:
            continue
        rows.append({"type": "event", **asdict(e), "flag_kind": "bit"})
    for k in enemy_kills(game):
        if any(i.chance >= ENEMY_DROP_MIN_CHANCE for items in k.drops.values() for i in items):
            row = {"type": "enemy", **asdict(k), "flag_kind": "bit"}
            row["drops"] = {str(lot): items for lot, items in row["drops"].items()}
            rows.append(row)
    rows += shops(game)
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} locations -> {out}: {dict(Counter(r['type'] for r in rows))}")


if __name__ == "__main__":
    main()
