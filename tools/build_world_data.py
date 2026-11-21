"""Build the Archipelago world's tables (apworld/demons_souls/data/items.json and locations.json).

Inputs:
  work\\locations.json             every item source in the game files (tools/build_locations.py)
  work\\research\\final\\*.json      the reviewed research: names, descriptions, requirements, missable flags,
                                   which sources are locations at all (optional while research is running:
                                   without it, names are placeholders)

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
ITEM_BASE, KINDS, LOCATION_BASE, LOCK_ITEM_OFFSET = _ids.ITEM_BASE, _ids.KINDS, _ids.LOCATION_BASE, _ids.LOCK_ITEM_OFFSET
LOCK_ITEMS, PARTS = _parts.LOCK_ITEMS, _parts.PARTS

WORK = Path(r"C:\Dev\DeSArchi\work")
OUT = WORLD / "data"

MAP_PART = {part.map: part.code for part in PARTS}
MAP_PART["m01_00_00_00"] = "Nexus"
for sub in ("00", "01", "02"):
    MAP_PART[f"m08_{sub}_00_00"] = "Tutorial"
PART_ABBREVIATION = {part.code: part.abbreviation for part in PARTS} | {"Nexus": "NX", "Tutorial": "TUT"}

KEY_GOODS = set(range(6, 15)) | set(range(35, 45)) | {9931}
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


def research() -> dict[tuple, dict]:
    """Reviewed research entries by source key (empty while research is running)."""
    out: dict[tuple, dict] = {}
    for path in sorted((WORK / "research" / "final").glob("*.json")):
        for entry in json.loads(path.read_text(encoding="utf-8"))["locations"]:
            kind = entry["kind"]
            if kind == "treasure":
                key = ("treasure", entry["map"], entry["index"], entry["lot"])
            elif kind == "event":
                key = ("event", entry["map"], entry["function"], entry["lot"])
            elif kind == "enemy":
                key = ("enemy", entry["map"], entry["flag"])
            else:
                key = ("shop", entry["shop_row"])
            if key in out:
                raise ValueError(f"research lists {key} twice")
            out[key] = entry
    return out


def main() -> None:
    sources = raw_sources()
    notes = research()
    locations, logic_items = [], set()
    for source in sources:
        entry = notes.get(source["key"])
        # Shops have no map in the data; the research says where each merchant is (placeholder: the Nexus).
        part = MAP_PART.get(source["map"], "Nexus") if source["map"] else "Nexus"
        if entry is not None:
            if not entry.get("location", True):
                continue
            part = entry.get("part", part)
            name, description = entry["name"], entry.get("description", "")
            requires, missable, tendency = entry.get("requires", []), entry.get("missable") or "", entry.get("tendency") or ""
        else:
            if notes:
                raise ValueError(f"no research entry for {source['key']}")
            prefix = "SHOP" if source["kind"] == "shop" else PART_ABBREVIATION[part]
            name = f"{prefix}: {source['item']['name']} - {source['kind']} {'/'.join(map(str, source['key'][1:]))}"
            description, requires, missable, tendency = "", [], "", ""
            if any(l["code"] == source["code"] for l in locations):
                continue  # placeholder mode: the same lot given by two events of a map (NPC events, dropped later)
        it = source["item"]
        location = {"name": name, "code": source["code"], "part": part, "kind": source["kind"],
                    "vanilla_item": item_name(it["name"], it["count"]), "description": description,
                    "requires": requires, "missable": missable, "tendency": tendency, "game": source["game"],
                    "_item": it}
        logic_items.update(r for r in requires if not r.startswith("boss:"))
        locations.append(location)

    # Items: every vanilla item of a location, the world locks, the filler fallback.
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

    # Location groups and the bosses (events marking a part's boss dead; its requirements are its soul's).
    for location in locations:
        groups = [location["part"]] if location["part"] else []
        groups.append({"treasure": "Treasures", "event": "Events", "shop": "Shops", "enemy": "Enemy Drops"}[location["kind"]])
        if location["missable"] or location["tendency"]:
            groups.append("Missable")
        if location["vanilla_item"] in items and "Boss Souls" in items[location["vanilla_item"]]["groups"]:
            groups.append("Boss Rewards")
        location["groups"] = groups
    for part in PARTS:
        souls = [l for l in locations if l["part"] == part.code and "Boss Rewards" in l["groups"]]
        requires = sorted({r for l in souls for r in l["requires"]})
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
    print(f"{len(real)} locations ({Counter(l['kind'] for l in real)}), "
          f"{sum(1 for l in real if l['missable'] or l['tendency'])} missable; {len(items)} items "
          f"({Counter(i['classification'] for i in items.values())}); research entries: {len(notes)}")


if __name__ == "__main__":
    main()
