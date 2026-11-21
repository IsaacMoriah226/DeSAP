# DeSAP: Archipelago for Demon's Souls (PS5 remake on KytyPS5)

Private project: an Archipelago world, client and game bridge for Demon's Souls (PPSA01341, game version
01.007.000) running on the [chenxiao07/KytyPS5](https://github.com/chenxiao07/KytyPS5) emulator.

## Plan

| Part | Language | Where |
| --- | --- | --- |
| apworld (items, locations, regions, logic, options) | Python | `apworld/demons_souls/` |
| client (connects to the AP server, watches checks, grants items) | Python | inside the apworld |
| game bridge | the emulator's memory and live control (`KYTY_LIVE_FILE`); no emulator change | `apworld/demons_souls/client/` |
| data tools (params, item lots, Lua events, maps) | Python | `tools/` |
| reverse engineering | Ghidra, capstone | `C:\Dev\DeSArchi\ghidra_projects`, `tools/lua_bindings.py` |

How checks and items work: `docs/CLIENT.md` (with what is verified in game and what is still to test).

## Layout

- `tools/sce_elf_to_elf.py`: the decrypted eboot as a plain ELF for Ghidra (import at image base `0x900000000`).
- `tools/live.py`: send live-control commands (`where`, `warp MAP SPAWN`, `gamecmd ...`) and print the replies.
- `tools/list_spawns.py`: every warp destination (map and spawn point) from the game's MSB files.
- `desap/`: readers for the game's files (`souls.py`: BND3, PARAM, FMG; `msb.py`: maps), `gamedata.py` (items,
  item lots, treasures with their flags), `events.py` (Lua rewards and kills).
- `apworld/demons_souls/client/`: the client and its game access (`memory.py`, `gamecall.py`, `game.py`, ...).
- `tools/session.py`: drive the client's game access by hand in test sessions (state, give, warp, tables, ...).
- `tools/lua_bindings.py`: every Lua `proxy:` function with its native handler.
- `tools/check_lot_users.py`, `tools/check_free_flags.py`: safety checks for lot rewrites and the client's flags.
- `tools/build_locations.py`: every treasure location with its event flag, as JSON.
- `tools/flagwatch.py`: print event flag changes live (how the pickup flags were found).
- `tools/ghidra_run.ps1` with `ghidra_scripts/`: run a Ghidra script on the analyzed eboot.
- `docs/SETUP.md`: where every repo and tool lives on this PC and how to start them.
- `docs/FINDINGS.md`: what is verified in game so far (commands, map IDs, data locations).
