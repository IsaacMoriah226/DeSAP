"""The world's tables, generated from the game files by DeSAP/tools/build_world_data.py (do not edit the JSON
files by hand): data/items.json and data/locations.json. Read with pkgutil so they load from a packed .apworld.

Item ids (the client decodes them the same way):
    ITEM_BASE + kind * 100_000_000 + game_id * 100 + count   for game items (kind: 0 weapon, 1 armor, 2 ring,
                                                              3 goods; game_id: the id in the game's params)
    ITEM_BASE + 900_000_000 + n                               for Archipelago-only items (world locks)
Location ids:
    LOCATION_BASE + (world * 100 + part) * 10_000 + treasure index * 10 + lot slot   treasures (map mWW_PP)
    LOCATION_BASE + 100_000_000 + (world * 100 + part) * 100_000 + lot              scripted events (boss souls)
    LOCATION_BASE + 200_000_000 + ShopLineupParam row                               shop entries
    LOCATION_BASE + 300_000_000 + event flag                                         scripted enemy kills
"""

from __future__ import annotations

import json
import pkgutil
from dataclasses import dataclass, field

from .ids import ITEM_BASE, KINDS, LOCATION_BASE, LOCK_ITEM_OFFSET  # noqa: F401 (re-exported)


@dataclass(frozen=True)
class ItemData:
    name: str
    code: int
    kind: str  # weapon, armor, ring, goods, or "archipelago" for world locks
    game_id: int  # the id in the game's params (0 for Archipelago-only items)
    count: int
    classification: str  # progression, useful, filler
    groups: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocationData:
    name: str
    code: int | None  # None for events (a part's boss)
    part: str  # the world part (region) it is in: "Tutorial", "Nexus", "1-1" ... "5-3"
    kind: str  # treasure, event, shop, enemy
    vanilla_item: str  # the item name it holds in the unrandomized game
    description: str = ""
    requires: tuple[str, ...] = ()  # item names, or "boss:<part>" (that part's boss defeated)
    missable: str = ""  # why it can be lost; missable locations only get filler
    tendency: str = ""  # the world tendency it needs, if any (also makes it missable)
    groups: tuple[str, ...] = ()
    game: dict = field(default_factory=dict, compare=False, hash=False)  # map, flag, index, lot, ... for the client


def _load(name: str) -> list[dict]:
    raw = pkgutil.get_data(__name__, f"data/{name}")
    if raw is None:
        raise FileNotFoundError(f"data/{name} is missing from the world")
    return json.loads(raw.decode("utf-8"))


ITEMS: dict[str, ItemData] = {
    entry["name"]: ItemData(entry["name"], entry["code"], entry["kind"], entry["game_id"], entry["count"],
                            entry["classification"], tuple(entry.get("groups", ())))
    for entry in _load("items.json")
}

LOCATIONS: dict[str, LocationData] = {
    entry["name"]: LocationData(entry["name"], entry["code"], entry["part"], entry["kind"], entry["vanilla_item"],
                                entry.get("description", ""), tuple(entry.get("requires", ())),
                                entry.get("missable", ""), entry.get("tendency", ""), tuple(entry.get("groups", ())),
                                entry.get("game", {}))
    for entry in _load("locations.json")
}
