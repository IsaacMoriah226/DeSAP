"""Build the Archipelago world's tables (apworld/demons_souls/data/items.json and locations.json).

Inputs:
  work\\locations.json             every item source in the game files (tools/build_locations.py)
  work\\research\\out\\*.json        the research: names, descriptions, requirements, missable flags, which
                                   sources are locations at all; tools/research_rules.py turns its
                                   requirement texts into logic and holds the owner's decisions

  python -I tools/build_world_data.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORLD = ROOT / "apworld" / "demons_souls"


def _load(name: str):
    """A module of the world package on its own (the package itself needs Archipelago to import)."""
    spec = importlib.util.spec_from_file_location(f"des_{name}", WORLD / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_ids, _parts = _load("ids"), _load("parts")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import research_rules as rules  # noqa: E402
from desap.gamedata import GameData  # noqa: E402

GAME = GameData()
ITEM_BASE, KINDS, LOCATION_BASE, LOCK_ITEM_OFFSET = _ids.ITEM_BASE, _ids.KINDS, _ids.LOCATION_BASE, _ids.LOCK_ITEM_OFFSET
LOCK_ITEMS, PARTS = _parts.LOCK_ITEMS, _parts.PARTS

WORK = Path(r"C:\Dev\DeSArchi\work")
OUT = WORLD / "data"

MAP_PART = {part.map: part.code for part in PARTS}
MAP_PART["m01_00_00_00"] = "Nexus"
for sub in ("00", "01", "02"):
    MAP_PART[f"m08_{sub}_00_00"] = "Tutorial"
PART_ABBREVIATION = {part.code: part.abbreviation for part in PARTS} | {"Nexus": "NX", "Tutorial": "TUT"}

KEY_GOODS = {6, 8, 9, 10, 11, 12, 13, 14, 35, 36, 37, 39, 40, 41, 42, 43, 44, 9931}  # 7 is a demon soul, 38 a trade item
BOSS_SOULS = {7} | set(range(15, 30))
DEMON_SOULS = BOSS_SOULS | set(range(30, 35))
USEFUL_GOODS = {1010, 1018, 1021, 1033}
AMMUNITION = range(160000, 170000)


def item_name(name: str, count: int) -> str:
    return name if count == 1 else f"{name} x{count}"


def classify(kind: str, game_id: int, logic_items: set[str], name: str) -> tuple[str, list[str]]:
    if kind == "weapon":
        if game_id in AMMUNITION:
            return "filler", ["Ammunition"]
        return "useful", ["Weapons"]
    if kind == "armor":
        return "useful", ["Armor"]
    if kind == "ring":
        return "useful", ["Rings"]
    if game_id in KEY_GOODS:
        return ("progression" if name in logic_items else "useful"), ["Keys"]
    if game_id in DEMON_SOULS:
        return "useful", ["Demon Souls"] + (["Boss Souls"] if game_id in BOSS_SOULS else [])
    if 2000 <= game_id < 2100:
        return "useful", ["Upgrade Stones"]
    if game_id in USEFUL_GOODS:
        return "useful", []
    if 1025 <= game_id <= 1032:
        return "filler", ["Souls"]
    return "filler", ["Consumables"]


def map_number(map_id: str) -> int:
    return int(map_id[1:3]) * 100 + int(map_id[4:6])


def raw_sources() -> list[dict]:
    """Every item source as a location candidate: one per treasure lot / event lot / shop row / enemy."""
    out = []
    for source in json.loads((WORK / "locations.json").read_text(encoding="utf-8")):
        kind = source["type"]
        if kind == "treasure":
            for slot, (lot, items) in enumerate(source["lots"].items()):
                if not items:
                    continue
                (it,) = items
                out.append({"key": ("treasure", source["map"], source["index"], int(lot)), "kind": kind,
                            "map": source["map"], "item": it, "flag": source["flag"],
                            "code": LOCATION_BASE + map_number(source["map"]) * 10_000 + source["index"] * 10 + slot,
                            "game": {"map": source["map"], "index": source["index"], "lot": int(lot),
                                     "flag": source["flag"], "part": source["part"]}})
        elif kind == "event":
            (it,) = source["items"]
            out.append({"key": ("event", source["map"], source["function"], source["lot"]), "kind": kind,
                        "map": source["map"], "item": it, "flag": source["flag"],
                        "code": LOCATION_BASE + 100_000_000 + map_number(source["map"]) * 100_000 + source["lot"],
                        "game": {"map": source["map"], "function": source["function"], "lot": source["lot"],
                                 "flag": source["flag"], "other_flags": source["other_flags"]}})
        elif kind == "enemy":
            (lot, items), = source["drops"].items()
            (it,) = items
            out.append({"key": ("enemy", source["map"], source["flag"]), "kind": kind, "map": source["map"],
                        "item": it, "flag": source["flag"], "code": LOCATION_BASE + 300_000_000 + source["flag"],
                        "game": {"map": source["map"], "flag": source["flag"], "entity": source["entity"],
                                 "lot": int(lot)}})
        elif kind == "shop":
            category = ("weapon", "armor", "ring", "goods")[source["category"]]
            it = {"category": category, "id": source["item_id"], "count": source["quantity"],
                  "name": source["item"]}
            out.append({"key": ("shop", source["shop_row"]), "kind": kind, "map": None, "item": it,
                        "flag": source["flag"], "code": LOCATION_BASE + 200_000_000 + source["shop_row"],
                        "game": {"shop_row": source["shop_row"], "flag": source["flag"], "price": source["price"]}})
    return out


def source_key(entry: dict) -> tuple:
    kind = entry["kind"]
    if kind == "treasure":
        return ("treasure", entry["map"], entry["index"], entry["lot"])
    if kind == "event":
        return ("event", entry["map"], entry["function"], entry["lot"])
    if kind == "enemy":
        return ("enemy", entry["map"], entry["flag"])
    return ("shop", entry["shop_row"])


def research() -> dict[tuple, dict]:
    """The research entries (work/research/out/<world>.json) by source key."""
    out: dict[tuple, dict] = {}
    for path in sorted((WORK / "research" / "out").glob("*.json")):
        for entry in json.loads(path.read_text(encoding="utf-8"))["locations"]:
            key = source_key(entry)
            if key in out:
                raise ValueError(f"research lists {key} twice")
            out[key] = entry
    return out


def added_sources(notes: dict[tuple, dict], known: set[tuple]) -> list[dict]:
    """Item sources the extractor missed and the research added (e.g. dragon kills: no event flag of their own)."""
    out = []
    for key, entry in notes.items():
        if key in known:
            continue
        if not entry.get("location", True):
            continue  # the research's note on something that is not a source (e.g. a commented-out item call)
        if not entry.get("added_not_in_input"):
            raise ValueError(f"research entry {key} matches no item source in the game data")
        if entry["kind"] != "event":
            raise ValueError(f"added research entry {key} is not an event")
        (it,) = GAME.lot_items(entry["lot"])
        out.append({"key": key, "kind": "event", "map": entry["map"], "flag": entry["flag"],
                    "item": {"category": it.category, "id": it.id, "count": it.count, "name": it.name},
                    "code": LOCATION_BASE + 100_000_000 + map_number(entry["map"]) * 100_000 + entry["lot"],
                    "game": {"map": entry["map"], "function": entry["function"], "lot": entry["lot"],
                             "flag": entry["flag"], "other_flags": []}})
    return out


def main() -> None:
    notes = research()
    sources = raw_sources()
    sources += added_sources(notes, {s["key"] for s in sources})
    base_names = {s["item"]["name"] for s in sources}
    abbreviation_part = {abbr: part for part, abbr in PART_ABBREVIATION.items()}

    locations, logic_items, dropped = [], set(), Counter()
    for source in sources:
        entry = notes.get(source["key"])
        if entry is None:
            raise ValueError(f"no research entry for {source['key']}")
        name = rules.RENAMES.get(entry["name"], entry["name"])
        if name in rules.NOT_LOCATIONS:
            dropped["kept vanilla (owner)"] += 1
            continue
        if not entry.get("location", True):
            dropped["not a location (research)"] += 1
            continue
        norm = rules.normalize(entry.get("requires", []), base_names)
        if norm.impossible:
            dropped["impossible on the emulator"] += 1
            continue
        # The part (region) is the area the location is in: the map's, or for shops the merchant's area code.
        part = abbreviation_part[name.split(":", 1)[0]] if source["kind"] == "shop" else MAP_PART[source["map"]]
        missable = entry.get("missable") or ""
        if norm.npc and not missable:
            missable = "depends on " + "; ".join(norm.npc)
        missable = rules.MISSABLE.get(name, missable)
        if part == "Tutorial" and not missable:
            missable = "tutorial: cannot be revisited"
        it = source["item"]
        location = {"name": name, "code": source["code"], "part": part, "kind": source["kind"],
                    "vanilla_item": item_name(it["name"], it["count"]), "description": entry.get("description", ""),
                    "requires": norm.tokens, "missable": missable, "tendency": entry.get("tendency") or "",
                    "game": source["game"], "_item": it}
        logic_items.update(t for t in norm.tokens if ":" not in t)
        locations.append(location)

    # Items: every vanilla item of a location, and the world locks.
    items: dict[str, dict] = {}
    for location in locations:
        it = location.pop("_item")
        kind = KINDS.index(it["category"])
        name = item_name(it["name"], it["count"])
        classification, groups = classify(it["category"], it["id"], logic_items, it["name"])
        entry = {"name": name, "code": ITEM_BASE + kind * 100_000_000 + it["id"] * 100 + it["count"],
                 "kind": it["category"], "game_id": it["id"], "count": it["count"],
                 "classification": classification, "groups": groups}
        if name in items and items[name]["code"] != entry["code"]:
            raise ValueError(f"two different items are both called {name!r}")
        items[name] = entry
    for n, name in enumerate(LOCK_ITEMS):
        items[name] = {"name": name, "code": ITEM_BASE + LOCK_ITEM_OFFSET + n, "kind": "archipelago", "game_id": 0,
                       "count": 1, "classification": "progression", "groups": ["World Locks"]}
    unknown = sorted(r for r in logic_items if r not in items)
    if unknown:
        raise ValueError(f"requirements name items no location holds: {unknown}")

    # Location groups, and each part's boss: an event (no id) whose requirements are those of its soul's
    # location, without the boss itself.
    for location in locations:
        groups = [location["part"]]
        groups.append({"treasure": "Treasures", "event": "Events", "shop": "Shops", "enemy": "Enemy Drops"}[location["kind"]])
        if location["missable"] or location["tendency"]:
            groups.append("Missable")
        if "Boss Souls" in items[location["vanilla_item"]]["groups"]:
            groups.append("Boss Rewards")
        location["groups"] = groups
    for part in PARTS:
        souls = [l for l in locations if l["part"] == part.code and "Boss Rewards" in l["groups"]]
        if len(souls) != 1:
            raise ValueError(f"{part.code}: expected one boss soul location, found {[l['name'] for l in souls]}")
        requires = [t for t in souls[0]["requires"] if t != f"boss:{part.code}"]
        locations.append({"name": f"{part.code} boss: {part.boss}", "code": None, "part": part.code,
                          "kind": "boss_event", "vanilla_item": "", "requires": requires, "game": {}})

    names = Counter(l["name"] for l in locations)
    duplicated = [n for n, c in names.items() if c > 1]
    if duplicated:
        raise ValueError(f"duplicate location names: {duplicated}")
    codes = Counter(l["code"] for l in locations if l["code"] is not None)
    if any(c > 1 for c in codes.values()):
        raise ValueError(f"duplicate location codes: {[c for c, n in codes.items() if n > 1]}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "items.json").write_text(json.dumps(sorted(items.values(), key=lambda i: i["code"]), indent=1,
                                               ensure_ascii=False), encoding="utf-8")
    (OUT / "locations.json").write_text(json.dumps(locations, indent=1, ensure_ascii=False), encoding="utf-8")
    real = [l for l in locations if l["code"] is not None]
    print(f"{len(real)} locations ({dict(Counter(l['kind'] for l in real))}), "
          f"{sum(1 for l in real if l['missable'] or l['tendency'])} missable; dropped {dict(dropped)}")
    print(f"{len(items)} items ({dict(Counter(i['classification'] for i in items.values()))}); progression keys: "
          f"{sorted(n for n, i in items.items() if i['classification'] == 'progression' and 'Keys' in i['groups'])}")


if __name__ == "__main__":
    main()
