"""How the research's requirement texts become logic, plus the owner's decisions on top of the research.

The research (work/research/out/*.json, one file per world) writes each location's requirements as text: an item
name, "<boss> defeated", or a description of a lever, an NPC's state, etc. `normalize` turns every such text into
logic tokens for the world:

    <item name>        the item (a key that is itself a location's vanilla item, so it is in the pool)
    boss:<part>        that part's boss dead
    region:<part>      that part reachable (used for keys that stay vanilla: they are found there)
    archdemons:<n>     at least n of the five archdemons dead
    any:<a>|<b>        either token

and reports whether the text is an NPC's state, which makes the location missable (logic cannot see whether an
NPC lives or was rescued). A text this file does not know is an error: every requirement is decided here.
"""

from __future__ import annotations

import re

BOSS_PARTS = {
    "Phalanx": "1-1", "Tower Knight": "1-2", "Penetrator": "1-3", "Old King Allant": "1-4",
    "Armor Spider": "2-1", "Flamelurker": "2-2", "Dragon God": "2-3",
    "Fool's Idol": "3-1", "Maneater": "3-2", "Old Monk": "3-3",
    "Adjudicator": "4-1", "Old Hero": "4-2", "Storm King": "4-3",
    "Leechmonger": "5-1", "Dirty Colossus": "5-2", "Maiden Astraea": "5-3",
}

# Keys whose sources stay vanilla (unique enemy drops, NPC gifts): the logic needs where they are found instead.
# (None now: the Iron Key Ring and Bloody Iron Key are Fat Official drops, which are locations since 2026-11-20.)
VANILLA_KEYS: dict[str, list[str]] = {}
# Vanilla keys that come from an NPC's quest: the locations they open are missable.
NPC_KEYS = {"Mausoleum Key"}

# Things the player can always do once in the area (levers, wheels, elevators, walls, drops, ...): no logic.
FREE_ACTIONS = (
    "lever pulled", "magma wheel turned", "rotating elevator started", "both chains broken",
    "break an illusory wall", "break the illusory wall", "break the two chains", "drop into Patches' pit",
    "first ballista fired", "knock down the hanging slug colony", "ranged attacks (bow or spells)",
    "Old King Doran brought below 80% HP", "talk to the Maiden in Black",
)
# NPC states: the location is missable.
NPC_STATES = (
    "Biorr of the Twin Fangs 'is gone'", "Blige alive and not hostile", "Dregling Merchant alive",
    "Filthy Woman alive", "Patches alive", "Rydell freed and talked to", "Yurt, the Silent Chief rescued",
    "she is alive and not hostile",
)
# Not trackable by logic and not under the player's direct control: missable.
UNTRACKABLE = ("different Depraved Ones fallen to their death",)
# Impossible on the emulator: not a location at all.
IMPOSSIBLE = ("online mode:",)

ARCHDEMON_COUNT = {"two": 2, "three": 3, "four": 4, "all five": 5}


class Normalized:
    def __init__(self) -> None:
        self.tokens: list[str] = []
        self.npc: list[str] = []  # NPC states / untrackable conditions (location missable)
        self.impossible: list[str] = []


def normalize(texts: list[str], item_names: set[str]) -> Normalized:
    out = Normalized()
    for text in texts:
        out_tokens = _normalize_one(text, item_names, out)
        for token in out_tokens:
            if token not in out.tokens:
                out.tokens.append(token)
    return out


