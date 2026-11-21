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
VANILLA_KEYS = {
    # Dropped by a Fat Official in the Inner Ward.
    "Iron Key Ring": ["region:1-3"],
    # Dropped by the Fat Official in the Lord's Path prison, which needs the Iron Key Ring (Inner Ward).
    "Bloody Iron Key": ["region:1-2", "region:1-3"],
}
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
