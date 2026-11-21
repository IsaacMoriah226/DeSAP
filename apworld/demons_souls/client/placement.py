"""What the game should hand out at each location, how to see that a location was checked, and how received
weapons are upgraded. Pure functions (no game access), unit-tested in DeSAP.

Delivery (items_handling 0b111: the server sends every item, own ones included):
- A location whose lot the client rewrites ("physical": treasures, scripted rewards, one-time enemy drops; shop
  rows when the shop table is found) gives its item in the game itself when it holds an item of this world. The
  server's copy of that item is then skipped, but only if the location's flag is set in the save (an item
  collected some other way, e.g. !collect, still has to be given).
- Items for other worlds are placeholders (goods 2055, 2057, 9998 on corpses, one per item of a corpse; goods
  2056 in shops), with the Nexial Binding's icon, named after the nearby items ("Archipelago Item" otherwise),
  that the client removes from the inventory.
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

# Unused goods rows (2055 and 2057: upgrade stones cut from the game, "UNUSED DATA"; 9998 a key item, one at most):
# stackable, so a corpse with several other-world items shows one popup each (verified). Their text is set through
# the loaded text tables (any length, verified); their look is the Nexial Binding's: its iconId and the remake's UI
# link at goods row +64 (dress_placeholders in context.py, verified).
# Up to three placeholders per corpse (goods 2055 and 2057, stackable materials cut from the game, and 9998, a key
# item, one at most): each item of a corpse holding several items for other worlds gets its own, named after it.
PLACEHOLDERS = ((CATEGORY["goods"], 2055, 1), (CATEGORY["goods"], 2057, 1), (CATEGORY["goods"], 9998, 1))
PLACEHOLDER = PLACEHOLDERS[0]
GENERIC_NAME = "Archipelago Item"
PLACEHOLDER_TEXTS = {}
for _category, _item, _count in PLACEHOLDERS:
    PLACEHOLDER_TEXTS.update({
        f"GOODS_NAME_{_item}": GENERIC_NAME,
        f"GOODS_INFO_{_item}": "An item for another world",
        f"GOODS_CAPTION_{_item}": "This item belongs to another player's world in the Archipelago multiworld. "
                                  "It has been sent to them; the client takes this token away.",
    })
NAME_KEYS = tuple(f"GOODS_NAME_{item}" for _category, item, _count in PLACEHOLDERS)
# While you play, the client names the placeholder after the nearest unchecked location (in the world you are in)
# that holds another world's item: "<Player>'s <Item>". You stand at a corpse to loot it, so the pickup's popup shows
# that location's item. Scripted rewards have no position: they keep the generic name.
NAMING_RANGE = 40.0  # metres: farther than that, the generic name
# Shop rows holding another world's item sell a second placeholder (goods 2056, also cut from the game).
SHOP_PLACEHOLDER = (CATEGORY["goods"], 2056, 1)
SHOP_PLACEHOLDER_TEXTS = {
    "GOODS_NAME_2056": "[AP] Item for another world",
    "GOODS_INFO_2056": "Archipelago: sends an item to another world",
    "GOODS_CAPTION_2056": "Buying this sends an item to another player's world in the Archipelago multiworld; "
                          "the client takes this token away.",
}


def _spot(location) -> tuple:
    return location.game["map"], tuple(location.game.get("position") or ())


def placeholder_for(code: int) -> tuple[int, int, int]:
    rank = RANK.get(code, 0)
    return PLACEHOLDERS[rank] if rank < len(PLACEHOLDERS) else PLACEHOLDERS[0]


def nearest_foreign(position, area: int, scouted: dict, checked: frozenset, slot: int):
    """The nearest corpse (in this area) with unchecked locations holding other worlds' items: [(rank, item)] of
    those, and its distance; ([], inf) when there is none."""
    best, best_spot, best_distance = [], None, float("inf")
    if position is None:
        return best, best_distance
    for code, item in scouted.items():
        if item.player == slot or code in checked:
            continue
        location = LOCATION_BY_CODE.get(code)
        if location is None or "position" not in location.game or world_of_map(location.game["map"]) != area:
            continue
        x, y, z = location.game["position"]
        distance = ((x - position[0]) ** 2 + (y - position[1]) ** 2 + (z - position[2]) ** 2) ** 0.5
        if distance < best_distance - 0.01:
            best, best_spot, best_distance = [(RANK.get(code, 0), item)], _spot(location), distance
        elif best_spot is not None and _spot(location) == best_spot:
            best.append((RANK.get(code, 0), item))
    return sorted(best, key=lambda pair: pair[0]), best_distance


def placeholder_names(found: list, describe) -> dict[str, str]:
    """Each placeholder's name for the corpse's items `found` ([(rank, item)]); describe(item) -> "Player's Item"."""
    names = {key: GENERIC_NAME for key in NAME_KEYS}
    extra = [item for rank, item in found if rank >= len(PLACEHOLDERS)]
    for rank, item in found:
        if rank < len(PLACEHOLDERS):
            names[NAME_KEYS[rank]] = describe(item)
    if extra:
        first = names[NAME_KEYS[0]]
        names[NAME_KEYS[0]] = (first if first != GENERIC_NAME else describe(extra[0])) + \
            f" and {len(extra) if first != GENERIC_NAME else len(extra) - 1} more"
    return names
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


# A location's rank among the locations of its corpse (same map and position), in id order: which placeholder its
# lot gives when it holds another world's item (ranks past the last placeholder share the first).
RANK: dict[int, int] = {}
_by_spot: dict[tuple, list[int]] = {}
for _code, _location in sorted(LOCATION_BY_CODE.items()):
    if "position" in _location.game:
        _by_spot.setdefault(_spot(_location), []).append(_code)
for _codes in _by_spot.values():
    for _rank, _code in enumerate(_codes):
        RANK[_code] = _rank
