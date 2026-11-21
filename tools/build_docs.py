"""Write the player's location guide (apworld/demons_souls/docs/locations_en.md) from the world's final data and the
research's sub-area glossaries (with tools/research_rules.py's corrections). Run after build_world_data.py.

  python -I tools/build_docs.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import research_rules as rules  # noqa: E402

WORLD = ROOT / "apworld" / "demons_souls"
sys.path.insert(0, str(ROOT))
from desap import local  # noqa: E402

RESEARCH = local.path("work") / "research" / "out"

AREAS = [  # (code, number, area, maps)
    ("NX", "", "The Nexus", ["m01_00_00_00"]),
    ("TUT", "", "Tutorial (Boletarian Palace)", ["m08_00_00_00", "m08_01_00_00", "m08_02_00_00"]),
    ("GB", "1-1", "Gates of Boletaria", ["m02_00_00_00"]),
    ("LP", "1-2", "The Lord's Path", ["m02_01_00_00"]),
    ("IW", "1-3", "Inner Ward", ["m02_02_00_00"]),
    ("KT", "1-4", "The King's Tower", ["m02_03_00_00"]),
    ("SG", "2-1", "Smithing Grounds", ["m06_00_00_00"]),
    ("TC", "2-2", "The Tunnel City", ["m06_01_00_00"]),
    ("UT", "2-3", "Underground Temple", ["m06_02_00_00"]),
    ("PH", "3-1", "Prison of Hope", ["m04_00_00_00"]),
    ("UL", "3-2", "Upper Latria", ["m04_01_00_00"]),
    ("IT", "3-3", "The Ivory Tower", ["m04_02_00_00"]),
    ("IE", "4-1", "Island's Edge", ["m03_01_00_00"]),
    ("RP", "4-2", "The Ritual Path", ["m03_02_00_00"]),
    ("AS", "4-3", "Altar of Storms", ["m03_03_00_00"]),
    ("DC", "5-1", "Depraved Chasm", ["m05_00_00_00"]),
    ("SS", "5-2", "Swamp of Sorrow", ["m05_01_00_00"]),
    ("RH", "5-3", "Rotting Haven", ["m05_02_00_00"]),
]
BOSSES = {part: boss for boss, part in rules.BOSS_PARTS.items()}
AREA_OF = {number: area for _code, number, area, _maps in AREAS if number}

INTRO = """# Demon's Souls Remake: locations

Every location is named `<area code> <world number>: <original item> - <where>`, for example
`GB 1-1: Mail Breaker - first fog, corridor end`: the code and number of the area the item is in, the item it holds
in the unrandomized game, and a short description of the spot. Descriptions use made-up names for parts of each
area; this guide defines them, area by area, and lists every location with what it needs.

| Code | Area | | Code | Area | | Code | Area |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NX | The Nexus | | SG 2-1 | Smithing Grounds | | IE 4-1 | Island's Edge |
| TUT | Tutorial | | TC 2-2 | The Tunnel City | | RP 4-2 | The Ritual Path |
| GB 1-1 | Gates of Boletaria | | UT 2-3 | Underground Temple | | AS 4-3 | Altar of Storms |
| LP 1-2 | The Lord's Path | | PH 3-1 | Prison of Hope | | DC 5-1 | Depraved Chasm |
| IW 1-3 | Inner Ward | | UL 3-2 | Upper Latria | | SS 5-2 | Swamp of Sorrow |
| KT 1-4 | The King's Tower | | IT 3-3 | The Ivory Tower | | RH 5-3 | Rotting Haven |

## Getting into each part

1-1 is open from the start. Every other part needs its item (`1-2 The Lord's Path`, ..., `5-3 Rotting Haven`),
and also what the vanilla game needs to open its archstone:

- 2-1, 3-1, 4-1 and 5-1: Phalanx dead (the Monumental unseals the other archstones after the first boss).
- x-2 and x-3 (and 1-4): the previous part's boss dead (its archstone appears when you take its soul).
- 1-3 and 1-4: also the archdemon of another world dead and its soul taken (Dragon God, Old Monk, Storm King or
  Maiden Astraea): the gate past the Tower Knight stays sealed until then.

The client keeps you out of a part you cannot enter yet: it cannot be warped to, and walking into it sends you back
to the Nexus. The goal is the credits: kill all five archdemons (Old King Allant, Dragon God, Old Monk, Storm King,
Maiden Astraea), talk to the Maiden in Black and defeat False King Allant below the Nexus.

## Missable locations

Locations marked *missable* can be lost or only exist under conditions the logic cannot see (a world tendency,
an NPC who must stay alive or be helped, the tutorial, which cannot be revisited). They only ever hold filler, so
missing them never costs you or anyone else anything important.
"""


def need_text(token: str) -> str:
    if token.startswith("any:"):
        return " or ".join(need_text(t) for t in token[4:].split("|"))
    if token.startswith("boss:"):
        return f"{BOSSES[token[5:]]} dead"
    if token.startswith("region:"):
        part = token[7:]
        return f"access to {part} {AREA_OF[part]}"
    if token.startswith("archdemons:"):
        n = int(token[11:])
        return "all five archdemons dead" if n == 5 else f"{n} archdemons dead"
    return token


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def main() -> None:
    locations = [l for l in json.loads((WORLD / "data" / "locations.json").read_text(encoding="utf-8")) if l["code"]]
    glossaries: dict[str, dict[str, str]] = {}
    for path in sorted(RESEARCH.glob("*.json")):
        for map_id, region in json.loads(path.read_text(encoding="utf-8")).get("regions", {}).items():
            glossaries[map_id] = dict(region.get("glossary", {}))
    for map_id, fixes in rules.GLOSSARY_FIXES.items():
        for term, text in fixes.items():
            if text is None:
                glossaries[map_id].pop(term, None)
            else:
                glossaries[map_id][term] = text

    out = [INTRO]
    listed = 0
    for code, number, area, maps in AREAS:
        prefix = f"{code} {number}" if number else code
        here = [l for l in locations if l["name"].split(":", 1)[0] == prefix]
        listed += len(here)
        out.append(f"## {prefix}: {area}\n")
        terms = {}
        for map_id in maps:
            terms.update(glossaries.get(map_id, {}))
        if terms:
            out.append("Terms used in this area's names:\n")
            out += [f"- **{term}**: {cell(text)}" for term, text in terms.items()]
            out.append("")
        out.append("| Location | Where | Needs | |\n| --- | --- | --- | --- |")
        for l in here:
            needs = ", ".join(need_text(t) for t in l["requires"]) or "-"
            flag = ""
            if l["tendency"]:
                flag = f"*missable: world tendency {cell(l['tendency'])}*"
            elif l["missable"]:
                flag = f"*missable: {cell(l['missable'])}*"
            out.append(f"| {cell(l['name'])} | {cell(l['description'])} | {cell(needs)} | {flag} |")
        out.append("")
    if listed != len(locations):
        raise ValueError(f"the guide lists {listed} of {len(locations)} locations")
    path = WORLD / "docs" / "locations_en.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"{path}: {len(locations)} locations")


if __name__ == "__main__":
    main()