def _normalize_one(text: str, item_names: set[str], out: Normalized) -> list[str]:
    if text in VANILLA_KEYS:
        return VANILLA_KEYS[text]
    if text in NPC_KEYS:
        out.npc.append(f"needs the {text}, an NPC quest item that stays vanilla")
        return []
    if text in item_names:
        return [text]
    if any(text.startswith(p) for p in IMPOSSIBLE):
        out.impossible.append(text)
        return []
    if any(p in text for p in UNTRACKABLE):
        out.npc.append(text)
        return []
    match = re.match(r"(two|three|four|all five) archdemons killed", text)
    if match:
        return [f"archdemons:{ARCHDEMON_COUNT[match.group(1)]}"]
    if text.startswith("Patches in the Nexus: finish his trap event"):
        out.npc.append("Patches must have moved to the Nexus (his trap in The Tunnel City or The Ritual Path)")
        return ["any:region:2-2|region:4-2"]
    if text.startswith("Blige freed from his cell"):
        out.npc.append("Blige must be freed and stay friendly")
        return ["Copper Key"]
    if text.startswith("Tower Knight killed, the gate past Tower Knight unsealed"):
        out.npc.append("the Dregling Merchant moves to the Inner Ward and must stay alive")
        return ["boss:1-2", "region:1-3"]
    if text.startswith("Phalanx killed (he moves") or text.startswith("Leechmonger killed (she moves"):
        boss = text.split(" killed", 1)[0]
        out.npc.append(f"a merchant moves after {boss} dies and must stay alive")
        return [f"boss:{BOSS_PARTS[boss]}"]
    if text.startswith("reach her room on the 4th floor"):
        return ["Prison of Hope, 4F Key"]
    if text.startswith("Vanguard (tutorial boss) killed"):
        out.npc.append("only if you beat the tutorial Vanguard")
        return []
    if text.startswith("False King Allant killed"):
        return ["archdemons:5"]
    if any(p in text for p in NPC_STATES):
        out.npc.append(text)
        return []
    if any(p in text for p in FREE_ACTIONS):
        return []
    match = re.match(r"(.+?) (defeated|killed)\b", text)
    if match and match.group(1) in BOSS_PARTS:
        return [f"boss:{BOSS_PARTS[match.group(1)]}"]
    raise ValueError(f"unknown requirement text: {text!r}")


# --- the owner's decisions on top of the research (keyed by the research's location name) -------------------

NOT_LOCATIONS = {
    # Keep vanilla: the item that returns you to the Nexus, and the icon of other players' items in the game.
    "NX: Nexial Binding - first arrival": "kept vanilla: the return-to-Nexus item",
}
MISSABLE = {
    # Only below the Nexus at the very end, after the final boss; lost when an ending is chosen.
    "NX: Soulbrandt - final boss drop": "only after the final boss, lost when an ending starts",
}
# Name fixes (research name -> final name).
RENAMES = {
    # "CMG" was the researcher's shorthand for the Crescent Moon Grass x11 corpse 15 m away.
    "SS: Dark Moon Grass - north islands, by big CMG": "SS: Dark Moon Grass - north islands, platform",
}

