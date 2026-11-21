"""The running game: what the client reads (save identity, flags, map, deaths, inventory) and does (give and remove
items, send the player to the Nexus, kill the player, patch params and text). Blocking calls; the client runs them
off its event loop.

Addresses and how they were found: addresses.py. Status of each mechanism (verified in game or not): DeSAP's
docs/CLIENT.md.
"""

from __future__ import annotations

import logging
import struct
import time
from dataclasses import dataclass
from pathlib import Path

from . import addresses as A
from . import params
from .flags import CLIENT_BLOCK, CLIENT_BLOCK_SIZE, IDENTITY_OFFSET, RECEIVED_OFFSET, SNAPSHOT_SIZE, Flags, delivered_bit
from .gamecall import Call, GameCall
from .live import LiveControl
from .memory import Freeze, PAGE_READWRITE, GameMemory, find_pid

logger = logging.getLogger("Client")


class GameVersionError(RuntimeError):
    pass


@dataclass
class GameState:
    in_game: bool  # a character is loaded
    map_uid: int  # 0x02010000 for m02_01_00_00; -1 while unknown
    flags: Flags | None
    death_count: int
    position: tuple[float, float, float] | None = None  # the player's (world coordinates, y up)

    @property
    def area(self) -> int:
        return self.map_uid >> 24 & 0xFF if self.map_uid != -1 else -1

    @property
    def map_id(self) -> str:
        if self.map_uid == -1:
            return ""
        return f"m{self.map_uid >> 24 & 0xFF:02d}_{self.map_uid >> 16 & 0xFF:02d}_00_00"


@dataclass
class InventoryEntry:
    category: int
    item_id: int
    count: int


