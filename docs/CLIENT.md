# Client

The Demon's Souls client lives in the apworld (`apworld/demons_souls/client/`), so the `.apworld` file is all a
player installs; the AP Launcher lists it as **Demon's Souls Client**. It talks to the game through the emulator's
memory (Windows `ReadProcessMemory`/`WriteProcessMemory`) and KytyPS5's live-control file; no emulator change.

## Modules

| Module | What |
| --- | --- |
| `memory.py` | process memory access, the working-set search (`find_guest`) |
| `addresses.py` | every address and how it was found; code signatures (the client refuses other game versions) |
| `live.py` | writes KytyPS5's live-control file (`gamecmd ...`) |
| `gamecall.py` | runs a batch of game functions on the game's own thread: a stub behind a borrowed console command |
| `flags.py` | reads event flags from one snapshot of the flag manager; the client's state kept in the save |
| `params.py` | finds the loaded param tables, builds lot and shop row rewrites |
| `game.py` | the bridge: state (character, map, flags, deaths, inventory) and actions |
| `placement.py` | what each location gives, how a check is seen, weapon auto-upgrade (pure, unit-tested) |
| `context.py` | the Archipelago context and the game loop |

The modules other than `context.py` and `placement.py` import nothing from Archipelago, so `tools/session.py` drives
them by hand in test sessions.

## How it works

- **The save.** The client keeps three things in event flags nothing in the game uses (16964-17799, checked by
  `tools/check_free_flags.py`), so they are saved with the character and roll back with it:
  - an identity, a hash of (seed, team, slot);
  - how many received items the game has been given;
  - one bit per location for "the game gave this world's item here itself".

  A save with identity 0 is claimed automatically while it is in the tutorial, which is where every new character
  starts. Any other unclaimed save needs `/claim`. A save with another slot's identity is refused, with a message.
  This is how the client tells which save file is loaded.