# Corrections from the independent review (work/research/review/<world>.json), keyed by the research's name.
# Fields: name, description, add_requires / requires (requirement texts, normalized like the research's),
# tokens (logic tokens added as they are), missable.
OVERRIDES: dict[str, dict] = {
    # --- valley ---
    # The plague swamp is the boss arena (light wall o5985 is the boss fog; boss regions 2893/2897 right behind).
    "RH: Stone of Ephemeral Eyes - plague swamp edge": {"add_requires": ["Maiden Astraea defeated"]},
    "RH: Pure Marrowstone - plague swamp, grass patch": {"add_requires": ["Maiden Astraea defeated"]},
    "RH: Pure Suckerstone - ledge above plague swamp": {"add_requires": ["Maiden Astraea defeated"]},
    "RH: Pure Mercurystone - plague swamp": {"add_requires": ["Maiden Astraea defeated"]},
    "RH: Legendary Hero Soul - plague swamp pier": {"add_requires": ["Maiden Astraea defeated"]},
    # The fog wall's rotation puts the corpse just past the first fog gate, not before it.
    "DC: Noble's Lotus - first fog gate": {
        "name": "DC: Noble's Lotus - past first fog gate",
        "description": "Just through the first fog gate (the one by the four Depraved Ones), at the top of the way "
                       "down to the brush ledge."},
    # On the lone Shaman's platform 7 m below the boardwalk.
    "SS: Unknown Hero Soul - west boardwalk, by shaman": {
        "name": "SS: Unknown Hero Soul - lone shaman platform",
        "description": "On the low platform of the lone Shaman, below the start of the west boardwalk north of the "
                       "shanty town (drop down from the boardwalk)."},
    # --- boletaria ---
    # On the archer walls inside the Tower Knight arena, reached by the arena's own stairs.
    "LP: Renowned Warrior Soul - boss arena ramparts": {
        "add_requires": ["Tower Knight defeated"],
        "description": "On the walls of the boss arena, up the arena's side stairs, by the crossbow soldier at the "
                       "far (exit) end."},
    # Treasures 13 and 16 had each other's descriptions (positions, enemies and floor heights in the map data).
    "GB: Unknown Warrior Soul - Ostrava's route, corner": {
        "name": "GB: Unknown Warrior Soul - long corridor end",
        "description": "Back in the building past Ostrava's pit, at the left end of the long corridor, before the "
                       "gate guarded by an axe soldier."},
    "GB: Unknown Hero Soul - long corridor end": {
        "name": "GB: Unknown Hero Soul - Ostrava's route, corner",
        "description": "Following Ostrava right from the Blue Eye Knight's building, in the little corner guarded by "
                       "a melee Dregling and a crossbow soldier, beside the little staircase down to the barrel room."},
    # The cell doors sit side by side on one wall.
    "LP: Renowned Hero Soul - prison, cell opposite Biorr": {
        "name": "LP: Renowned Hero Soul - prison, cell next to Biorr",
        "description": "In the prison, the locked cell right beside Biorr's (the first cell you open)."},
    "LP: Storied Hero Soul - prison, far cell": {
        "description": "In the prison, the second cell on the side wall, past the empty one next to Biorr's corner."},
    "IW: Full Moon Grass - alleys, below ledge": {"name": "IW: Full Moon Grass - alleys, drop to ledge"},
    # --- stonefang ---
    # Behind the boss elevator by its upper call handle (wikidot walk2-1 point 20), not below the Kris Blade walkway.
    "SG: Spiderstone Shard - boss elevator top": {
        "name": "SG: Spiderstone Shard - behind boss elevator top",
        "description": "Corpse behind the big boss elevator at its top, next to the upper call handle, before you "
                       "ride down (the Kris Blade walkway is on the other side of the lift)."},
    # 39 m from the lever: by the two miners just over the wooden bridge.
    "SG: Ed's Sharpening Stone - lever gallery, behind rubble": {
        "description": "Corpse behind breakable rubble by the two miners just over the wooden bridge in the lever "
                       "gallery, before the corridor that leads to the gate lever."},
    # The worm cliff is outside the fog into the bug tunnels.
    "TC: Storied Warrior Soul - bug tunnels, worm cliff": {
        "name": "TC: Storied Warrior Soul - worm cliff, ore carts",
        "description": "Corpse among the ore carts on the open ledge at the bottom of the rift path, just before the "
                       "fog into the bug tunnels."},
    "TC: Storied Warrior Soul - bug tunnels, side branch": {
        "description": "Corpse down the right-hand branch at the first junction just inside the fog into the bug "
                       "tunnels (the left branch when coming from the pit bottom)."},
    # The ring is on the upper ledge; the Giant Bearbug lands below it.
    "TC: Flame Resistance Ring - bearbug ledge": {
        "description": "Glowing item at the bottom of the stairs down from the rift platforms, on the ledge above "
                       "the Club (Patches runs here to grab it if his trap springs)."},
    # Enemies are not landmarks (naming guide).
    "TC: Dragonstone Shard - bearbug den, past giant bearbug": {"name": "TC: Dragonstone Shard - bearbug den, right corner"},
    "TC: Clearstone Chunk - bug tunnels, behind bearbug": {"name": "TC: Clearstone Chunk - bug tunnels, right branch"},
    "TC: Hardstone Chunk - rift path, past three worms": {"name": "TC: Hardstone Chunk - rift path junction"},
    "TC: Greystone Shard - bearbug ledge, rock worm": {"name": "TC: Greystone Shard - bearbug ledge, right side"},
    "SG: Unknown Hero Soul - archstone ledge, past lizard": {"name": "SG: Unknown Hero Soul - archstone ledge, broken cart"},
    # --- shrine ---
    # The Vanguard's courtyard is level with the first fog gate (not sunken); the second fog gate is on its far side.
    "IE: Kilij - pit courtyard": {
        "description": "Corpse in the Vanguard's courtyard straight through the first fog gate, to the right near "
                       "the well."},
    "IE: Full Moon Grass - pit courtyard": {
        "description": "Corpse in the far left corner by the rubble of the Vanguard's courtyard, straight through "
                       "the first fog gate."},
    "IE: Storied Hero Soul - pit courtyard": {
        "description": "Corpse further into the Vanguard's courtyard (straight through the first fog gate), on the "
                       "right, near the miniboss."},
    "IE: Uchigatana - before second fog gate": {
        "description": "Corpse by the second fog gate on the far side of the Vanguard's courtyard, to the right of "
                       "the gate."},
    # Two illusory walls lead into the cell tunnels, and both come back on every load: nothing is required.
    "IE: Crescent Moon Grass - cell tunnels": {"requires": []},
    "IE: Renowned Hero Soul - Blige's cell": {"requires": ["Copper Key"]},
    "IE: Augite of Guidance - crow's cliff": {
        "description": "Corpse on the path up the cliff toward Sparkly the Crow, through the other door of the east "
                       "tower (past the archer walkway, not the key tower)."},
    "IE: Gray Demon Soul - pit courtyard miniboss": {
        "name": "IE: Gray Demon Soul - pit courtyard, miniboss drop",
        "description": "Dropped by the optional Vanguard in the courtyard straight through the first fog gate."},
    "RP: Colorless Demon Soul - secret cliff, black tendency": {"name": "RP: Colorless Demon Soul - secret cliff, miniboss drop"},
    "RP: Storied Warrior Soul - stairs to slug cavern": {
        "description": "Corpse midway down the left-hand stairs past the third Reaper (beyond the second fog gate), "
                       "on the way down to the slug cavern."},
    "RP: Kunai - across bridge": {
        "name": "RP: Kunai - casket hall upper walkway",
        "description": "Corpse on the upper walkway of the casket (first Reaper) hall, to the left as you come in "
                       "from the tunnel."},
    "RP: Sticky White Slime - slug cavern, first slugs": {
        "name": "RP: Sticky White Slime - slug cavern, below sarcophagus",
        "description": "Corpse on the cavern floor a few metres from the sarcophagus, on the opposite side from the "
                       "Moonshadestone Chunk column."},
    "RP: Full Moon Grass - boss arena": {
        "description": "Corpse on the left side of the Old Hero's battlefield (as you come in from the fog gate)."},
    # The game has no compass: left/right as seen on the way in.
    "RP: Unknown Warrior Soul - west stairs, midway": {"name": "RP: Unknown Warrior Soul - left stairs, midway"},
    "RP: Stone of Ephemeral Eyes - top of west stairs, trap": {"name": "RP: Stone of Ephemeral Eyes - top of left stairs, trap"},
    # --- nexus / shops ---
    # Biorr's cell needs the Iron Key Ring; he leaves only after Penetrator and the King's Tower dragon or Allant.
    **{f"IW: {item} - Dregling Merchant after Biorr leaves": {"tokens": ["region:1-3", "boss:1-3", "region:1-4"]}
       for item in ("Brushwood Helm", "Brushwood Armor", "Brushwood Gauntlets", "Brushwood Greaves",
                    "Large Brushwood Shield")},
    # Yurt is freed in Upper Latria (3-2), not the Prison of Hope.
    "NX: Renowned Warrior Soul - outer stairs, after rescuing Yurt": {"tokens": ["region:3-2"]},
    "NX: Storied Warrior Soul - second floor, after rescuing Yurt": {"tokens": ["region:3-2"]},
    # --- latria ---
    # Kept as locations (missable, filler only) against the reviewer's suggestion: they are corpse pickups that
    # appear after Rydell's quest step; logic treats them as NPC-dependent.
    # Cell numbering from the map's door positions (review): the third inner-row cell from the plate end.
    "PH: Renowned Hero Soul - 2F east, inner cell": {
        "name": "PH: Renowned Hero Soul - 2F east, middle inner cell",
        "description": "Corpse in the third inner-row cell from the plate end of 2F East, the locked one nearest the "
                       "middle of the block (2F E. Cell Key door)."},
    "PH: Mercurystone Chunk - 2F east, inner cell": {
        "name": "PH: Mercurystone Chunk - 2F east, middle inner cell",
        "description": "Corpse at the back of the third inner-row cell from the plate end of 2F East (2F E. Cell "
                       "Key door)."},
    # The Venerable Sage set and the Three-Cornered Hat are in different locked cells.
    **{f"PH: Venerable Sage's {piece} - 2F west inner row, locked cell": {
        "name": f"PH: Venerable Sage's {piece} - 2F west inner row, stair-end locked cell", "description": 'Corpse in the second inner-row cell from the stair end of 2F West, the locked one nearest the stairs, beyond the rubble, behind a 2F W. Cell Key door.'}
       for piece in ("Hood", "Robe", "Gloves", "Boots")},
    "PH: Three-Cornered Hat - 2F west inner row, locked cell": {
        "name": "PH: Three-Cornered Hat - 2F west inner row, middle locked cell",
        "description": "Corpse in the third inner-row cell from the plate end of 2F West, beyond the rubble, behind "
                       "a 2F W. Cell Key door."},
    "PH: Mercurystone Shard - 3F east, stair-end inner cell": {
        "name": "PH: Mercurystone Shard - 3F east, inner cell near stair end",
        "description": "Corpse in the second inner-row cell from the stair end of 3F East (open door)."},
    # Numbered in walking order (index 61 comes first on the way).
    "PH: Renowned Warrior Soul - ballista bridge bodies 1": {"name": "PH: Renowned Warrior Soul - ballista bridge bodies 2"},
    "PH: Renowned Warrior Soul - ballista bridge bodies 2": {"name": "PH: Renowned Warrior Soul - ballista bridge bodies 1"},
    # --- one-time enemies ---
    # Their bodies are not saved: the drop is lost if not picked up before the area reloads.
    **{name: {"missable": "the drop is lost if not picked up before the area reloads"} for name in (
        'KT: Tower Shield - phantom hall, phantom drop',
        'KT: White Bow - phantom hall, phantom drop',
        'KT: Penetrating Sword - phantom hall, phantom drop',
        'KT: Rune Sword - long walkway, phantom drop',
        'KT: Rune Shield - long walkway, phantom drop',
        'RP: Moonshadestone Chunk - pit, phantom drop',
        'RP: Stone of Ephemeral Eyes - pit, phantom drop',
        'PH: Moonlightstone Chunk - below catwalk ledge, phantom drop',
        'PH: Stone of Ephemeral Eyes - below catwalk ledge, phantom drop',
        'SS: Faintstone Chunk - northeast island, phantom drop',
        'SS: Stone of Ephemeral Eyes - northeast island, phantom drop',
        'TC: Dragonstone Chunk - lizard nest, first phantom drop',
        'TC: Stone of Ephemeral Eyes - lizard nest, first phantom drop',
        'TC: Clearstone Chunk - lizard nest, second phantom drop',
        'TC: Stone of Ephemeral Eyes - lizard nest, second phantom drop',
    )},
    # The lone Shaman stands on the low platform below the west boardwalk (valley review).
    **{f"SS: {piece} - west boardwalk, miniboss drop": {"name": f"SS: {piece} - lone shaman platform, mob drop"}
       for piece in ("Shaman's Garb", "Shaman's Armbands", "Shaman's Tabi")},
    # --- one-time enemies: review (work/research/review/unique_enemies.json) ---
    **{f"GB: {piece} - mausoleum, miniboss drop": {"description": 'Old King Doran in the Mausoleum (door behind the Red Eye Knight, needs the Mausoleum Key). Below 80% HP he lets you take Demonbrandt; below 60% he fights again. Killing him does not lose the sword. His body stays until looted.'}
       for piece in ("Eternal Warrior's Ring", "Ancient King's Mask", "Ancient King's Breastplate",
                     "Ancient King's Gauntlets", "Ancient King's Greaves")},
    **{f"GB: {piece} - execution grounds stairwell, miniboss drop": {"description": 'Executioner Miralda, alive at the top of the pit steps (right side) by the execution grounds stairwell; only at pure white world tendency. Her body stays until looted.'}
       for piece in ("Binded Hood", "Binded Cross", "Binded Gloves", "Binded Boots", "Master's Ring")},
    "IW: Official's Cap - by gate lever, miniboss drop": {
        "description": "The Fat Official who shut the gate in the opening cutscene, waiting at the bottom of the "
                       "stairs below the Iron Key Ring yard, next to the lever that reopens that gate. His body "
                       "stays until looted."},
    # Sack miners placed against the map and the wiki by the review.
    **{name: {"description": "The sack-carrying miner among the six miners in the second room of the miners' path "
                             "(the room whose far end has the dog jars), before the ore room. His body stays until "
                             "looted."}
       for name in ("SG: Hardstone Shard - miners' path, mob drop 1", "SG: Hardstone Shard - miners' path, mob drop 2",
                    "SG: Sharpstone Shard - miners' path, mob drop 1", "SG: Sharpstone Shard - miners' path, mob drop 2")},
    **{old: {"name": new, "description": "The sack-carrying miner in the last group of three miners, right beside "
                                         "the gate lever in the lever gallery. His body stays until looted."}
       for old, new in (("SG: Clearstone Shard - lever gallery, mob drop 1", "SG: Clearstone Shard - by gate lever, mob drop 1"),
                        ("SG: Clearstone Shard - lever gallery, mob drop 2", "SG: Clearstone Shard - by gate lever, mob drop 2"),
                        ("SG: Clearstone Chunk - lever gallery, mob drop", "SG: Clearstone Chunk - by gate lever, mob drop"))},
    **{old: {"name": new, "description": "The sack-carrying miner in the first group of three miners in the corridor "
                                         "leading to the gate lever (the second group stands at the lever)."}
       for old, new in (("SG: Hardstone Shard - lever gallery, mob drop 1", "SG: Hardstone Shard - lever corridor, first trio, mob drop 1"),
                        ("SG: Hardstone Shard - lever gallery, mob drop 2", "SG: Hardstone Shard - lever corridor, first trio, mob drop 2"),
                        ("SG: Large Hardstone Shard - lever gallery, mob drop", "SG: Large Hardstone Shard - lever corridor, first trio, mob drop"))},
    **{old: {"name": new, "description": "The sack-carrying miner at the end of the lever gallery's east corridor, "
                                         "across the little stone bridge, standing above the ore room."}
       for old, new in (("SG: Sharpstone Shard - lever gallery, mob drop 1", "SG: Sharpstone Shard - above ore room, mob drop 1"),
                        ("SG: Sharpstone Shard - lever gallery, mob drop 2", "SG: Sharpstone Shard - above ore room, mob drop 2"),
                        ("SG: Large Sharpstone Shard - lever gallery, mob drop", "SG: Large Sharpstone Shard - above ore room, mob drop"))},
    # Whether these lots' one-time flags are set on the kill or on the pickup is unverified: if on the kill, an
    # unlooted drop is lost.
    "SG: Official's Gloves - Fat Official platform, miniboss drop": {"missable": "the one-time drop may be lost if not looted"},
    "SG: Official's Leggings - barrel room, miniboss drop": {"missable": "the one-time drop may be lost if not looted"},
    # Ordinary-looking enemies: "mob drop", like the sack miners.
    **{f"SS: {piece} - second swamp islet, miniboss drop": {"name": f"SS: {piece} - second swamp islet, mob drop"}
       for piece in ("Dull Gold Helm", "Dull Gold Armor", "Dull Gold Gauntlets", "Dull Gold Leggings")},
    'TC: Dragonstone Chunk - lizard nest, first phantom drop': {"name": 'TC: Dragonstone Chunk - lizard nest, phantom drop', "missable": 'the drop is lost if not picked up before the area reloads'},
    'TC: Clearstone Chunk - lizard nest, second phantom drop': {"name": 'TC: Clearstone Chunk - lizard nest, phantom drop', "missable": 'the drop is lost if not picked up before the area reloads'},
    'TC: Stone of Ephemeral Eyes - lizard nest, first phantom drop': {"name": 'TC: Stone of Ephemeral Eyes - lizard nest, phantom drop 1', "missable": 'the drop is lost if not picked up before the area reloads'},
    'TC: Stone of Ephemeral Eyes - lizard nest, second phantom drop': {"name": 'TC: Stone of Ephemeral Eyes - lizard nest, phantom drop 2', "missable": 'the drop is lost if not picked up before the area reloads'},
}

