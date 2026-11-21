"""What the game should hand out at each location, how to see that a location was checked, and how received
weapons are upgraded. Pure functions (no game access), unit-tested in DeSAP.

Delivery (items_handling 0b111: the server sends every item, own ones included):
- A location whose lot the client rewrites ("physical": treasures, scripted rewards, one-time enemy drops; shop
  rows when the shop table is found) gives its item in the game itself when it holds an item of this world. The
  server's copy of that item is then skipped, but only if the location's flag is set in the save (an item
  collected some other way, e.g. !collect, still has to be given).
- Items for other worlds are a placeholder (one goods item, renamed "Archipelago", Nexial Binding icon) that the
  client removes from the inventory.
- Locations on a shared lot (Primeval Demons, the two Vanguards, two Fat Officials' grass) get an empty lot; the
  client gives their item when the location's flag turns on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..data import ITEMS, LOCATIONS, ItemData, LocationData
from ..ids import ITEM_BASE, KINDS, LOCK_ITEM_OFFSET
from .addresses import CATEGORY
from .flags import Flags, world_of_map

# Unused goods row 2055 (an upgrade stone cut from the game, "UNUSED DATA"; PS3 "Large Clearstone Shard"). Goods
# 9998 was tried first (2026-11-21): a key item, one at most, so a corpse with several other-world items showed one
# popup. 2055 is a stackable material (to check in game). Its text is set through the loaded text tables (any
# length, verified). Its icon cannot be changed through EquipParamGoods' iconId: the remake draws icons by item id.
PLACEHOLDER = (CATEGORY["goods"], 2055, 1)
PLACEHOLDER_TEXTS = {
    "GOODS_NAME_2055": "Archipelago Item",
    "GOODS_INFO_2055": "An item for another world",
    "GOODS_CAPTION_2055": "This item belongs to another player's world in the Archipelago multiworld. "
                          "It has been sent to them; the client takes this token away.",
}
GOAL_FLAG, GOAL_WORLD = 70, 1  # OnCharacterDead(70, 821): False King Allant (m01_00_00_00_eventboss.lua)
AMMUNITION = range(160000, 170000)

ITEM_BY_CODE: dict[int, ItemData] = {item.code: item for item in ITEMS.values()}
LOCATION_BY_CODE: dict[int, LocationData] = {
    location.code: location for location in LOCATIONS.values() if location.code is not None}


def game_item(code: int) -> tuple[int, int, int] | None:
    """(category, id, count) of one of this world's items; None for an Archipelago-only item (a world lock)."""
    item = ITEM_BY_CODE.get(code)
    if item is None or item.kind not in KINDS:
        return None
    return CATEGORY[item.kind], item.game_id, item.count


def is_lock(code: int) -> bool:
    return code - ITEM_BASE >= LOCK_ITEM_OFFSET and code in ITEM_BY_CODE


LOCK_CODES: dict[str, int] = {item.name: item.code for item in ITEMS.values() if is_lock(item.code)}


@dataclass(frozen=True)
class Check:
    """How to see that a location was checked."""
    flag: int
    world: int
    counter: bool = False  # a shop's 8-bit purchase counter (the whole byte at flag // 8) instead of one bit

    def done(self, flags: Flags) -> bool:
        return flags.byte(self.flag, self.world) > 0 if self.counter else flags.get(self.flag, self.world)


def check_of(location: LocationData) -> Check:
    game = location.game
    if location.kind == "shop":
        return Check(game["flag"], 0, counter=True)
    flag = game.get("detect_flag") or game["flag"]
    return Check(flag, world_of_map(game["map"]))


# Locations whose flag was not measured in game (data/treasure_flags.json: the tutorial so far) are left out: a
# wrong flag would report the wrong location.
CHECKS: dict[int, Check] = {code: check_of(location) for code, location in LOCATION_BY_CODE.items()
                            if not location.game.get("flag_unverified")}
# Each location's bit in the save's "delivered by the game" flags (flags.py): location id order. A client must
# match the world version that generated the seed (the slot data carries it).
LOCATION_INDEX: dict[int, int] = {code: i for i, code in enumerate(sorted(LOCATION_BY_CODE))}


def has_lot(location: LocationData) -> bool:
    return location.kind in ("treasure", "event", "enemy") and "lot" in location.game


def shared(location: LocationData) -> bool:
    return bool(location.game.get("shared_lot"))


# --- weapon upgrades ------------------------------------------------------------------------------------------


def upgrade_path(weapon_id: int, rows: set[int]) -> tuple[int, int, int]:
    """(path base id, level, the path's maximum level). The normal path is base + 0..10; the others (Quality,
    Mercury, Sharp, ...) are base + 10 * p + 1..5."""
    base, offset = weapon_id // 100 * 100, weapon_id % 100
    if offset <= 10:
        top = 0
        while top < 10 and base + top + 1 in rows:
            top += 1
        return base, offset, top
    first = base + offset // 10 * 10
    top = max(k for k in range(1, 10) if first + k in rows) if any(first + k in rows for k in range(1, 10)) else 0
    return first, offset % 10, top


def upgraded_weapon(weapon_id: int, held: list[int], rows: set[int]) -> int:
    """`weapon_id` upgraded to the same share of its normal path's maximum as the best of the held weapons (rounded
    up), never below its own level (DESIGN.md: proportional auto-upgrade)."""
    if weapon_id in AMMUNITION or weapon_id not in rows:
        return weapon_id
    best = 0.0
    for other in held:
        if other in AMMUNITION or other not in rows:
            continue
        _base, level, top = upgrade_path(other, rows)
        if top:
            best = max(best, level / top)
    base, level, top = upgrade_path(weapon_id, rows)
    if not top or weapon_id % 100 > 10:  # not upgradable, or already on a special path
        return weapon_id
    target = min(top, max(level, math.ceil(best * top - 1e-9)))
    return base + target if base + target in rows else weapon_id
