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

Details of each test: `docs/FINDINGS.md` (test sessions 2026-11-20 and 2026-11-21).

| Mechanism | Status |
| --- | --- |
| Lot rewrite (treasures after a reload), item-get popup, batches (2 and 8 items) | verified |
| Current map, its change on a part border; the kick to the Nexus (`WarpNextStage`) | verified |
| Death counter, DeathLink kill | verified |
| Client flags kept in the save across quit and Continue | verified |
| Shop table found, shop row rewrite | verified |
| `RemoveInventoryEquip`, inventory reading | verified |
| Title screen reads as not in game | verified |
| Item text of any length (name, info, caption) | verified (name); info and caption set the same way |
| Item icon | **not possible** through the param (the remake draws icons by item id) |
| Treasure pickup flags | **fixed**: measured in game for every world but the tutorial (13 tutorial locations are not reported until measured) |
| Placeholder goods 2055 stacks (several other-world items on one corpse each pop up) | **to test** |
| Whole client against a real seed | verified up to the first courtyard of 1-1 (claim, placement, own and other-world pickups, removal); the treasure flag fix and the new placeholder: **to test** |

## Next test session

1. A new character: in the tutorial (played normally, not warped in), `tools/map_treasures.py` to measure the
   tutorial's 13 treasure flags.
2. The whole client against a local two-player seed: the 1-1 pickups that were reported wrongly (Mail Breaker
   corpse, barrels corpse) and a corpse with several other-world items (several "Archipelago Item" popups, all
   removed).
3. A received weapon with auto-upgrade; a received world lock opening its part.

`tools/session.py` must not run while the client runs (both drive the same game-call stub).

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