# Glossary corrections for the location guide (map -> term -> new text; None removes the term). From the review.
GLOSSARY_FIXES: dict[str, dict[str, str | None]] = {
    "m02_01_00_00": {
        "prison": "Behind the locked door near the first Blue Eye Knight before the boss fog (Iron Key Ring): a "
                  "corridor of locked cells (Biorr in one), a Fat Official, then a tunnel past a Crystal Lizard to an "
                  "iron gate. 'Cell next to Biorr' is the cell beside Biorr's on the end wall; 'far cell' is the second "
                  "cell on the side wall; 'tunnel end' is the corpse by the iron gate at the end.",
    },
    "m03_01_00_00": {
        "key tower": "The crumbled tower at the end of the rampart; stairs down to a floor-switch spear trap and the "
                     "closed steel gate opened with the Copper Key; its broken top is where you can roll off to the "
                     "hidden ledge.",
        "east tower": "The tower past the archer walkway: the left way up leads to the archer tower, its other door to "
                      "the crow's cliff, its stairs down to the first illusory wall into the cell tunnels.",
        "crow's cliff": "The path up the cliff from the east tower to Sparkly the Crow's nest; the lizard ledge with a "
                        "Crystal Lizard is below the nest (drop down).",
        "cell tunnels": "The corridors behind the illusory wall at the bottom of the small stairs below the east tower: "
                        "a crossroad with a two-skeleton ambush, Graverobber Blige's locked cell at one end, a second "
                        "illusory wall at the other, beyond which an arrow trap and a rubble climb lead up into the pit "
                        "courtyard. Both illusory walls come back every time the area loads.",
        "pit courtyard": "The open courtyard straight through the first fog gate, on the same level, where the optional "
                         "Vanguard (miniboss) stands; an open pit in its floor drops to the corridor outside the cell "
                         "tunnels, and the rubble there climbs back up. The second fog gate is on its far side.",
        "second fog gate": "The fog gate on the far side of the pit courtyard (also reached by the rubble climb out of "
                           "the courtyard pit).",
    },
    "m03_02_00_00": {
        "bridge": "The upper walkway of the casket hall; coming in from the tunnel it is on the left (it is across the "
                  "bridge if you come back up the stairs from below).",
        "west stairs": None,
        "left stairs": "The staircase by the casket hall, past Patches through the gate, climbing to the trapped Stone "
                       "of Ephemeral Eyes at the top; the illusory wall to the secret cliff is halfway up on the right.",
        "secret cliff": "The path behind the illusory wall on the left stairs: a dual-katana Black Skeleton at the cliff "
                        "edge, then a narrow path up past a Crystal Lizard (and the Primeval Demon at black tendency) to "
                        "the White Bow at the top.",
        "first slugs": None,
    },
    "m06_01_00_00": {
        "bearbug ledge": "The ledge at the bottom of the stairs down from the rift platforms where Patches sets his "
                         "trap: the Flame Resistance Ring glows on the upper ledge where the Giant Bearbug waits, and the "
                         "Club (the bait) lies on the ledge below where it lands.",
        "worm cliff": "The open ledge with ore carts and three rock worms at the bottom of the rift path, right before "
                      "the fog entrance to the bug tunnels; flying bearbugs come up from its edge.",
    },
    "m02_00_00_00": {
        "execution grounds stairwell": "The stairwell building of the execution grounds, where Executioner Miralda "
                                       "hides (pure white tendency only).",
    },
    "m02_02_00_00": {
        "by gate lever": "Down the stairs from the yard before the closed gate, next to the lever that reopens it.",
    },
    "m02_03_00_00": {
        "long walkway": "The long walkway before the elevator to the boss, where a black phantom attacks.",
    },
    "m04_00_00_00": {
        "below catwalk ledge": "The ground below the catwalk ledge, under the Liar's balcony, near the church before "
                               "the boss (a crossbow black phantom hides there).",
    },
    "m05_01_00_00": {
        "second swamp islet": "The small island in the second swamp, east of the giants' island and west of the slug "
                              "nest, where a lone Phosphorescent Slug sits.",
    },
    "m06_00_00_00": {
        "cliff corridor": "The corridor with four miners just before the cliff above the archstone.",
        "magma wheel room": "The room with five miners and the magma wheel at the bottom of the lizard tower.",
    },
    "m06_01_00_00": {
        "Scirvir's cave": "The cave halfway down the great pit with two Crystal Lizards, where Scirvir stands.",
    },
    "m05_02_00_00": {
        "plague swamp end": "The far end of the plague swamp, where Garl Vinland guards Maiden Astraea.",
        "cavern": "The boss arena past the boss fog gate at the bottom of the upper descent (the fight starts with a "
                  "cutscene on entry): a vast cavern with Depraved Ones praying to the Maiden.",
        "upper descent": "Holes and ladders leading down from the Dirty Colossus archstone to the boss fog gate.",
    },
}


