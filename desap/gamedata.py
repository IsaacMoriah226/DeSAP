"""The game data the world and client need, read from the dump: item names, item lots and every map's treasures
with the event flag a pickup sets.

Treasure flags (verified in game on 1-1 treasures 2-4 and 1-2 treasures 1-2): a map's treasures are its MSB
treasure events in file order; treasure i of map mWW_SS_00_00 sets flag 10240 + 512 * SS + i. In the flag
manager (pointer at 0x9027bf328) that is bit (flag % 8) of byte flag // 8 while the world is loaded, and the
game writes the same bit into the world's saved block at +0x2b1c + (WW - 1) * 0x200 + (flag - 8192) // 8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from . import msb, souls

DEFAULT_GAME = Path(r"C:\Users\Isaac Moriah\Desktop\PPSA01341-app0")

# ITEMLOT_ITEMCATEGORY -> (kind, item.msgbnd name file id of the PS3 text)
CATEGORIES = {
    0x00000000: ("weapon", 11),
    0x10000000: ("armor", 12),
    0x20000000: ("ring", 13),
    0x40000000: ("goods", 10),
}
# The remake's own UI text (Bluepoint .ctxt files, what the game shows): kind -> (file, key prefix)
REMAKE_TEXT = {
    "weapon": ("weapon_name", "WEAPON_NAME_"),
    "armor": ("protector_name", "PROTECTOR_NAME_"),
    "ring": ("accessory_name", "ACCESSORY_NAME_"),
    "goods": ("goods_name", "GOODS_NAME_"),
    "magic": ("magic_name", "MAGIC_NAME_"),
}


def read_ctxt(path: Path, prefix: str) -> dict[int, str]:
    """Lines `<PREFIX><id>:<hash>=<text>`; continuation lines (multi-line text) are joined with newlines."""
    out: dict[int, str] = {}
    last = None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith(prefix) and ":" in line and "=" in line:
            key, text = line.split("=", 1)
            last = int(key[len(prefix):key.index(":")])
            out[last] = text
        elif last is not None and line:
            out[last] += "\n" + line
    return out
CONSOLE_ADD = {"weapon": "cp11_addWeapon", "armor": "cp11_addArmor", "ring": "cp11_addAccessory",
               "goods": "cp11_addGoods"}

TREASURE_FLAG_BASE = 10240
FLAGS_PER_MAP = 512
WORLD_BLOCK_FIRST_FLAG = 8192
FLAG_MANAGER_PTR = 0x9027bf328
STORED_WORLD_BLOCKS = 0x2B1C
STORED_WORLD_BLOCK_SIZE = 0x200

# Map ids to areas. m02 (1-1, 1-2) is confirmed in game; the rest follow from the boss soul each map's script
# gives (m03: Adjudicator, Old Hero, Storm King; m04: Fool's Idol, Maneater, Old Monk) and their treasures.
AREAS = {
    "m01_00_00_00": "Nexus",
    "m02_00_00_00": "Gates of Boletaria",
    "m02_01_00_00": "The Lord's Path",
    "m02_02_00_00": "Inner Ward",
    "m02_03_00_00": "The King's Tower",
    "m03_00_00_00": "Shrine of Storms (unused)",
    "m03_01_00_00": "Island's Edge",
    "m03_02_00_00": "The Ritual Path",
    "m03_03_00_00": "Altar of Storms",
    "m04_00_00_00": "Prison of Hope",
    "m04_01_00_00": "Upper Latria",
    "m04_02_00_00": "The Ivory Tower",
    "m05_00_00_00": "Depraved Chasm",
    "m05_01_00_00": "Swamp of Sorrow",
    "m05_02_00_00": "Rotting Haven",
    "m06_00_00_00": "Smithing Grounds",
    "m06_01_00_00": "The Tunnel City",
    "m06_02_00_00": "Underground Temple",
    "m08_00_00_00": "Tutorial 1",
    "m08_01_00_00": "Tutorial 2",
    "m08_02_00_00": "Tutorial 3",
}


@dataclass
class LotItem:
    category: str
    id: int
    count: int
    name: str
    chance: int  # lotItemBasePoint (a lot with several items picks one by these weights)


@dataclass
class TreasureLocation:
    map: str
    area: str
    index: int
    flag: int
    part: str
    position: tuple[float, float, float]
    lots: dict[int, list[LotItem]] = field(default_factory=dict)

    @property
    def world(self) -> int:
        return int(self.map[1:3])

    @property
    def stored_offset(self) -> tuple[int, int]:
        """(byte offset from the flag manager, bit) of this flag in its world's saved block."""
        relative = self.flag - WORLD_BLOCK_FIRST_FLAG
        return (STORED_WORLD_BLOCKS + (self.world - 1) * STORED_WORLD_BLOCK_SIZE + relative // 8, relative % 8)


class GameData:
    def __init__(self, game: Path = DEFAULT_GAME, language: str = "na_english"):
        self.game = game
        self.dvdroot = game / "cp11demonssouls" / "dvdroot"
        self.language = language

    @cached_property
    def ps3_names(self) -> dict[int, dict[int, str]]:
        """The original game's item text (msg/<language>/item.msgbnd); the remake does not show it."""
        files = souls.read_bnd3((self.dvdroot / "msg" / self.language / "item.msgbnd").read_bytes())
        return {f.id: souls.read_fmg(f.data) for f in files}

    @cached_property
    def names(self) -> dict[str, dict[int, str]]:
        """kind -> id -> the remake's English name (text/ds/_cmn/*.en.ctxt)."""
        folder = self.game / "text" / "ds" / "_cmn"
        return {kind: read_ctxt(folder / f"{file}.en.ctxt", prefix) for kind, (file, prefix) in REMAKE_TEXT.items()}

    @cached_property
    def params(self) -> dict[str, souls.BinderFile]:
        return souls.read_bnd3_file(self.dvdroot / "param" / "gameparam" / "gameparamna.parambnd")

    @cached_property
    def item_lots(self) -> dict[int, souls.Row]:
        return souls.read_param(self.params["ItemLotParam"].data, souls.load_paramdef("ItemLotParam")).by_id()

    def item_name(self, category: int, item_id: int) -> str:
        kind = CATEGORIES.get(category)
        if kind is None:
            return f"?{category:#x}:{item_id}"
        name = self.names[kind[0]].get(item_id)
        if not name:  # not in the remake's text: the PS3 name, marked
            name = self.ps3_names.get(kind[1], {}).get(item_id)
            return f"{name} (PS3 name)" if name else f"?{kind[0]}:{item_id}"
        return name

    def lot_items(self, lot_id: int) -> list[LotItem]:
        row = self.item_lots.get(lot_id)
        if row is None:
            return []
        out = []
        for i in range(1, 9):
            category, item_id = row[f"lotItemCategory0{i}"], row[f"lotItemId0{i}"]
            if item_id <= 0 or category == -1 or category not in CATEGORIES:
                continue
            out.append(LotItem(CATEGORIES[category][0], item_id, row[f"lotItemNum0{i}"],
                               self.item_name(category, item_id), row[f"lotItemBasePoint0{i}"]))
        return out

    def host_only_item(self, lot_id: int) -> LotItem | None:
        """A lot's host-only item (hostOnlyItemCate/Id/Num): always given to the world's host on top of the weighted
        entries. NPCs and unique enemies carry their fixed drops here (their weighted entries are "nothing")."""
        row = self.item_lots.get(lot_id)
        if row is None:
            return None
        category, item_id = row["hostOnlyItemCate"], row["hostOnlyItemId"]
        if item_id <= 0 or category not in CATEGORIES:
            return None
        return LotItem(CATEGORIES[category][0], item_id, row["hostOnlyItemNum"], self.item_name(category, item_id),
                       1000)

    def treasures(self) -> list[TreasureLocation]:
        out = []
        for path in sorted((self.dvdroot / "map" / "mapstudio").glob("m0*.msb")):
            if len(path.name) != 16:
                continue
            data = msb.read_msb(path)
            sub = int(data.map[4:6])
            for index, treasure in enumerate(data.treasures):
                location = TreasureLocation(
                    data.map, AREAS.get(data.map, data.map), index, TREASURE_FLAG_BASE + FLAGS_PER_MAP * sub + index,
                    treasure.part.name if treasure.part else "", treasure.part.position if treasure.part else (0, 0, 0))
                for lot in treasure.item_lots:
                    location.lots[lot] = self.lot_items(lot)
                out.append(location)
        return out
