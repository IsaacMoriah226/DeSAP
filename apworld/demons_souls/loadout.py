"""Randomized starting loadouts (the RandomizeStartingLoadout option), after Dark Souls III's randomizer: each class
keeps its stats, spells, ring and items, and gets random weapons, shield and armor it can use.

- The main weapon and a melee second weapon: random melee weapons the class can wield one-handed with its stats
  (every requirement met; any weapon with RemoveStatRequirements), at most a little heavier than what they replace.
- A bow stays a bow (the class's arrows still fit); a catalyst or talisman stays as it is (the class's spells need
  it); a shield becomes another shield the class can hold.
- Armor: a random piece in every slot, the set within the class's own armor weight (+3), so it rolls as before.

Pools (data/equipment.json, built from the game files): the world's weapons and armor plus what merchants sell, all
obtainable in a normal game. The result goes to the client in the slot data; it rewrites the classes' rows of
CharaInitParam at the title screen, so the class selection shows the new gear.
"""

from __future__ import annotations

import json
import pkgutil
from random import Random

EQUIPMENT = json.loads(pkgutil.get_data(__name__, "data/equipment.json").decode("utf-8"))
MELEE = {0, 1, 2, 3, 4, 5, 6, 7, 9}
CATALYST, BOW, CROSSBOW, SHIELD = 8, 10, 11, 12
WEAPON_FIELDS = ("equip_Wep_Right", "equip_Subwep_Right", "equip_Wep_Left", "equip_Subwep_Left")
ARMOR_FIELDS = ("equip_Helm", "equip_Armer", "equip_Gaunt", "equip_Leg")  # slots 1-4
ARMOR_ALLOWANCE = 3.0
WEAPON_ALLOWANCE = 3.0


def usable(weapon: dict, stats: dict, no_requirements: bool) -> bool:
    if no_requirements:
        return True
    return (weapon["str"] <= stats["baseStr"] and weapon["dex"] <= stats["baseDex"]
            and weapon["mag"] <= stats["baseMag"] and weapon["fai"] <= stats["baseFai"])


def class_loadout(row: dict, random: Random, no_requirements: bool) -> dict[str, int]:
    """New values for one class's CharaInitParam fields."""
    weapons = EQUIPMENT["weapons"]
    out: dict[str, int] = {}
    taken: set[int] = set()
    for field in WEAPON_FIELDS:
        info = row.get(field + "_info")
        if not info or row[field] <= 0:
            continue
        category = info["category"]
        if category in MELEE:
            pool = [w for w in weapons.items() if w[1]["category"] in MELEE and w[1]["right"]]
        elif category == SHIELD:
            pool = [w for w in weapons.items() if w[1]["category"] == SHIELD and w[1]["left"]]
        elif category == BOW:
            pool = [w for w in weapons.items() if w[1]["category"] == BOW]
        else:
            continue  # catalysts, talismans, crossbows (bolts): as they are
        limit = max(info["weight"] + WEAPON_ALLOWANCE, 3.0)
        pool = [(int(i), w) for i, w in pool
                if usable(w, row, no_requirements) and w["weight"] <= limit and int(i) not in taken]
        if pool:
            chosen = random.choice(sorted(pool))[0]
            out[field] = chosen
            taken.add(chosen)
    budget = sum(row[f + "_weight"] for f in ARMOR_FIELDS) + ARMOR_ALLOWANCE
    pieces = {slot: sorted((int(i), a) for i, a in EQUIPMENT["armor"].items() if a["slot"] == slot)
              for slot in (1, 2, 3, 4)}
    lightest = {slot: min((a["weight"] for _i, a in pieces[slot]), default=0.0) for slot in pieces}
    slots = [1, 2, 3, 4]
    random.shuffle(slots)  # (no slot always gets the first pick of the budget)
    for n, slot in enumerate(slots):
        reserve = sum(lightest[s] for s in slots[n + 1:])
        fitting = [(i, a) for i, a in pieces[slot] if a["weight"] <= budget - reserve]
        if not fitting:
            continue
        item, armor = random.choice(fitting)
        out[ARMOR_FIELDS[slot - 1]] = item
        budget -= armor["weight"]
    return out


def starting_loadouts(random: Random, no_requirements: bool) -> dict[str, dict[str, int]]:
    """class row id -> field -> new item id, for the ten classes."""
    return {row_id: class_loadout(row, random, no_requirements)
            for row_id, row in sorted(EQUIPMENT["classes"].items())}


def describe(loadouts: dict[str, dict[str, int]]) -> dict[str, list[str]]:
    """Class name -> the names of its gear (the launcher's preview and the spoiler)."""
    weapon_names = {int(i): w["name"] for i, w in EQUIPMENT["weapons"].items()}
    armor_names = {int(i): a["name"] for i, a in EQUIPMENT["armor"].items()}  # (ids overlap with weapons')
    out = {}
    for row_id, fields in loadouts.items():
        row = EQUIPMENT["classes"][row_id]
        gear = []
        for field in WEAPON_FIELDS + ARMOR_FIELDS:
            item = fields.get(field, row[field])
            names = armor_names if field in ARMOR_FIELDS else weapon_names
            if item > 0 and item in names:
                gear.append(names[item])
        out[row["name"]] = gear
    return out