class DemonsSoulsGame:
    def __init__(self, live_file: Path):
        self.live = LiveControl(live_file)
        self.memory: GameMemory | None = None
        self.call: GameCall | None = None
        self.tables: dict[str, list[params.Table]] = {}
        self.originals: dict[int, bytes] = {}  # address -> the bytes there before the first rewrite
        self.exe_path = ""

    # --- attaching ---------------------------------------------------------------------------------------------

    @property
    def attached(self) -> bool:
        return self.memory is not None and self.memory.alive()

    def attach(self) -> None:
        """Open the emulator, check the game version, install the call stub. Raises LookupError when the emulator
        is not running or the game has not finished starting, GameVersionError on another game version."""
        memory = GameMemory(find_pid(), write=True)
        try:
            try:
                started = memory.u64(A.FLAG_MANAGER) != 0  # (the event flags exist from the title screen on)
            except OSError:
                started = False
            if not started:
                raise LookupError("the game is still starting")
            for address, expected in A.SIGNATURES.items():
                found = memory.read(address, len(expected) // 2).hex()
                if address == A.TRIGGER_CALLBACK and found.startswith("48b8"):
                    continue  # our own jump (an earlier client's stub)
                if found != expected:
                    raise GameVersionError(f"unexpected code at {address:#x} ({found}): this client supports "
                                           "Demon's Souls 01.007.000 only")
            call = GameCall(memory, self.live.gamecmd)
            call.install()
        except Exception:
            memory.close()
            raise
        self.memory, self.call = memory, call
        self.tables = {}
        self.originals = {}
        try:
            self.exe_path = memory.image_path()
        except OSError:
            self.exe_path = ""

    def detach(self) -> None:
        if self.memory is not None:
            try:
                if self.call is not None and self.memory.alive():
                    self.call.uninstall()
            except OSError:
                pass
            self.memory.close()
        self.memory = self.call = None
        self.tables = {}
        self.originals = {}
        self.__dict__.pop("_text_buffers", None)

    # --- reading -------------------------------------------------------------------------------------------------

    def state(self) -> GameState:
        m = self.memory
        try:
            chr_ins = m.u64(m.u64(A.CHR_INS_MAN) + A.PLAYER_CHR) if m.u64(A.CHR_INS_MAN) else 0
        except OSError:
            chr_ins = 0
        map_uid = -1
        try:
            manager = m.u64(A.MAP_MANAGER)
            if manager:
                index = m.i32(manager + A.MAP_CURRENT_BLOCK)
                blocks = m.u64(manager + A.MAP_BLOCKS)
                if index >= 0 and blocks and index < m.i32(blocks + 0x10):
                    block = m.u64(blocks + 0x18 + 8 * index)
                    if block:
                        map_uid = m.u32(block + A.BLOCK_MAP_UID)
        except OSError:
            pass
        flags = None
        death_count = -1
        try:
            manager = m.u64(A.FLAG_MANAGER)
            if manager:
                flags = Flags(m.read(manager, SNAPSHOT_SIZE))
            player = m.u64(A.PLAYER_GAME_DATA)
            if player:
                death_count = m.u32(player + A.DEATH_COUNT)
        except OSError:
            pass
        position = None
        if chr_ins:
            try:
                body = m.u64(m.u64(chr_ins + A.CHR_CTRL) + A.CHR_BODY)
                if body:
                    position = struct.unpack("<3f", m.read(body + A.BODY_POSITION, 12))
            except OSError:
                position = None
        return GameState(bool(chr_ins) and flags is not None and map_uid != -1, map_uid, flags, death_count,
                         position)

    def inventory(self) -> list[InventoryEntry]:
        m = self.memory
        data = m.u64(m.u64(A.PLAYER_GAME_DATA) + A.PLAYER_DATA) + A.INVENTORY
        count = m.i32(data + A.INVENTORY_COUNT)
        entries = m.u64(data + A.INVENTORY_ENTRIES)
        if not 0 < count <= 4096 or not entries:
            return []
        raw = m.read(entries, count * A.INVENTORY_ENTRY_SIZE)
        out = []
        for i in range(count):
            category, item_id, amount = struct.unpack_from("<iiI", raw, i * A.INVENTORY_ENTRY_SIZE)
            if item_id > 0 and category in (0, 0x10000000, 0x20000000, 0x40000000) and amount > 0:
                out.append(InventoryEntry(category, item_id, amount))
        return out

    # --- the save's Archipelago state (unused event flags, see flags.py) -----------------------------------------

    def write_identity(self, identity: int) -> None:
        self.memory.write(self.memory.u64(A.FLAG_MANAGER) + IDENTITY_OFFSET, struct.pack("<Q", identity))

    def write_received(self, count: int) -> None:
        self.memory.write(self.memory.u64(A.FLAG_MANAGER) + RECEIVED_OFFSET, struct.pack("<I", count))

    def set_delivered(self, index: int) -> None:
        offset, bit = delivered_bit(index)
        at = self.memory.u64(A.FLAG_MANAGER) + offset
        self.memory.write(at, bytes([self.memory.u8(at) | 1 << bit]))  # (the game never writes these flags)

    def clear_client_flags(self) -> None:
        """Zero the client's block (a save being claimed)."""
        self.memory.write(self.memory.u64(A.FLAG_MANAGER) + CLIENT_BLOCK, bytes(CLIENT_BLOCK_SIZE))

    # --- actions -------------------------------------------------------------------------------------------------

    def give_items(self, items: list[tuple[int, int, int]]) -> None:
        """(category, id, count) each, with the game's "item get" popup."""
        self.call.run([Call(A.GIVE_ITEM, (0, category, item_id, count)) for category, item_id, count in items])

    def remove_item(self, category: int, item_id: int, count: int = 1) -> None:
        self.call.run([Call(A.REMOVE_ITEM, (0, category, item_id))] * count)

    def warp_to_nexus(self, from_area: int) -> None:
        """The archstones' own warp to the Nexus, landing in front of `from_area`'s archstone."""
        event = A.NEXUS_RETURN_EVENT.get(from_area, -1)
        self.call.run([Call(A.WARP_NEXT_STAGE, (0, A.NEXUS_AREA, 0, 0, 0, event))])

    def kill_player(self) -> None:
        self.live.gamecmd(A.SUICIDE_COMMAND)

    # --- params and text -----------------------------------------------------------------------------------------

    def prepare(self, text_keys: list[str]) -> dict[str, list[int]]:
        """Find the live param tables and the text entries of `text_keys` in one pass over the game's memory (by
        the markers of addresses.py: about 15 s where they have always been, longer if they must be looked for
        everywhere). Returns the text fields (as find_text_entries); sets self.tables. Raises LookupError when the
        item lots are not there yet."""
        tables, fields = self.scan_markers(text_keys, *A.HOT_MEMORY)
        if len(tables["ITEMLOT_PARAM_ST"]) != 1 or not all(fields.values()):
            logger.info("Not all of the game's tables are where they usually are: searching all of its memory.")
            tables, fields = self.scan_markers(text_keys)
        if len(tables["ITEMLOT_PARAM_ST"]) != 1:
            raise LookupError("the item lots are not in memory yet (or not one live copy)")
        self.tables = tables
        return fields

    def scan_markers(self, text_keys: list[str], start: int = 0, end: int = 1 << 47):
        """(live TABLES copies, text fields of text_keys) found in [start, end) by their markers. Regular
        expressions, not bytes.find: several times faster here (about 1 s per expression and 4 GB)."""
        import os
        import re
        entry_rx = re.compile(re.escape(struct.pack("<Q", A.PARAM_ENTRY)))
        # a text node whose key is as long as one of the keys (the length qword right after the key's pointer)
        lengths = b"".join(re.escape(bytes([n])) for n in sorted({len(key) for key in text_keys}))
        node_rx = re.compile(re.escape(struct.pack("<QQ", *A.TEXT_NODE)) +
                             b".{%d}[%s]\0{7}" % (A.TEXT_NODE_KEY + 8 - 16, lengths), re.S)
        needles = [key.encode("ascii") + b"\0" for key in text_keys]
        prefix = os.path.commonprefix(needles)  # (a literal prefix keeps the expression fast)
        key_rx = re.compile(re.escape(prefix) + b"(?:" + b"|".join(re.escape(n[len(prefix):]) for n in needles) + b")")
        entries: list[int] = []
        nodes: list[tuple[int, int, int]] = []  # (key pointer, key length, text field)
        key_strings: dict[int, str] = {}
        for at, block, n in self.memory.blocks(start, end, overlap=A.TEXT_NODE_KEY + 16):
            for m in entry_rx.finditer(block, 0, n + 7):
                if m.start() % 8 == 0 and m.start() < n:
                    entries.append(at + m.start())
            for m in node_rx.finditer(block):
                if m.start() % 8 == 0 and m.start() < n:
                    key_at, length = struct.unpack_from("<QQ", block, m.start() + A.TEXT_NODE_KEY)
                    nodes.append((key_at, length, at + m.start() + A.TEXT_NODE_TEXT))
            for m in key_rx.finditer(block):
                if m.start() < n:
                    key_strings[at + m.start()] = m.group(0)[:-1].decode("ascii")
        tables: dict[str, list[params.Table]] = {name: [] for name in params.TABLES}
        seen = set()
        for entry in entries:
            try:
                start_at = self.memory.u64(entry + A.PARAM_ENTRY_TABLE)
                if start_at in seen:
                    continue
                header = self.memory.read(start_at, 0x30)
                name = header[0x0C:0x2C].split(b"\0")[0].decode("ascii", "replace")
                if name not in params.TABLES:
                    continue
                table = params.read_table(self.memory, start_at)
            except OSError:
                continue
            seen.add(start_at)
            table.name, table.reference = name, entry + A.PARAM_ENTRY_TABLE
            if table.live(self.memory):
                tables[name].append(table)
        fields: dict[str, list[int]] = {key: [] for key in text_keys}
        for key_at, length, field in nodes:
            key = key_strings.get(key_at)
            if key is not None and len(key) == length:
                fields[key].append(field)
        return tables, fields

    def paused(self, record: Path | None = None) -> Freeze:
        """A context manager that pauses the game (not its window) while the client prepares it (memory.Freeze)."""
        return Freeze(self.memory.pid, record)

    def find_tables(self) -> dict[str, list[params.Table]]:
        """Locate the param tables (slow: about 30 s). Raises LookupError if the lots are not loaded yet."""
        tables = params.find_tables(self.memory)
        if len(tables["ITEMLOT_PARAM_ST"]) != 1:
            raise LookupError("the item lots are not in memory yet (or not one live copy)")
        self.tables = tables
        return tables

    def tables_live(self) -> bool:
        """Drop copies the game no longer uses; False when the item lots have gone (the tables must be found again)."""
        for name, copies in list(self.tables.items()):
            self.tables[name] = [t for t in copies if t.live(self.memory)]
        if not self.tables.get("ITEMLOT_PARAM_ST"):
            self.tables = {}
            self.originals = {}
            return False
        return True

    def patch_rows(self, table: str, writes: dict[int, dict[int, bytes]]) -> int:
        """Apply row writes (row id -> offset -> bytes) to every copy of a table; rows the copy lacks are skipped.
        Returns how many row writes were made."""
        done = 0
        for copy in self.tables.get(table, []):
            if not copy.live(self.memory):
                continue  # (freed or moved: never write there)
            for row_id, row_writes in writes.items():
                row = copy.row(row_id)
                if row is not None:
                    for offset, data in row_writes.items():
                        self.originals.setdefault(row + offset, self.memory.read(row + offset, len(data)))
                    params.write_row(self.memory, row, row_writes)
                    done += 1
        return done

    def restore_rows(self) -> int:
        """Put back every param byte the client rewrote (the vanilla game again), in copies still live."""
        live = [t for copies in self.tables.values() for t in copies if t.live(self.memory)]
        for address, data in self.originals.items():
            if any(t.start <= address < t.start + 0x100000 for t in live):
                self.memory.write(address, data)
        restored = len(self.originals)
        self.originals = {}
        return restored

    def rows_intact(self, table: str, writes: dict[int, dict[int, bytes]]) -> bool:
        """Whether the patch is still in place (the game could reload its params, e.g. on returning to the title)."""
        for copy in self.tables.get(table, []):
            if not copy.live(self.memory):
                return False
            for row_id, row_writes in writes.items():
                row = copy.row(row_id)
                if row is not None:
                    return params.row_matches(self.memory, row, row_writes)
        return False

    def rename_text(self, key: str, old: str, new: str) -> int:
        """Overwrite a loaded text entry (the remake's .ctxt tables, in memory as `<key>\\0<hash>\\0<text>\\0`).
        `new` must not be longer than `old` (verified: the inventory shows the new text at once). Returns the
        number of copies rewritten."""
        new_bytes, old_bytes = new.encode("utf-8"), old.encode("utf-8")
        if len(new_bytes) > len(old_bytes):
            raise ValueError("the new text must not be longer than the old")
        needle = key.encode("ascii") + b"\0"
        done = 0
        for hit in self.memory.find_guest([needle], limit=16)[needle]:
            try:
                tail = self.memory.read(hit + len(needle), 32 + len(old_bytes))
            except OSError:
                continue
            hash_end = tail.find(b"\0")
            if hash_end < 0 or hash_end > 16:
                continue
            text_at = hit + len(needle) + hash_end + 1
            if tail[hash_end + 1:hash_end + 1 + len(old_bytes) + 1] == old_bytes + b"\0":
                self.memory.write(text_at, new_bytes + b"\0" * (len(old_bytes) - len(new_bytes)))
                done += 1
        return done

    def find_text_entries(self, keys: list[str]) -> dict[str, list[int]]:
        """Each key's loaded text entries (the game loads its text twice): the address of the entry's text field.
        An entry is a hash-table node with string views (pointer, length): +0x28 the .ctxt hash, +0x30 the text,
        +0x50 the key (verified on GOODS_NAME_9998, 2026-11-21). Two memory passes (about a minute)."""
        needles = {key: key.encode("ascii") + b"\0" for key in keys}
        hits = self.memory.find_guest(list(needles.values()), limit=16)
        key_at = {address: key for key, needle in needles.items() for address in hits[needle]}
        if not key_at:
            return {key: [] for key in keys}
        pointers = self.memory.find_guest([struct.pack("<Q", address) for address in key_at], limit=16)
        out: dict[str, list[int]] = {key: [] for key in keys}
        for address, key in key_at.items():
            for field in pointers[struct.pack("<Q", address)]:
                try:
                    if self.memory.u64(field + 8) == len(key):  # the key's length follows its pointer
                        out[key].append(field - 0x20)
                except OSError:
                    continue
        return out

    def set_text_buffer(self, fields: list[int], text: str, buffer_key: str) -> None:
        """Like set_text, but always in the same buffer for `buffer_key` (for text that changes often)."""
        data = text.encode("utf-8")[:0xFF0]
        buffers = self.__dict__.setdefault("_text_buffers", {})
        if buffer_key not in buffers:
            buffers[buffer_key] = self.memory.alloc(0x1000, PAGE_READWRITE)
        buffer = buffers[buffer_key]
        self.memory.write(buffer, data + b"\0")
        for field in fields:
            if self.text_entry_live(field, buffer_key):
                self.memory.write(field, struct.pack("<QQ", buffer, len(data)))

    def text_entry_live(self, field: int, key: str) -> bool:
        """The text entry is still there: its key view (at +0x20 from the text's) still names `key`."""
        try:
            key_at, length = struct.unpack("<QQ", self.memory.read(field + 0x20, 16))
            return length == len(key) and self.memory.read(key_at, length) == key.encode("ascii")
        except OSError:
            return False

    def set_text(self, fields: list[int], text: str, key: str) -> None:
        """Point text entries (from find_text_entries) at a new string of any length (verified: a 60-character
        item name shows whole in the inventory)."""
        data = text.encode("utf-8")
        if len(data) + 1 > 0x1000:
            raise ValueError("text too long")
        buffer = self.memory.alloc(0x1000, PAGE_READWRITE)  # (a page per text: few texts, never freed)
        self.memory.write(buffer, data + b"\0")
        for field in fields:
            if self.text_entry_live(field, key):
                self.memory.write(field, struct.pack("<QQ", buffer, len(data)))
