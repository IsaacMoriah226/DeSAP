"""Event flags, read from one snapshot of the flag manager (pointer at addresses.FLAG_MANAGER).

Flag ids are one bit array (flag n = bit n % 8 of byte n // 8 from the manager). Two ranges belong to the world
being played and are swapped on world change (verified on treasure pickups and the Tower Knight's kill):
  0-3199      live at +0x0,   saved per world at +0x8d0  + (w - 1) * 0x190
  8192-12287  live at +0x400, saved per world at +0x2b1c + (w - 1) * 0x200
Everything else (3200-8191, 12288-18047) is global. The world being played is the byte at +0x3cd3. A world's
number is its map's area (m02_00_00_00 -> 2; the Nexus is 1, the tutorial 8).

The client keeps its own state in the save, in flags nothing uses: 16964-17799 appears in no Lua script (number
literals, comments stripped), no param's flag field, and no flag call of the eboot with a constant id (DeSAP
tools/check_free_flags.py); the scripts' computed flags (archstones visited: 10000 + 200 * area + 1979..1983)
stay below 13584. Kept in the save with the inventory, so the two never disagree:
  16968-17031  the save's Archipelago identity (64 bits, 0 = a save the client has not claimed)
  17032-17063  how many received items the game has been given (32 bits)
  17064-...    one bit per location (in location id order): the game gave this world's item there by itself,
               so the server's copy of it is not given again
"""

from __future__ import annotations

import struct

WORLD_RANGES = (  # (first flag, last flag + 1, live offset, saved base, saved size per world)
    (0, 3200, 0x0, 0x8D0, 0x190),
    (8192, 12288, 0x400, 0x2B1C, 0x200),
)
CURRENT_WORLD = 0x3CD3
FLAG_COUNT = 18048
SNAPSHOT_SIZE = 0x3D00

IDENTITY_FLAG = 16968
RECEIVED_FLAG = 17032
DELIVERED_FLAG = 17064
FREE_END = 17800  # first flag past the free range
IDENTITY_OFFSET = IDENTITY_FLAG // 8  # 8 bytes
RECEIVED_OFFSET = RECEIVED_FLAG // 8  # 4 bytes
DELIVERED_OFFSET = DELIVERED_FLAG // 8
assert IDENTITY_FLAG % 8 == 0 and RECEIVED_OFFSET == IDENTITY_OFFSET + 8 and DELIVERED_OFFSET == RECEIVED_OFFSET + 4


def world_of_map(map_id: str) -> int:
    """m02_01_00_00 -> 2."""
    return int(map_id[1:3])


def flag_location(flag: int, world: int, current_world: int) -> tuple[int, int]:
    """(byte offset from the flag manager, bit) holding `flag` of `world` while `current_world` is loaded."""
    for first, end, live, saved, size in WORLD_RANGES:
        if first <= flag < end:
            relative = flag - first
            if world == current_world:
                return live + relative // 8, relative % 8
            return saved + (world - 1) * size + relative // 8, relative % 8
    if not 0 <= flag < FLAG_COUNT:
        raise ValueError(f"flag {flag} out of range")
    return flag // 8, flag % 8


class Flags:
    """A snapshot of the flag manager."""

    def __init__(self, data: bytes):
        if len(data) < SNAPSHOT_SIZE:
            raise ValueError("short flag snapshot")
        self.data = data
        self.current_world = data[CURRENT_WORLD]

    def get(self, flag: int, world: int) -> bool:
        offset, bit = flag_location(flag, world, self.current_world)
        return bool(self.data[offset] >> bit & 1)

    def byte(self, flag: int, world: int) -> int:
        """The whole byte holding `flag` (shop purchase counters are 8-bit counters at flag // 8)."""
        offset, _bit = flag_location(flag, world, self.current_world)
        return self.data[offset]

    @property
    def identity(self) -> int:
        return struct.unpack_from("<Q", self.data, IDENTITY_OFFSET)[0]

    @property
    def received(self) -> int:
        return struct.unpack_from("<I", self.data, RECEIVED_OFFSET)[0]

    def delivered(self, index: int) -> bool:
        return bool(self.data[DELIVERED_OFFSET + index // 8] >> index % 8 & 1)


def delivered_bit(index: int) -> tuple[int, int]:
    """(byte offset from the flag manager, bit) of location `index`'s delivered bit."""
    if not 0 <= index < (FREE_END - DELIVERED_FLAG):
        raise ValueError(f"location index {index} past the free flags")
    return DELIVERED_OFFSET + index // 8, index % 8