- **Placement.** Once the server answers the location scouts, the client finds the param tables in memory (about
  30 s) and rewrites every location's item lot:
  - this world's item goes in as itself;
  - another world's item becomes a placeholder: goods 9998, renamed "Archipelago", with the Nexial Binding's icon,
    which the client takes back out of the inventory;
  - shared lots (Primeval Demons, the Vanguards, two Fat Officials' grass) become empty, and the client gives
    their item by flag;
  - shop rows get the same treatment.

  Treasures take their contents when their area loads, so the area being played changes only after its next
  loading screen. Boss souls, scripted rewards and enemy drops read their lot when they are given.
- **Checks.** About 4 times a second the client reads the flag manager and tests each location's flag:
  - treasures: the pickup flag;
  - events: the reward function's flag;
  - one-time enemies: the corpse or death flag;
  - shops: the purchase counter byte.
- **Items.** `items_handling` 0b111: the server sends every item, this world's own included. Items are given
  through the game's own item-get (the popup), and the count is kept in the save.

  A server copy of an item the game already handed out is skipped: this world's item, at a location whose lot
  was rewritten, picked up after its area was randomized. Anything collected some other way (`!collect`, a
  pickup before the area reloaded) is given by the client.
- **World locks.** If the player's map belongs to a part whose lock item has not been received, the client calls
  the archstones' own warp, `WarpNextStage`, to the Nexus. It lands in front of that world's archstone.
- **DeathLink.** The game's death counter going up is sent out. A received death becomes `+cp11_playerSuicide`,
  held while in the tutorial, where death is blocked.
- **Goal.** Flag 70 (False King Allant dead).
- **Options.** Stat requirements are removed by zeroing every weapon row's requirements. Auto-upgrade raises a
  received weapon to the same share of its maximum as the best weapon held (rounded up). Spells are not covered
  yet (the remake's Magic rows are 8 bytes longer and the requirement fields are unknown).

## Status

| Mechanism | Status |
| --- | --- |
| Lot rewrite, reload needed for treasures | verified in game (2026-11-20) |
| Item-get popup through the stub | verified (single calls); batches of several: **to test** |
| Requirement removal, text rename (same length), DeathLink kill, Nexus by debug warp | verified |
| Current map (MAPUID) from the map manager, changing when walking into the next part | **to test** |
| `WarpNextStage` to the Nexus from the stub (the kick) | **to test** |
| Death counter | **to test** |
| Client flags 16964-17799 saved with the character | **to test** |
| Shop table (`SHOP_LINEUP_PARAM`) found, shop row rewrite | **to test** |
| `RemoveInventoryEquip` from the stub | **to test** |
| Inventory entry layout (count at +8) | **to test** |
| Title screen: no character pointer (so no false "in game") | **to test** |
| Whole client against a real seed | **to test**; offline: 24 unit tests, and a dry run with a real MultiServer and a fake game |

## Test session plan

Run the emulator with live control on, then `python -I tools/session.py <command>`:

1. `state` at the title screen, in the tutorial, and in the Nexus: is the character pointer null at the title?
   Are the map id and death count right?
2. `watch`, then walk from 1-1 into 1-2 past Phalanx (or across any other part border): does the map change on
   the border?
3. `tables`: are both shop table copies found?
4. `give goods 1000 1 goods 1001 1`: two popups from one batch?
5. `inventory 1000`, then `remove goods 1000 1`.
6. `nexus` in 1-1: does it warp to the Nexus without Exit Game?
7. Die once (`watch` running): does the death count go up?
8. `mark 0123456789abcdef`, rest at an archstone, quit to the title, Continue, `state`: is the identity still
   there?
9. `text-refs GOODS_NAME_9998`: is there a pointer to the text (the way to longer names)?
10. The whole client against a local seed with a new character.

## Planned

### Launcher (our own, styled after KytyLauncher)

- The player picks `KytyLauncher.exe`/`kyty_emulator.exe` once. The launcher reuses the emulator's own settings
  (`launcher-settings.json`) and command line, and adds what Archipelago needs:
  - live control (`KYTY_LIVE_FILE`);
  - its own working folder, so Archipelago saves are separate from vanilla ones. The emulator puts saves in
    `_SaveData` under its working folder; the shader cache and pipeline seeds are linked in with directory
    junctions.
- Fields for server, port, slot name and password. **Launch** connects first, then starts the emulator and the
  client together.
- **Saves:**
  - backups of the Archipelago save folder at connect and every few minutes, kept by count;
  - the client's save identity check gives the "wrong save" message ("load the save you made for this slot").
- **Per-seed game files (to try).** `--game` can point at a mirror of the game folder: directory junctions for
  everything untouched, real files for what changes. With it, every location could carry its own item name
  ("[Player]'s [Item]"), the Nexial Binding icon and shop text, with no in-memory patching and no "reload the
  area" step. First check: does the game read a changed loose `text/ds/_cmn/*.ctxt` or `param` file?

### Universal Tracker and the options creator

- **Universal Tracker:** no option changes the logic and nothing is randomized beyond item placement, so UT can
  rebuild the logic without the player's YAML (`ut_can_gen_without_yaml`). Each location already has a hint text
  (the location guide).
- **Options creator:** the AP Launcher's Options Creator builds YAMLs for any installed world from its options;
  nothing extra needed.

### 3D tracker (experimental)

Feasible. Each map in the dump has its navmesh (`map/<map>/*.nvmbnd`: the walkable surface as triangles), plus
collision (`.hkxfilebnd`) and the original map models (`*.flver`). Each location already has its position from
the MSB.

The plan:
- export one simplified navmesh per map to glTF;
- show it in a local web page (three.js: orbit, pan and zoom like Blender's viewport);
- mark every location as checked, in logic or out of logic, computed by the client with the world's own rules
  from the received items;
- show the progression items, and the player's live position (from the game's memory).

The navmesh reader (DeS NVM format, documented in SoulsFormats) is the first step.
