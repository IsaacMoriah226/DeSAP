"""Test-session helpers: patch and inspect the running game (Demon's Souls 01.007.000 on KytyPS5).

  python -I session.py params                         where the param tables are loaded
  python -I session.py set-lot <lot> <cat> <id> <n>    a lot gives only that item (cat: weapon armor ring goods)
  python -I session.py rename <old text> <new text>    overwrite loaded text (new must not be longer)
  python -I session.py give <cat> <id> <n>             grant through the game's own item-get (popup)
  python -I session.py noreq <weapon id>               zero a weapon's stat requirements
  python -I session.py player [<item id>...]           dump player data to work\\player.bin; find item ids in it
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from desap import souls  # noqa: E402
from desap.gamecall import GameCall  # noqa: E402
from desap.memory import GameMemory  # noqa: E402

CATEGORY = {"weapon": 0x00000000, "armor": 0x10000000, "ring": 0x20000000, "goods": 0x40000000}
PLAYER_GAME_DATA = 0x9027E6948  # [[this] + 0x10]: the player's stats (cp11_setBaseStats's handler)
WORK = Path(r"C:\Dev\DeSArchi\work")


def loaded_params(game: GameMemory, param_type: str) -> list[int]:
    """Start addresses of loaded copies of a PARAM (its type name sits at +0x0c)."""
    hits = game.find(param_type.encode("ascii") + b"\0", limit=32)
    out = []
    for hit in hits:
        start = hit - 0x0C
        try:
            header = game.read(start, 0x30)
        except OSError:
            continue
        if header[0x2C] == 0 and header[0x0C:0x0C + len(param_type)] == param_type.encode():
            out.append(start)
    return out


def row_offset(game: GameMemory, start: int, row_id: int) -> int | None:
    count = struct.unpack("<H", game.read(start + 0x0A, 2))[0]
    table = game.read(start + 0x30, count * 12)
    for i in range(count):
        rid, data_at, _name = struct.unpack_from("<iII", table, i * 12)
        if rid == row_id:
            return start + data_at
    return None


def cmd_params(game: GameMemory, _args) -> None:
    for name in ("ITEMLOT_PARAM_ST", "EQUIP_PARAM_WEAPON_ST", "EQUIP_PARAM_GOODS_ST", "SHOP_LINEUP_PARAM_ST"):
        starts = loaded_params(game, name)
        print(name, [hex(s) for s in starts])


def cmd_set_lot(game: GameMemory, args) -> None:
    lot, category, item_id, count = int(args[0]), CATEGORY[args[1]], int(args[2]), int(args[3])
    lot_def = souls.load_paramdef("ItemLotParam")
    fields = {f.name: f.offset for f in lot_def.fields}
    for start in loaded_params(game, "ITEMLOT_PARAM_ST"):
        row = row_offset(game, start, lot)
        if row is None:
            print(f"copy {start:#x}: no row {lot}")
            continue
        for i in range(1, 9):
            game.write(row + fields[f"lotItemId0{i}"], struct.pack("<i", 0))
        game.write(row + fields["lotItemCategory01"], struct.pack("<i", category))
        game.write(row + fields["lotItemId01"], struct.pack("<i", item_id))
        game.write(row + fields["lotItemNum01"], struct.pack("<H", count))
        game.write(row + fields["lotItemBasePoint01"], struct.pack("<H", 1000))
        print(f"copy {start:#x}: lot {lot} -> {args[1]} {item_id} x{count}")


def cmd_rename(game: GameMemory, args) -> None:
    old, new = args[0], args[1]
    if len(new) > len(old):
        raise SystemExit("the new text must not be longer than the old")
    for encoding, terminator in (("utf-8", b"\0"), ("utf-16-le", b"\0\0")):
        old_bytes, new_bytes = old.encode(encoding), new.encode(encoding)
        hits = game.find(old_bytes, limit=64)
        for hit in hits:
            game.write(hit, new_bytes + terminator)
        print(f"{encoding}: {len(hits)} copies rewritten {[hex(h) for h in hits[:8]]}")


def cmd_give(game: GameMemory, args) -> None:
    call = GameCall(game)
    call.install()
    try:
        call.give_item(CATEGORY[args[0]], int(args[1]), int(args[2]))
        print("the game ran the item-get call")
    finally:
        call.uninstall()


def cmd_noreq(game: GameMemory, args) -> None:
    weapon = int(args[0])
    offsets = [f.offset for f in souls.load_paramdef("EquipParamWeapon").fields if f.name.startswith("proper")]
    for start in loaded_params(game, "EQUIP_PARAM_WEAPON_ST"):
        row = row_offset(game, start, weapon)
        if row is not None:
            before = [game.u8(row + o) for o in offsets]
            for o in offsets:
                game.write(row + o, b"\0")
            print(f"copy {start:#x}: weapon {weapon} requirements {before} -> 0")


def cmd_player(game: GameMemory, args) -> None:
    data_at = game.u64(game.u64(PLAYER_GAME_DATA) + 0x10)
    blob = game.read(data_at, 0x20000)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "player.bin").write_bytes(blob)
    print(f"player game data at {data_at:#x}; 0x20000 bytes -> {WORK / 'player.bin'}")
    for item in args:
        needle = struct.pack("<I", int(item))
        offsets, i = [], blob.find(needle)
        while i != -1 and len(offsets) < 20:
            if i % 4 == 0:
                offsets.append(i)
            i = blob.find(needle, i + 1)
        print(f"item {item}: at {[hex(o) for o in offsets]}")


COMMANDS = {"params": cmd_params, "set-lot": cmd_set_lot, "rename": cmd_rename, "give": cmd_give,
            "noreq": cmd_noreq, "player": cmd_player}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        raise SystemExit(__doc__)
    write = sys.argv[1] != "params" and sys.argv[1] != "player"
    with GameMemory(write=write) as game:
        COMMANDS[sys.argv[1]](game, sys.argv[2:])


if __name__ == "__main__":
    main()
