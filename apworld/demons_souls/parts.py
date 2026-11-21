"""The world parts (Archipelago regions) and their bosses.

Parts are numbered as the community does (the Fextralife "World Number" system): world 1 Boletarian Palace,
2 Stonefang Tunnel, 3 Tower of Latria, 4 Shrine of Storms, 5 Valley of Defilement. Each part runs from its
archstone to its boss. The game's map ids differ from the world numbers (Stonefang is m06, Latria m04, Shrine m03,
Valley m05).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Part:
    code: str  # "1-1"
    world: int
    number: int
    area: str  # the area's name
    abbreviation: str  # location name prefix
    map: str  # the game's map id
    boss: str

    @property
    def lock_item(self) -> str:
        """The Archipelago item that opens this part (None for 1-1, open from the start)."""
        return f"{self.code} {self.area}"

    @property
    def boss_event(self) -> str:
        return f"Defeated {self.boss}"


PARTS: tuple[Part, ...] = (
    Part("1-1", 1, 1, "Gates of Boletaria", "GB", "m02_00_00_00", "Phalanx"),
    Part("1-2", 1, 2, "The Lord's Path", "LP", "m02_01_00_00", "Tower Knight"),
    Part("1-3", 1, 3, "Inner Ward", "IW", "m02_02_00_00", "Penetrator"),
    Part("1-4", 1, 4, "The King's Tower", "KT", "m02_03_00_00", "Old King Allant"),
    Part("2-1", 2, 1, "Smithing Grounds", "SG", "m06_00_00_00", "Armor Spider"),
    Part("2-2", 2, 2, "The Tunnel City", "TC", "m06_01_00_00", "Flamelurker"),
    Part("2-3", 2, 3, "Underground Temple", "UT", "m06_02_00_00", "Dragon God"),
    Part("3-1", 3, 1, "Prison of Hope", "PH", "m04_00_00_00", "Fool's Idol"),
    Part("3-2", 3, 2, "Upper Latria", "UL", "m04_01_00_00", "Maneater"),
    Part("3-3", 3, 3, "The Ivory Tower", "IT", "m04_02_00_00", "Old Monk"),
    Part("4-1", 4, 1, "Island's Edge", "IE", "m03_01_00_00", "Adjudicator"),
    Part("4-2", 4, 2, "The Ritual Path", "RP", "m03_02_00_00", "Old Hero"),
    Part("4-3", 4, 3, "Altar of Storms", "AS", "m03_03_00_00", "Storm King"),
    Part("5-1", 5, 1, "Depraved Chasm", "DC", "m05_00_00_00", "Leechmonger"),
    Part("5-2", 5, 2, "Swamp of Sorrow", "SS", "m05_01_00_00", "Dirty Colossus"),
    Part("5-3", 5, 3, "Rotting Haven", "RH", "m05_02_00_00", "Maiden Astraea"),
)
PART_BY_CODE = {part.code: part for part in PARTS}
LOCKED_PARTS = tuple(part for part in PARTS if part.code != "1-1")
LOCK_ITEMS = tuple(part.lock_item for part in LOCKED_PARTS)

# The archdemons whose deaths open the way to the Old One (the last part of each world).
ARCHDEMON_PARTS = ("1-4", "2-3", "3-3", "4-3", "5-3")

HUB_REGIONS = ("Tutorial", "Nexus")
