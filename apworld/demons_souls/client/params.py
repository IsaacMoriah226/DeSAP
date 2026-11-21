"""The game's param tables in memory: find them and rewrite rows (lots, shop lineup, weapon requirements, item
icons). Field offsets come from Paramdex's DES paramdefs (checked against them in DeSAP's tests); the client needs
no game files.

Loaded params keep the PARAM file layout (verified 2026-11-20): +0x0a u16 row count, +0x0c type name, +0x2c
endianness byte (0), row table at +0x30 of (i32 id, u32 data offset, u32 name offset).

Memory may hold a second copy of a param: a load buffer the game frees, whose memory is then reused (writing into
it crashed the game, 2026-11-21). The live copy is the one the game's param list points to (one pointer to its
start, verified for all five tables). Only those copies are used, and the pointer is checked again right before
every write.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .memory import GameMemory

# type name -> (row count in 01.007.000, row size)
TABLES = {
    "ITEMLOT_PARAM_ST": (1511, 192),
    "SHOP_LINEUP_PARAM": (177, 32),
    "EQUIP_PARAM_WEAPON_ST": (1882, 184),
    "EQUIP_PARAM_GOODS_ST": (149, 72),
    "CHARACTER_INIT_PARAM": (122, 288),
}

# ItemLotParam: 8 entries of 20 bytes from +4: i32 category, i32 id, u16 count, u16 base point, i16 QWC base
# point, i16 QWC applies point, u16 enable luck; then host-only item (i32 category, i32 id, u16 count) at +164;
# i32 eventId (the lot's one-time flag) at +176.
LOT_ENTRY_START, LOT_ENTRY_SIZE, LOT_ENTRIES = 4, 20, 8
LOT_HOST_ONLY = 164
# ShopLineupParam: u8 shopType, u8 equipType (0 weapon, 1 armor, 2 ring, 3 goods), i32 equipId at +4, i32 value
# (price) at +8, i32 mtrlId at +12, i32 eventFlag at +16, i32 sellQuantity at +20.
SHOP_EQUIP_TYPE, SHOP_EQUIP_ID = 1, 4
SHOP_EQUIP_TYPES = {0x00000000: 0, 0x10000000: 1, 0x20000000: 2, 0x40000000: 3}
# EquipParamWeapon: u8 properStrength, properAgility, properMagic, properFaith at +108 (verified: zeroing them lets
# an under-leveled weapon swing normally).
WEAPON_REQUIREMENTS = 108
# EquipParamGoods: u16 iconId at +0 (the PS3's; the remake's inventory ignores it), and at +64, past the PS3 fields,
# a u32 of the remake's (17177 for the Nexial Binding, different for every item): its link to the item's icon and
# 3D preview, by the look of it (to check in game).
GOODS_ICON = 0
GOODS_REMAKE_UI = 64


@dataclass
class Table:
    start: int
    rows: dict[int, int]  # row id -> row address
    name: str = ""
    reference: int = 0  # where the game's param list points at this copy (0: not checked)

    def row(self, row_id: int) -> int | None:
        return self.rows.get(row_id)

    def live(self, game: GameMemory) -> bool:
        """Still the game's copy: its param list still points here and the header is still this table's."""
        try:
            if self.reference and game.u64(self.reference) != self.start:
                return False
            header = game.read(self.start, 0x30)
        except OSError:
            return False
        count, _size = TABLES.get(self.name, (None, None))
        return header[0x0C:0x0C + len(self.name)] == self.name.encode("ascii") and (
            count is None or struct.unpack_from("<H", header, 0x0A)[0] == count)


def read_table(game: GameMemory, start: int) -> Table:
    count = struct.unpack("<H", game.read(start + 0x0A, 2))[0]
    table = game.read(start + 0x30, count * 12)
    rows = {}
    for i in range(count):
        row_id, data_at, _name = struct.unpack_from("<iII", table, i * 12)
        rows[row_id] = start + data_at
    return Table(start, rows)


def find_tables(game: GameMemory) -> dict[str, list[Table]]:
    """The game's live copy of each TABLES param (two passes over the game's memory: about 45 s)."""
    needles = {name: name.encode("ascii") + b"\0" for name in TABLES}
    hits = game.find_guest(list(needles.values()), limit=32)
    out: dict[str, list[Table]] = {name: [] for name in TABLES}
    for name, needle in needles.items():
        count, row_size = TABLES[name]
        for hit in hits[needle]:
            start = hit - 0x0C
            try:
                header = game.read(start, 0x30)
                if header[0x2C] != 0 or struct.unpack_from("<H", header, 0x0A)[0] != count:
                    continue
                table = read_table(game, start)
            except OSError:
                continue
            addresses = sorted(table.rows.values())
            if len(addresses) > 1 and addresses[1] - addresses[0] != row_size:
                continue
            table.name = name
            out[name].append(table)
    candidates = [t for copies in out.values() for t in copies]
    if candidates:  # keep the copies the game points to
        pointers = game.find_guest([struct.pack("<Q", t.start) for t in candidates], limit=4)
        for name, copies in out.items():
            live = []
            for table in copies:
                found = pointers[struct.pack("<Q", table.start)]
                if found:
                    table.reference = found[0]
                    live.append(table)
            out[name] = live
    return out


def lot_bytes(category: int, item_id: int, count: int, host_only: bool) -> dict[int, bytes]:
    """Writes (offset -> bytes) that make a lot give exactly this item: one weighted entry with every point, the
    others nothing; for host-only lots (NPCs and unique enemies) the item goes in the host-only slot and the
    weighted entries give nothing. A category of -1 makes the lot give nothing at all."""
    writes: dict[int, bytes] = {}
    for i in range(LOT_ENTRIES):
        at = LOT_ENTRY_START + i * LOT_ENTRY_SIZE
        if i == 0 and not host_only and category != -1:
            writes[at] = struct.pack("<iiHHhhH", category, item_id, count, 1000, 0, 0, 0)
        else:
            writes[at] = struct.pack("<iiHHhhH", 0, 0, 0, 1000 if i == 0 else 0, 0, 0, 0)
    if host_only and category != -1:
        writes[LOT_HOST_ONLY] = struct.pack("<iiH", category, item_id, count)
    else:
        writes[LOT_HOST_ONLY] = struct.pack("<iiH", 0, 0, 0)
    return writes


def shop_bytes(category: int, item_id: int) -> dict[int, bytes]:
    return {SHOP_EQUIP_TYPE: bytes([SHOP_EQUIP_TYPES[category]]), SHOP_EQUIP_ID: struct.pack("<i", item_id)}


def write_row(game: GameMemory, row: int, writes: dict[int, bytes]) -> None:
    for offset, data in writes.items():
        game.write(row + offset, data)


def row_matches(game: GameMemory, row: int, writes: dict[int, bytes]) -> bool:
    return all(game.read(row + offset, len(data)) == data for offset, data in writes.items())