# Locations the owner added on top of the research (review recommendation): the Fat Officials' New Moon Grass is
# always dropped, only its count is random (x1 or x2). Vanilla item: New Moon Grass x1. Same corpse as their key.
ADDITIONS = [
    {"map": "m02_01_00_00", "kind": "enemy", "flag": 560, "lot": 220080, "entity": 115, "corpse_flag": 15622,
     "item": "New Moon Grass", "count": 1, "random_count": True, "name": "LP: New Moon Grass - prison, miniboss drop",
     "description": "The Fat Official inside the prison, who also drops the Bloody Iron Key.",
     "requires": ["Iron Key Ring"], "added_not_in_input": True},
    {"map": "m02_02_00_00", "kind": "enemy", "flag": 1280, "lot": 230090, "entity": 451, "corpse_flag": 15621,
     "item": "New Moon Grass", "count": 1, "random_count": True, "name": "IW: New Moon Grass - after first fog, miniboss drop",
     "description": "The Fat Official in the yard right after the first fog, who also drops the Iron Key Ring.",
     "requires": [], "added_not_in_input": True},
    {"map": "m02_02_00_00", "kind": "enemy", "flag": 1281, "lot": 230090, "entity": 452, "corpse_flag": 15620,
     "item": "New Moon Grass", "count": 1, "random_count": True, "name": "IW: New Moon Grass - by gate lever, miniboss drop",
     "description": "The Fat Official by the gate lever, who also drops the Official's Cap.",
     "requires": [], "added_not_in_input": True},
]
