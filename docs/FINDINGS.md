# Findings

Game: Demon's Souls PS5 remake, PPSA01341, version 01.007.000. Emulator: KytyPS5 v20261120 (chenxiao07 fork).

## Verified in game (2026-11-20, throwaway character in save slot 1)

| Test | Command | Result |
| --- | --- | --- |
| Position | `where` | `x=179.5 y=-1.2 z=-86.2 yaw=1.77` in the tutorial |
| Souls | `gamecmd +cp11_addSouls 1000` | souls went from 2 to 1002 |
| Item grant | `gamecmd +cp11_addGoods 1026 1` | an Unknown Hero's Soul appeared in the inventory |
| Warp | `warp m02_00_00_00 c0000_0001`, then Exit Game and Continue | loaded at Boletaria 1-1's start (cutscene played); `where` gave `17.55 21.17 -159.31 yaw 3.054`, the spawn point exactly; the warp ended when the game saved on m02_00_00_00 |

Notes:
- The game runs one queued console command at a time (one slot in the emulator), so commands go about 1 s apart.
  The client needs a queue for item grants.
- Paramdex's DES row names are machine translations (1026 is listed as "The pure soul of an unnamed warrior");
  item names have to come from the game's own `msg\*\item.msgbnd`.
- The warp works from the tutorial and skips the Nexus story state.

## Dev console commands (usage strings in the eboot)

- `cp11_addWeapon <id> [quantity] [durability]`
- `cp11_addArmor <id> [quantity] [durability]`
- `cp11_addGoods <id> [quantity]`
- `cp11_addAccessory <id> [quantity]`
- `cp11_addSouls [souls]`, `cp11_setSouls`, `cp11_unlockArchstone`, `cp11_unlockAllArchstones`,
  `cp11_loadLevel <world> <level>`, `cp11_equipGoods <id> [slot]`, `cp11_unequipItem <slot>`

## Map IDs

From `tools/list_spawns.py` (50 player spawn points). Only `m02` is confirmed in game.

| ID | Maps | Area (guess unless marked) |
| --- | --- | --- |
| m01 | 00 | Nexus (many spawns, at two heights) |
| m02 | 00-03 | Boletarian Palace 1-1 to 1-4 (m02_00 = 1-1 confirmed) |
| m03 | 00-03 | Tower of Latria (m03_00 has no c0000 spawn) |
| m04 | 00-02 | Shrine of Storms (the fork's notes: m04_01 c0000_0001 is at the Maneater fog gate) |
| m05 | 00-02 | Valley of Defilement |
| m06 | 00-02 | Stonefang Tunnel |
| m08 | 00-02 | tutorial |

## Game data in the dump

`cp11demonssouls\dvdroot` holds the original game's data: `param\gameparam\gameparam.parambnd` (ItemLotParam and
the other params), `script\*.lua` (event scripts, plain text, translated by Bluepoint), `msg\<language>\*.msgbnd`,
`map\mapstudio\*.msb` (64-bit remake layout). The game writes its own log to `<game folder>\logs`.
