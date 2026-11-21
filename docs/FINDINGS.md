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
rest follow from the boss soul each map's script gives and from their treasures.

| ID | Maps | Area |
| --- | --- | --- |
| m01 | 00 | Nexus (many spawns, at two heights) |
| m02 | 00-03 | Boletarian Palace 1-1 to 1-4 |
| m03 | 00-03 | Shrine of Storms 4-1 to 4-3 (Adjudicator, Old Hero, Storm King souls; m03_00 has no spawn or treasures) |
| m04 | 00-02 | Tower of Latria 3-1 to 3-3 (Fool's Idol, Maneater, Old Monk souls; the fork's notes: m04_01 c0000_0001 is at the Maneater fog gate) |
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

**Corrected 2026-11-21:** the rule below (flag 10240 + 512 * SS + MSB index) held only for the treasures first
checked. A pickup sets 10240 + 512 * SS + n with n from Bluepoint's level data; only 1-2 and 4-3 follow the MSB
order. The true flags were measured from the game's treasure records (see "Treasure records" below) into
`data/treasure_flags.json`.

Old rule, for the record: treasure `i` of map `mWW_SS_00_00` sets flag 10240 + 512 * SS + i.

| Pickup | Map, treasure | Flag | Live byte, bit | Saved byte, bit |
| --- | --- | --- | --- | --- |
| Late Moon Grass x2 | m02_00 #2 | 10242 | `+0x500`, 2 | `+0x2e1c`, 2 |
| Crescent Moon Grass x3 | m02_00 #3 | 10243 | `+0x500`, 3 | `+0x2e1c`, 3 |
| Unknown Soldier's Soul | m02_00 #4 | 10244 | `+0x500`, 4 | `+0x2e1c`, 4 |
| Throwing Knife x10 | m02_01 #2 | 10754 | `+0x540`, 2 | `+0x2e5c`, 2 |
| Half Moon Grass x3 | m02_01 #1 | 10753 | `+0x540`, 1 | `+0x2e5c`, 1 |

### Flag ranges

| Flags | Kind | Read from another world |
| --- | --- | --- |
| 0-3199 | the world's own (event script flags such as 37, 582, one-time NPC deaths) | saved block `+0x8d0` |
| 3200-8191 | global (boss kills and souls: 4224, 4252, ...) | live |
| 8192-12287 | the world's own (treasures from 10240) | saved block `+0x2b1c` |
| 12288-18047 | global (shop purchase counters from 14984, ...) | live |

Lua flag ids (`proxy:SetEventFlag(n, true)`, `CompleteEvent(n)`, a `once` event's own id) are these ids.

### Bosses (verified on Tower Knight, 2026-11-20)

- The kill: the script's `proxy:OnCharacterDead(4224, 801, "OnEvent_4224", once)` (801 is Tower Knight's MSB
  entity id) set flag 4224 when he died.
- The soul: `OnEvent_4252_1` gives the Iron Demon's Soul (`GetRateItem(10111)`) and sets 4252, when the archstone
  is touched (not on the kill). Flag 4252 came on with the soul.
- Ordinary enemies' deaths set world flags (850-870 in 1-2) that clear when the area resets: not locations.

### Location table

`tools/build_locations.py` writes 570 locations to `work\locations.json`:

| Type | Count | Source | Flag |
| --- | --- | --- | --- |
| treasure | 484 | MSB treasure events (15 more hold nothing) | 10240 + 512 * sub-map + index |
| event | 66 | Lua `GetRateItem(lot)`: all 16 boss souls, keys, gifts | the rewarding function's `SetEventFlag`, `CompleteEvent`, or its `once` event id |
| enemy | 6 | Lua `OnCharacterDead(flag, entity, ..., once)` with a guaranteed drop: 5 Primeval Demons (Colorless Demon's Soul), the Fat Officer (Grey Demon's Soul) | the death flag |
| shop | 14 | ShopLineupParam rows with limited stock | `eventFlag`: an 8-bit purchase counter (byte `flag // 8`) |

Not covered yet:
- NPC trades and gifts: Sparkly the Crow (ItemLot 20000-20018), Blige's trades (10219-10228), a few NPC gifts.
  They run through the compiled talk scripts (`script\talk\*.talkesdbnd`, ESD).
- Remake additions (ItemLot rows named "BP - ...": Penetrator armor, collectible coins, new Sparkly trades). Their
  items are not in the PS3 text files and they are not placed by the original-format MSB/Lua data.
