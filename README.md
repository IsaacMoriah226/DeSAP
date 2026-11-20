# DeSAP: Archipelago for Demon's Souls (PS5 remake on KytyPS5)

Private project: an Archipelago world, client and game bridge for Demon's Souls (PPSA01341, game version
01.007.000) running on the [chenxiao07/KytyPS5](https://github.com/chenxiao07/KytyPS5) emulator.

## Plan

| Part | Language | Where |
| --- | --- | --- |
| apworld (items, locations, regions, logic, options) | Python | `apworld/demons_souls/` |
| client (connects to the AP server, watches checks, grants items) | Python | inside the apworld |
| game bridge | the emulator's live control (`KYTY_LIVE_FILE`) now; a C++ addition to the fork later if needed | `tools/live.py` |
| data tools (params, item lots, Lua events, maps) | Python | `tools/` |
| reverse engineering | Ghidra | `C:\Dev\DeSArchi\ghidra_projects` |

How checks and items work (planned):
- **Locations:** per seed, item lots are rewritten so pickups give placeholder items; the client watches the
  pickup event flags in game memory and sends the checks.
- **Received items:** granted with the game's dev console (`+cp11_addWeapon`, `+cp11_addArmor`, `+cp11_addGoods`,
  `+cp11_addAccessory`) through the live command `gamecmd`.

## Layout

- `tools/sce_elf_to_elf.py`: the decrypted eboot as a plain ELF for Ghidra (import at image base `0x900000000`).
- `tools/live.py`: send live-control commands (`where`, `warp MAP SPAWN`, `gamecmd ...`) and print the replies.
- `tools/list_spawns.py`: every warp destination (map and spawn point) from the game's MSB files.
- `desap/`: readers for the game's files (`souls.py`: BND3, PARAM, FMG; `msb.py`: maps), `gamedata.py` (items,
  item lots, treasures with their flags), `memory.py` (reads and writes the running game's memory).
- `tools/build_locations.py`: every treasure location with its event flag, as JSON.
- `tools/flagwatch.py`: print event flag changes live (how the pickup flags were found).
- `tools/ghidra_run.ps1` with `ghidra_scripts/`: run a Ghidra script on the analyzed eboot.
- `docs/SETUP.md`: where every repo and tool lives on this PC and how to start them.
- `docs/FINDINGS.md`: what is verified in game so far (commands, map IDs, data locations).
