"""Test-session helpers: drive the client's game access by hand (Demon's Souls 01.007.000 on KytyPS5).
The emulator must run with live control on (KYTY_LIVE_FILE = DESAP_LIVE_FILE, default work\\live.txt).

  python -I tools/session.py state                      character, map, world, deaths, the save's client flags
  python -I tools/session.py watch [seconds]            print map and death-count changes (walk across a border)
  python -I tools/session.py tables                     find the param tables (ItemLot, ShopLineup, ...)
  python -I tools/session.py give <cat> <id> <n> [...]  give items through the game's item-get, one batch
  python -I tools/session.py remove <cat> <id> [n]      RemoveInventoryEquip n times
  python -I tools/session.py inventory [<id>...]        the inventory (or only these ids)
  python -I tools/session.py nexus                      the archstones' warp to the Nexus
  python -I tools/session.py kill                       cp11_playerSuicide
  python -I tools/session.py set-lot <lot> <cat> <id> <n> [host]   a lot gives only that item
  python -I tools/session.py set-shop <row> <cat> <id>  a shop row sells that item
  python -I tools/session.py rename <key> <old> <new>   overwrite a text entry (same length or shorter)
  python -I tools/session.py text-refs <key>            where the game points at a text entry (for longer names)
  python -I tools/session.py mark <hex>                 write 8 bytes into the client's identity flags
  python -I tools/session.py noreq <weapon id>          zero a weapon's stat requirements
cat: weapon armor ring goods
"""

from __future__ import annotations

import os
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apworld" / "demons_souls"))
from client import addresses as A  # noqa: E402
from client import params  # noqa: E402
from client.flags import IDENTITY_OFFSET  # noqa: E402
from client.game import DemonsSoulsGame  # noqa: E402

LIVE_FILE = Path(os.environ.get("DESAP_LIVE_FILE", r"C:\Dev\DeSArchi\work\live.txt"))


def category(name: str) -> int:
    return A.CATEGORY[name]


def show_state(game: DemonsSoulsGame) -> None:
    state = game.state()
    flags = state.flags
    print(f"in game {state.in_game}, map uid {state.map_uid:#x} ({state.map_id}), area {state.area}, "
          f"flag world {flags.current_world if flags else '?'}, deaths {state.death_count}")
    if flags:
        print(f"client flags: identity {flags.identity:#018x}, received {flags.received}")


def cmd_state(game, _args) -> None:
    show_state(game)


def cmd_watch(game, args) -> None:
    end = time.monotonic() + (float(args[0]) if args else 1e9)
    last = None
    while time.monotonic() < end:
        state = game.state()
        now = (state.in_game, state.map_uid, state.death_count, state.flags.current_world if state.flags else -1)
        if now != last:
            print(f"{time.strftime('%H:%M:%S')} in game {now[0]}, map {state.map_id or '-'} ({now[1]:#x}), "
                  f"deaths {now[2]}, flag world {now[3]}", flush=True)
            last = now
        time.sleep(0.1)


def cmd_tables(game, _args) -> None:
    start = time.monotonic()
    tables = params.find_tables(game.memory)
    print(f"searched in {time.monotonic() - start:.0f} s")
    for name, copies in tables.items():
        print(name, [(hex(t.start), len(t.rows)) for t in copies])


def cmd_give(game, args) -> None:
    items = [(category(args[i]), int(args[i + 1]), int(args[i + 2])) for i in range(0, len(args), 3)]
    game.give_items(items)
    print(f"the game ran {len(items)} item-get call(s)")


def cmd_remove(game, args) -> None:
    game.remove_item(category(args[0]), int(args[1]), int(args[2]) if len(args) > 2 else 1)
    print("removed")


def cmd_inventory(game, args) -> None:
    wanted = {int(a) for a in args}
    for entry in game.inventory():
        if not wanted or entry.item_id in wanted:
            print(f"{entry.category:#x} {entry.item_id} x{entry.count}")


def cmd_nexus(game, _args) -> None:
    state = game.state()
    game.warp_to_nexus(state.area)
    print(f"warp to the Nexus requested (from area {state.area})")


def cmd_kill(game, _args) -> None:
    game.kill_player()
    print("suicide command sent")


def cmd_set_lot(game, args) -> None:
    lot, cat, item_id, count = int(args[0]), category(args[1]), int(args[2]), int(args[3])
    host_only = len(args) > 4 and args[4] == "host"
    game.find_tables()
    n = game.patch_rows("ITEMLOT_PARAM_ST", {lot: params.lot_bytes(cat, item_id, count, host_only)})
    print(f"lot {lot}: {n} copies rewritten")


def cmd_set_shop(game, args) -> None:
    row, cat, item_id = int(args[0]), category(args[1]), int(args[2])
    game.find_tables()
    n = game.patch_rows("SHOP_LINEUP_PARAM", {row: params.shop_bytes(cat, item_id)})
    print(f"shop row {row}: {n} copies rewritten")


def cmd_rename(game, args) -> None:
    print(f"{game.rename_text(args[0], args[1], args[2])} copies rewritten")


def cmd_text_refs(game, args) -> None:
    """Find the entry's text and every 8-byte value in memory that points at it (or at its key)."""
    m = game.memory
    needle = args[0].encode("ascii") + b"\0"
    for hit in m.find_guest([needle], limit=8)[needle]:
        tail = m.read(hit + len(needle), 96)
        hash_end = tail.find(b"\0")
        text_at = hit + len(needle) + hash_end + 1
        text = tail[hash_end + 1:].split(b"\0")[0]
        print(f"key at {hit:#x}, text at {text_at:#x}: {text!r}")
        for target in (hit, text_at):
            refs = m.find_guest([struct.pack("<Q", target)], limit=16)[struct.pack("<Q", target)]
            print(f"   pointers to {target:#x}: {[hex(r) for r in refs]}")


def cmd_mark(game, args) -> None:
    value = int(args[0], 16)
    game.memory.write(game.memory.u64(A.FLAG_MANAGER) + IDENTITY_OFFSET, struct.pack("<Q", value))
    show_state(game)


def cmd_noreq(game, args) -> None:
    game.find_tables()
    n = game.patch_rows("EQUIP_PARAM_WEAPON_ST", {int(args[0]): {params.WEAPON_REQUIREMENTS: bytes(4)}})
    print(f"{n} copies rewritten")


COMMANDS = {"state": cmd_state, "watch": cmd_watch, "tables": cmd_tables, "give": cmd_give, "remove": cmd_remove,
            "inventory": cmd_inventory, "nexus": cmd_nexus, "kill": cmd_kill, "set-lot": cmd_set_lot,
            "set-shop": cmd_set_shop, "rename": cmd_rename, "text-refs": cmd_text_refs, "mark": cmd_mark,
            "noreq": cmd_noreq}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        raise SystemExit(__doc__)
    game = DemonsSoulsGame(LIVE_FILE)
    game.attach()
    try:
        COMMANDS[sys.argv[1]](game, sys.argv[2:])
    finally:
        game.detach()


if __name__ == "__main__":
    main()
