"""Archipelago world for Demon's Souls (PS5 remake, PPSA01341, game version 01.007.000).

Logic: 1-1 is open. Every other world part needs its lock item ("1-2 The Lord's Path", ...), and a part after
the first of its world also needs the previous part's boss dead. The goal is the ending credits: the Old One,
reached once every archdemon is dead. Locations that can be lost (world tendency, one-time events) are excluded:
they only get filler.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any, ClassVar

from BaseClasses import Item, ItemClassification, Location, LocationProgressType, Region, Tutorial
from worlds.AutoWorld import WebWorld, World

from .data import ITEMS, LOCATIONS, ItemData, LocationData
from .options import DemonsSoulsOptions, option_groups
from .parts import ARCHDEMON_PARTS, LOCK_ITEMS, LOCKED_PARTS, PART_BY_CODE, PARTS

GAME = "Demon's Souls Remake"
VICTORY = "Victory"
FILLER_FALLBACK = "Crescent Moon Grass"

_CLASSIFICATION = {
    "progression": ItemClassification.progression,
    "useful": ItemClassification.useful,
    "filler": ItemClassification.filler,
}


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

    item_name_to_id: ClassVar[dict[str, int]] = {name: item.code for name, item in ITEMS.items()}
    location_name_to_id: ClassVar[dict[str, int]] = {
        name: location.code for name, location in LOCATIONS.items() if location.code is not None}
    item_name_groups = _groups(ITEMS)
    location_name_groups = _groups(LOCATIONS)
    location_descriptions = {name: location.description for name, location in LOCATIONS.items()
                             if location.code is not None and location.description}

    # --- regions and locations -------------------------------------------------------------------------------

    def create_regions(self) -> None:
        regions = {name: Region(name, self.player, self.multiworld) for name in ("Tutorial", "Nexus")}
        for part in PARTS:
            regions[part.lock_item] = Region(part.lock_item, self.player, self.multiworld)
        regions["The Old One"] = Region("The Old One", self.player, self.multiworld)
        self.multiworld.regions += regions.values()

        regions["Tutorial"].connect(regions["Nexus"], "Leave the tutorial")
        regions["Nexus"].connect(regions[PART_BY_CODE["1-1"].lock_item], "Archstone 1-1")
        for part in LOCKED_PARTS:
            regions["Nexus"].connect(regions[part.lock_item], f"Archstone {part.code}", self._part_rule(part.code))
        regions["Nexus"].connect(regions["The Old One"], "Descend to the Old One", self._requires(
            tuple(f"boss:{code}" for code in ARCHDEMON_PARTS)))

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

        victory = DemonsSoulsLocation(self.player, "The Old One", None, regions["The Old One"])
        victory.place_locked_item(DemonsSoulsItem(VICTORY, ItemClassification.progression, None, self.player))
        regions["The Old One"].locations.append(victory)

    def _part_rule(self, code: str):
        """Entering a locked part: its lock item, and for x-2 and later the previous part's boss dead."""
        part = PART_BY_CODE[code]
        needs = [part.lock_item]
        if part.number > 1:
            needs.append(f"boss:{part.world}-{part.number - 1}")
        return self._requires(tuple(needs))

    def _requires(self, needs: tuple[str, ...]):
        if not needs:
            return lambda state: True
        items = []
        for need in needs:
            if need.startswith("boss:"):
                items.append(PART_BY_CODE[need[5:]].boss_event)
            else:
                items.append(need)
        counts = Counter(items)
        player = self.player
        if len(counts) == 1 and next(iter(counts.values())) == 1:
            only = items[0]
            return lambda state: state.has(only, player)
        return lambda state: state.has_all_counts(counts, player)

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
            "world_version": str(self.world_version),
            "remove_stat_requirements": bool(self.options.remove_stat_requirements),
            "auto_upgrade_weapons": bool(self.options.auto_upgrade_weapons),
            "death_link": bool(self.options.death_link),
        }
