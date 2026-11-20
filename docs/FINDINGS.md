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

From `tools/list_spawns.py` (50 player spawn points). m02_00 (1-1) and m02_01 (1-2) are confirmed in game; the
rest agree with the items their treasures hold (Prison of Hope keys in m03, Hardstone in m06, and so on).

| ID | Maps | Area |
| --- | --- | --- |
| m01 | 00 | Nexus (many spawns, at two heights) |
| m02 | 00-03 | Boletarian Palace 1-1 to 1-4 |
| m03 | 00-03 | Tower of Latria (m03_00 has no c0000 spawn and no treasures) |
| m04 | 00-02 | Shrine of Storms (the fork's notes: m04_01 c0000_0001 is at the Maneater fog gate) |
| m05 | 00-02 | Valley of Defilement |
| m06 | 00-02 | Stonefang Tunnel |
| m08 | 00-02 | tutorial |

## Event flags

Flag manager: pointer at `0x9027bf328` (getter `0x9002edd40`). Found from the Lua binding of `SetEventFlag`
(registered at `0x90024d96b`, handler `0x900216d10`, setter `0x9002a7460`).

- Flags 0-18047 are one bit array from the manager's start: flag `n` is bit `n % 8` of byte `n // 8`
  (set/get by id: `0x9002a7400` / `0x9002a7550`).
- The current world's live flags: 0-3199 (bytes `+0x0`-`+0x18f`) and 8192-12287 (bytes `+0x400`-`+0x5ff`).
  The current world number is the byte at `+0x3cd3`.
- On leaving a world the game copies those two blocks to the world's saved slots: `+0x8d0 + (w - 1) * 0x190`
  and `+0x2b1c + (w - 1) * 0x200` (`0x9002a7230`). A treasure pickup writes the saved slot at once too.

### Treasure pickups (verified)

Treasure `i` of map `mWW_SS_00_00` (its MSB treasure events in file order) sets **flag 10240 + 512 * SS + i**.

| Pickup | Map, treasure | Flag | Live byte, bit | Saved byte, bit |
| --- | --- | --- | --- | --- |
| Late Moon Grass x2 | m02_00 #2 | 10242 | `+0x500`, 2 | `+0x2e1c`, 2 |
| Crescent Moon Grass x3 | m02_00 #3 | 10243 | `+0x500`, 3 | `+0x2e1c`, 3 |
| Unknown Soldier's Soul | m02_00 #4 | 10244 | `+0x500`, 4 | `+0x2e1c`, 4 |
| Throwing Knife x10 | m02_01 #2 | 10754 | `+0x540`, 2 | `+0x2e5c`, 2 |
| Half Moon Grass x3 | m02_01 #1 | 10753 | `+0x540`, 1 | `+0x2e5c`, 1 |

`tools/build_locations.py` writes all 499 treasures (484 with an item; the largest map has 64) with their flags.

Not covered yet: boss souls and other event rewards (Lua `GetItem`/`AddInventoryItem`), NPC gifts and trades,
enemy drops, shops.

## Game data in the dump

`cp11demonssouls\dvdroot` holds the original game's data: `param\gameparam\gameparam.parambnd` (ItemLotParam and
the other params), `script\*.lua` (event scripts, plain text, translated by Bluepoint), `msg\<language>\*.msgbnd`,
`map\mapstudio\*.msb` (64-bit remake layout). The game writes its own log to `<game folder>\logs`.