- The two dragon souls (Small/Large Flame-Scale Demon's Soul, given through an NPC state list) and Crystal
  Lizards (their persistence is not in the Lua scripts).
- The final soul choice in the Nexus (left out on purpose).

## Client mechanisms (test session 2026-11-20, fresh character, all verified in game)

| Mechanism | How | Result |
| --- | --- | --- |
| Finding loaded data | `GameMemory.find_guest`: only pages in the working set (`QueryWorkingSetEx`), skipping GPU (write-combined) memory; about 30 s | the game's data sits in mapped views at 0x2_0000_0000 and up, not in the 13.8 GB view at 0x9000200000 |
| Loaded params | 2 copies each of ItemLotParam (`0x24fd147a0`, `0x3327aea90` this run), EquipParamWeapon, EquipParamGoods, raw file layout (type name at +0x0c); ShopLineupParam not found by its type name yet | |
| Rewriting a lot | `session.py set-lot` writes the row in both copies | **treasure contents are fixed when the area loads**: a patch shows only after a reload (Exit Game, Continue). Then the pickup popup and the item are the new ones |
| Item names | the remake's ctxt table is loaded twice as `GOODS_NAME_<id>\0<hash>\0<name>\0`; overwriting the name changes the inventory name at once | longer names need the lookup redirected (not done) |
| Receiving an item | `gamecall.py`: patch `cp11_setShopLvl`'s callback to call 0x900216980(esi=category, edx=id, ecx=count), trigger with `gamecmd +cp11_setShopLvl`, restore | the vanilla "item get" popup and the item; no crash |
| Inventory | adds go through 0x9002916b0 into the inventory at player data (`[[0x9027e6948]+0x10]`) +0x130: entries `[+0x260]`, slot count `[+0x258]` (2048), 32 bytes each: category, item id, count, slot index, ... | weapon ids carry the upgrade level (base id + level) |
| Stat requirements | zero EquipParamWeapon `proper*` in the loaded copy (only one of the two copies had the row) | an under-leveled weapon swings normally |
| DeathLink | `gamecmd +cp11_playerSuicide` (callback 0x900346370 calls 0x900328570 on the player ChrIns, `[0x9027cf378]+0x258`) | **kills the player** (Nexus); does nothing in the tutorial, where death is blocked. Setting HP to 0 (`cp11_setCurrentStats ... 0`) only empties the bar |
| Kick to the Nexus | `warp m01_00_00_00 c0000_0001`, then Exit Game and Continue | works. `cp11_loadLevel 1 0 forceReload=true ...` did nothing |

Other: reloading in the tutorial resets the tutorial. `cp11_addGoods 1003 47` did not show up in the inventory.

## Game data in the dump

`cp11demonssouls\dvdroot` holds the original game's data: `param\gameparam\gameparam.parambnd` (ItemLotParam and
the other params), `script\*.lua` (event scripts, plain text, translated by Bluepoint), `msg\<language>\*.msgbnd`,
`map\mapstudio\*.msb` (64-bit remake layout). The game writes its own log to `<game folder>\logs`.

## Found in the eboot for the client (2026-11-21, static analysis; not yet checked in game)

- **Lua bindings:** `tools/lua_bindings.py` lists all 943 `proxy:` functions with their native handlers
  (`work/lua_bindings.txt`). Each binding is a 0x18-byte static object (+0x8 handler), and the code fills the NEXT
  binding's fields right after registering one, so handlers are matched by the object's address. (The old note
  "SetEventFlag handler 0x900216d10" was off by one: 0x900216d10 is SetAreaEventFlag, SetEventFlag is 0x900216ca0.)
- **WarpNextStage(area, block, 0, 0, spawn event)** (0x900216300): stores the map id into GameMan (`[0x9027bf378]`
  +0xc), the spawn event into +0x90, the warp request byte +0x8 = 1. The archstones use it
  (`BP_WarpToSelectedSlot`); the Warp miracle uses `WarpNextStage(1, 0, 0, 0, -1)`. Nexus spawn events in front of
  each world's archstone: 1006 Boletaria, 1010 Stonefang, 1008 Latria, 1007 Shrine, 1009 Valley.
- **The map the player is in** (what the save stores as MAPUID, and what `BP_GetAreaId` reads):
  `[0x9027df318]`: +0x8 block list (count +0x10, blocks at +0x18), +0x60 the current block's index; a block's map
  id at +0x228 (0x02010000 = m02_01_00_00).
- **Death count:** `[0x9027e6948]` +0x94 (`AddDeathCount` -> 0x900448620). `OnEvent_4000` (global_event.lua) counts
  every player death.
