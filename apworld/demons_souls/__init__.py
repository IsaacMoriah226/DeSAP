"""Archipelago world for Demon's Souls (PS5 remake, PPSA01341, game version 01.007.000).

Logic: 1-1 is open. Every other world part needs its lock item ("1-2 The Lord's Path", ...) and the vanilla
conditions of its archstone (see `part_requirements`). The goal is the ending credits: False King Allant below the
Nexus, reached once all five archdemons are dead. Locations that can be lost (world tendency, NPC states, the
tutorial, one-time events) are excluded: they only get filler.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any, ClassVar

from BaseClasses import Item, ItemClassification, Location, LocationProgressType, Region, Tutorial
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, Type, components
from worlds.LauncherComponents import launch as launch_component

from .data import ITEMS, LOCATIONS, ItemData, LocationData
from .loadout import describe, starting_loadouts
from .options import DemonsSoulsOptions, option_groups
from .parts import ARCHDEMON_PARTS, LOCK_ITEMS, LOCKED_PARTS, PART_BY_CODE, PARTS

GAME = "Demon's Souls Remake"
VICTORY = "Victory"
FINAL_REGION = "Below the Nexus"
FILLER_FALLBACK = "Crescent Moon Grass"

_CLASSIFICATION = {
    "progression": ItemClassification.progression,
    "useful": ItemClassification.useful,
    "filler": ItemClassification.filler,
}


def launch_client(*args: str) -> None:
    from .client import launch
    launch_component(launch, name="Demon's Souls Launcher", args=args)


components.append(Component("Demon's Souls Launcher", func=launch_client, component_type=Type.CLIENT, game_name=GAME,
                            supports_uri=True, description="Starts Demon's Souls (KytyPS5) for Archipelago and connects it."))


def part_requirements(code: str) -> tuple[str, ...]:
    """What entering a part from its archstone needs (the client enforces the same):
    - its lock item;
    - x-1 of worlds 2-5: Phalanx dead (the Monumental unseals the other archstones only after the first boss);
    - x-n for n > 1: the boss of x-(n-1) dead (its archstone appears when you take that boss's soul);
    - 1-3 (and so 1-4): an archdemon of another world dead (the gate past the Tower Knight stays sealed until
      then, event flag 8035).
    """
    part = PART_BY_CODE[code]
    needs = [] if code == "1-1" else [part.lock_item]
    if part.number == 1 and part.world != 1:
        needs.append("boss:1-1")
    if part.number > 1:
        needs.append(f"boss:{part.world}-{part.number - 1}")
    if code == "1-3":
        needs.append("any:" + "|".join(f"boss:{other}" for other in ARCHDEMON_PARTS if not other.startswith("1-")))
    return tuple(needs)


def region_name(part: str) -> str:
    """The region a location's `part` field names: "Tutorial", "Nexus", or "1-1 Gates of Boletaria"."""
    return PART_BY_CODE[part].lock_item if part in PART_BY_CODE else part


class DemonsSoulsItem(Item):
    game = GAME


class DemonsSoulsLocation(Location):
    game = GAME


class DemonsSoulsWeb(WebWorld):
    theme = "stone"
    rich_text_options_doc = True
    option_groups = option_groups
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "Setting up the Demon's Souls Remake randomizer (KytyPS5 emulator) for Archipelago.",
        "English",
        "setup_en.md",
        "setup/en",
        ["isaacmoriah226"],
    ), Tutorial(
        "Location Guide",
        "Where every location is, what its name's terms mean, and what each one needs.",
        "English",
        "locations_en.md",
        "locations/en",
        ["isaacmoriah226"],
    )]


def _groups(entries: Mapping[str, ItemData] | Mapping[str, LocationData]) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    for name, entry in entries.items():
        for group in entry.groups:
            groups.setdefault(group, set()).add(name)
    return groups