- **Inventory:** `[[0x9027e6948] + 0x10] + 0x130`: slot count +0x128, entries +0x130 (32 bytes: category, id,
  count, ...). `RemoveInventoryEquip(category, id)` (0x90021b9d0) removes one.
- **Goal:** False King Allant's death sets flag 70 (world 1): `OnCharacterDead(70, 821)` in
  m01_00_00_00_eventboss.lua.
- **Text lookup:** keys like `GOODS_NAME_%d` are hashed with FNV-1a 32 on upper-cased bytes (0x900863ff0) and looked
  up in hash tables (0x900866150 -> 0x90086d280: buckets at +0x78, count +0x80, nodes with the hash at +0x0 and the
  next node at +0x70). Longer names would need a node's text pointer redirected (to be found in game).
- **Shop lineup param:** its type name is `SHOP_LINEUP_PARAM` (no `_ST`), which is why the earlier search missed it.
- **Free event flags:** 16964-17799 (`tools/check_free_flags.py`); the client keeps the save's state there.
- **The remake's params grew:** EquipParamGoods rows are 72 bytes (PS3 paramdef 64), EquipParamWeapon 184 (176),
  EquipParamProtector 256 (144), Magic 56 (48); the PS3 fields keep their offsets (requirement removal worked).

## The emulator (chenxiao07 fork, for the launcher)

- `kyty_emulator.exe --game <folder>` mounts that folder as `/app0`, so a launcher can point it at a mirror of the
  game folder with changed files (params, text, scripts) without touching the original.
- Saves go to `_SaveData\<title id>` under the emulator's working folder (`src/libs/libSaveData.cpp`), with the
  fork's own backups in `_SaveData\.kyty-backup`. A different working folder gives separate saves.
- `gamecmd` keeps one pending console command: a new one replaces a pending one (`QueueCommand`), and it runs on the
  next pad read.

## Test session 2026-11-21 (client mechanisms; KytyPS5 v20261120)

| Mechanism | Result |
| --- | --- |
| Title screen | no character pointer: the client reads "not in game" |
| Current map | MAPUID from the map manager; it changes on the border when walking from Phalanx's arena into the Lord's Path (m02_00 <-> m02_01), both ways |
| Param tables | all found in 29 s: ItemLotParam x2, `SHOP_LINEUP_PARAM` x2, EquipParamWeapon x1, EquipParamGoods x1 |
| Batched item-get | 2 and 8 items in one call: one popup each, in order |
| `RemoveInventoryEquip` | removes the item |
| Shop row rewrite | Boldwin's Dagger row sold Full Moon Grass (price kept, row unlimited) |
| Client flags in the save | written, then the title screen clears memory, Continue reloads them from the save: persisted |
| Death counter | +1 about 6 s after `cp11_playerSuicide`, before the respawn load |
| `WarpNextStage(1, ...)` from the stub | grey loading screen, then the Nexus in front of world 1's archstone |
| Text redirection | a 60-character item name shows whole in the inventory list and header |
| Item icon | EquipParamGoods `iconId` is ignored by the remake (the icon follows the item id); a changed id gives "?" in the large panel |
| Goods 9998 | one at most: a second grant gives nothing (no popup) |
| Full Moon Grass | 2 held + 25 given = 25 shown (the rest probably went to storage) |
| Whole client, 2-player seed | wrong-slot save refused; new character claimed in the tutorial; tables found, texts set, items placed; other worlds' items popped as "Archipelago Item" and were removed; own items given once (server copies skipped) |

The debug warp serves a copy of the save made when it is armed, so a claim made after arming is not in it (the
client then asks for `/claim`).

### Treasure records (how the true flags were found)

While a world is loaded the game holds a record for every treasure of all its blocks (`tools/map_treasures.py`):
+0x0 ordinal, +0x4 entity (0x20000000 + block << 24 | n), +0x8 the pickup flag, +0xc item slots, +0x10 five lot ids,
+0x24 the items given now (the client's rewrites show there). Most sit behind the allocator qword 0x90260e038
(at -0x30); every record is also listed in object pointer arrays. Scans of every world (and of a second character
for 1-1's corpses the first had looted) matched every MSB treasure with an item. Not matched:
- treasures whose lots are empty in the remake (world-tendency corpses in Stonefang and Latria, second lots of two
  Prison of Hope corpses): not locations, no records;
- the Prison of Hope key corpses (the keys are given by script events) and one Nexus corpse (lot 10816);
- the tutorial: no records when warped into it. Its 13 treasure locations keep the index rule, marked
  `flag_unverified`, and the client does not report them until measured.
- In the Shrine of Storms the record's block byte is one less than the map (its maps start at m03_01); the flag
  gives the map.