class DemonsSoulsWorld(World):
    """Demon's Souls is an action role-playing game set in the fog-covered kingdom of Boletaria. Travel from the
    Nexus through five worlds, slay the archdemons and face the Old One. This is the PS5 remake (Bluepoint Games)."""

    game = GAME
    web = DemonsSoulsWeb()
    options_dataclass = DemonsSoulsOptions
    options: DemonsSoulsOptions
    origin_region_name = "Tutorial"
    ut_can_gen_without_yaml = True  # Universal Tracker: no option changes the logic

    item_name_to_id: ClassVar[dict[str, int]] = {name: item.code for name, item in ITEMS.items()}
    location_name_to_id: ClassVar[dict[str, int]] = {
        name: location.code for name, location in LOCATIONS.items() if location.code is not None}
    item_name_groups = _groups(ITEMS)
    location_name_groups = _groups(LOCATIONS)
    location_descriptions = {name: location.description for name, location in LOCATIONS.items()
                             if location.code is not None and location.description}

    loadouts: dict[str, dict[str, int]]

    def generate_early(self) -> None:
        self.loadouts = starting_loadouts(self.random, bool(self.options.remove_stat_requirements)) \
            if self.options.randomize_starting_loadout else {}

    # --- regions and locations -------------------------------------------------------------------------------

    def create_regions(self) -> None:
        regions = {name: Region(name, self.player, self.multiworld) for name in ("Tutorial", "Nexus")}
        for part in PARTS:
            regions[part.lock_item] = Region(part.lock_item, self.player, self.multiworld)
        regions[FINAL_REGION] = Region(FINAL_REGION, self.player, self.multiworld)
        self.multiworld.regions += regions.values()

        regions["Tutorial"].connect(regions["Nexus"], "Leave the tutorial")
        regions["Nexus"].connect(regions[PART_BY_CODE["1-1"].lock_item], "Archstone 1-1")
        for part in LOCKED_PARTS:
            regions["Nexus"].connect(regions[part.lock_item], f"Archstone {part.code}", self._part_rule(part.code))
        # With every archdemon dead, the Maiden in Black takes you below the Nexus to False King Allant.
        regions["Nexus"].connect(regions[FINAL_REGION], "Descend below the Nexus", self._requires(("archdemons:5",)))

        for name, data in LOCATIONS.items():
            region = regions[region_name(data.part)]
            if data.kind == "boss_event":
                # The boss of a part: an event whose item marks the boss dead.
                location = DemonsSoulsLocation(self.player, name, None, region)
                location.place_locked_item(DemonsSoulsItem(PART_BY_CODE[data.part].boss_event,
                                                           ItemClassification.progression, None, self.player))
            else:
                location = DemonsSoulsLocation(self.player, name, data.code, region)
                if data.missable or data.tendency:
                    location.progress_type = LocationProgressType.EXCLUDED
            location.access_rule = self._requires(data.requires)
            region.locations.append(location)

        victory = DemonsSoulsLocation(self.player, "False King Allant", None, regions[FINAL_REGION])
        victory.place_locked_item(DemonsSoulsItem(VICTORY, ItemClassification.progression, None, self.player))
        regions[FINAL_REGION].locations.append(victory)

    def _part_rule(self, code: str):
        """Entering a locked part from the Nexus: see `part_requirements`."""
        return self._requires(part_requirements(code))

    def _requires(self, needs: tuple[str, ...]):
        """A rule for requirement tokens (see DeSAP/tools/research_rules.py): item names, "boss:<part>",
        "region:<part>", "archdemons:<n>", "any:<token>|<token>"."""
        if not needs:
            return lambda state: True
        checks = [self._token(need) for need in needs]
        if len(checks) == 1:
            return checks[0]
        return lambda state: all(check(state) for check in checks)

    def _token(self, need: str):
        player = self.player
        if need.startswith("any:"):
            options = [self._token(option) for option in need[4:].split("|")]
            return lambda state: any(option(state) for option in options)
        if need.startswith("boss:"):
            event = PART_BY_CODE[need[5:]].boss_event
            return lambda state: state.has(event, player)
        if need.startswith("region:"):
            region = PART_BY_CODE[need[7:]].lock_item
            return lambda state: state.can_reach_region(region, player)
        if need.startswith("archdemons:"):
            count = int(need[11:])
            events = [PART_BY_CODE[code].boss_event for code in ARCHDEMON_PARTS]
            return lambda state: state.has_from_list_unique(events, player, count)
        if need not in ITEMS:
            raise KeyError(f"{GAME}: a requirement names an unknown item: {need!r}")
        return lambda state: state.has(need, player)

    def set_rules(self) -> None:
        self.multiworld.completion_condition[self.player] = lambda state: state.has(VICTORY, self.player)

    # --- items -------------------------------------------------------------------------------------------------

    def create_item(self, name: str) -> DemonsSoulsItem:
        data = ITEMS[name]
        return DemonsSoulsItem(name, _CLASSIFICATION[data.classification], data.code, self.player)

    def get_filler_item_name(self) -> str:
        return FILLER_FALLBACK

    def create_items(self) -> None:
        pool = [self.create_item(data.vanilla_item) for data in LOCATIONS.values() if data.code is not None]
        pool += [self.create_item(name) for name in LOCK_ITEMS]
        # Make room for the lock items by dropping filler (never a missable location's only filler).
        surplus = len(pool) - len(self.multiworld.get_unfilled_locations(self.player))
        filler = [i for i, item in enumerate(pool) if item.classification == ItemClassification.filler]
        if surplus > len(filler):
            raise RuntimeError(f"{GAME}: not enough filler to make room for {surplus} items")
        for index in sorted(self.random.sample(filler, surplus), reverse=True):
            del pool[index]
        self.multiworld.itempool += pool

    # --- client data -------------------------------------------------------------------------------------------

    def fill_slot_data(self) -> Mapping[str, Any]:
        return {
            "world_version": self.world_version.as_simple_string(),
            "remove_stat_requirements": bool(self.options.remove_stat_requirements),
            "auto_upgrade_weapons": bool(self.options.auto_upgrade_weapons),
            "death_link": bool(self.options.death_link),
            "starting_loadouts": self.loadouts,
        }

    def write_spoiler(self, spoiler_handle) -> None:
        if self.loadouts:
            spoiler_handle.write(f"\n\nStarting loadouts ({self.multiworld.get_player_name(self.player)}):\n")
            for name, gear in describe(self.loadouts).items():
                spoiler_handle.write(f"    {name}: {', '.join(gear)}\n")
