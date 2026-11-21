# Client

The client lives in the apworld (`apworld/demons_souls/client/`), so the `.apworld` is all a player installs. The
Archipelago Launcher lists it as **Demon's Souls Launcher**. It talks to the game through the emulator's memory
(Windows `ReadProcessMemory`/`WriteProcessMemory`) and KytyPS5's live-control file; the emulator is not changed.

## Modules

| Module | What |
| --- | --- |
| `memory.py` | process memory access; scanning touched memory (`blocks`, `find_guest`); `Freeze` (pause the game) |
| `addresses.py` | every address and how it was found; markers for the fast table search; code signatures (other game versions are refused) |
| `live.py` | writes KytyPS5's live-control file (`gamecmd ...`) |
| `gamecall.py` | runs a batch of game functions on the game's own thread: a stub behind a borrowed console command |
| `flags.py` | reads event flags from one snapshot of the flag manager; the client's state kept in the save |
| `params.py` | the param tables the client rewrites, row writes for lots, shops, requirements |
| `game.py` | the bridge: state (character, map, flags, deaths, position, inventory) and actions; finding tables and texts |
| `placement.py` | what each location gives, how a check is seen, placeholders and their names, auto-upgrade (pure) |
| `context.py` | the Archipelago context and the game loop |
| `profile.py`, `settings.py` | the launcher's emulator profile, saves and backups; its settings |
| `gui.py` | the launcher window (Play, Classes, Overlay, Saves pages) |
| `overlay.py`, `gdiplus.py` | the in-game message window, drawn with GDI+ |
| `tracker.py`, `mapshapes.py` | the 3D map tracker: its logic, its local web server, the map shapes |

The modules that read and write the game import nothing from Archipelago, so `tools/session.py` drives them by
hand in test sessions.

## The launcher

- **Profile.** The player picks `KytyLauncher.exe` once. The launcher mirrors that emulator folder into
  `%LOCALAPPDATA%\DemonsSoulsAP\profile` (hard links and directory junctions, the shader caches shared) with its
  own `_SaveData`, so Archipelago saves never mix with vanilla ones. It asks KytyLauncher for its play command
  (`--dry-run`) and runs it from the profile, adding the live-control file. The player's settings (resolution,
  upscaler, ...) apply unchanged.
- **PLAY** connects first, then starts the game. With the game already running from the profile it only connects
  (the button says CONNECT).
- **Saves** are backed up at launch and every 10 minutes (40 kept); the Saves page restores one.
- **Classes** shows each class's starting gear for the seed (the game's own class preview cannot be changed: it is
  Bluepoint's, not the param's).

## How it works

- **Ready before play.** At the title (in the profile: every save there is an Archipelago save) or when a save
  loads, the client pauses the game (every thread but its window's, so Windows never calls it "Not Responding"),
  finds the tables, places the items, and resumes it: about 5 seconds. The overlay says "Preparing Archipelago:
  wait for Ready!" from the moment the client attaches, then "Ready!". If the client dies while the game is
  paused, the next client resumes it (`paused.json` lists the paused threads).
- **Finding the tables.** One pass over the game's memory finds the param list's entries and the text table's
  nodes by their markers (`addresses.py`), from 0x2_0000_0000 to 0x4_0000_0000 where they have always been, all of
  memory otherwise. Only the copy of a param the game's list points to is written (other copies are freed load
  buffers: writing one crashed the game), and every write checks the copy is still live.
- **The save.** The client keeps three things in world 7's saved flag block (the Pantheon, online only, never
  loaded offline), so they are saved with the character and roll back with it:
  - an identity, a hash of (seed, team, slot);
  - how many received items the game has been given;
  - one bit per location for "the game gave this world's item here itself".

  A save with identity 0 is claimed while it is in the tutorial, where every new character starts. Any other
  unclaimed save needs `/claim`; a save with another slot's identity is refused, with a message. That is how the
  client tells which save is loaded.
- **Placement.** Every location's item lot is rewritten:
  - this world's item goes in as itself;
  - another world's item becomes a placeholder: goods 2055, 2057 and 9998 (one per item on the same corpse, in
    location order), with the Nexial Binding's icon (its icon id and the remake's UI link, goods row +64). The
    placeholders take the names of the items of the nearest corpse within 40 m ("Friend's Moonlight Greatsword",
    "... and N more" past three), and the client takes them back out of the inventory;
  - shared lots (Primeval Demons, the Vanguards, two Fat Officials' grass) become empty, and the client gives
    their item by flag;
  - shop rows get goods 2056, "[AP] Item for another world".

  Treasures take their contents when their area loads, so pickups already in the area being played change after
  its next loading screen. Boss souls, scripted rewards and enemy drops read their lot when they are given.
- **Checks.** About 4 times a second the client reads the flag manager and tests each location's flag:
  - treasures: the pickup flag (measured in game for all 521);
  - events: the reward function's flag;
  - one-time enemies: the corpse or death flag;
  - shops: the purchase counter byte.
- **Items.** `items_handling` 0b111: the server sends every item, this world's own included. Items are given
  through the game's own item-get (the popup), up to 4 per call, and the count is kept in the save. A server copy
  of an item the game already handed out is skipped; anything collected some other way (`!collect`, a pickup
  before the area reloaded) is given by the client.
- **World locks.** If the player's map belongs to a part whose lock item has not been received, the client calls
  the archstones' own warp, `WarpNextStage`, to the Nexus; the player lands in front of that world's archstone.
- **DeathLink.** The game's death counter going up is sent out. A received death becomes `+cp11_playerSuicide`,
  held while in the tutorial, where death is blocked.
- **Goal.** Flag 70 (False King Allant dead).
- **Options.**
  - Randomize Starting Loadout: the classes' rows of CharaInitParam (1000-1009), written at the title before a
    character is made. Weapons a class can use, armor of about the same weight that both body types can wear.
  - Remove Stat Requirements: every weapon row's requirements (weapons, shields, catalysts, talismans) and the
    faith Saint Urbain asks before teaching three miracles (MagicParam `faithForGet`). Spells have no requirement
    to cast.
  - Auto-upgrade: a received weapon arrives at the same share of its maximum as the best weapon held (rounded up).

## The overlay

A layered, always-on-top window over the game (KytyPS5's fullscreen is borderless, so it can draw there): the
items this player finds, sends and receives, coloured as Archipelago does, and the Preparing/Ready notice. It
never takes the focus, shows only while the game is in front, can be dragged anywhere, and its gear opens the
launcher's Overlay page (size, lines, colours, opacity, how long messages stay). Drawn with GDI+ (Windows' own),
in Jost Medium loaded from memory: Archipelago's released build has no Pillow.

## The map tracker

`MAP TRACKER` on the Play page (or `/tracker`) opens `http://127.0.0.1:38390/` (the next free port if taken).

- **Map.** `mapshapes.py` builds each world's shape from the player's own dump on first use, about 0.1 s: the
  navmeshes of its maps placed by the MSB, in the MSB's coordinates (the same as the locations' and the player's),
  into `%LOCALAPPDATA%\DemonsSoulsAP\maps`. The game folder comes from KytyLauncher's settings. Nothing from the
  game ships.
- **Logic.** `tracker.py` evaluates the world's own requirement tokens to a fixed point (parts open by their
  archstone rules, bosses reachable in open parts). It agrees with the generator on every case the tests try, and
  with Universal Tracker.
- **Page.** `data/tracker/index.html`: three.js from a CDN, polling `/api/state`. Blender-style navigation
  (orbit, Shift/right-drag pan, zoom to cursor, numpad 1/3/7 views, 5 orthographic, 2/4/6/8 orbit, Home, `.`, an
  axis gizmo), markers by status, the player's position followed live, archstones and keys, rewards and shops
  without a position listed apart, search, an optional reveal of every location's item.

## Status

Details of each test: `FINDINGS.md`.

| Mechanism | Status |
| --- | --- |
| Lot rewrite (treasures after a reload), item-get popup, batches | verified |
| Current map and its change at a part border; the kick to the Nexus | verified |
| Death counter, DeathLink kill | verified |
| Client state in the save across quit and Continue | verified |
| Shop table found, shop row rewrite | verified |
| Treasure pickup flags (all 521 measured), tutorial checks | verified |
| Placeholder icon (Nexial Binding) and names (one per corpse) | verified |
| One named placeholder per item of a corpse | built, to confirm in play |
| Ready gate: pause, placement in about 5 s, overlay and launcher notice | verified |
| Launcher profile, PLAY, CONNECT, starting loadouts in game | verified |
| Overlay; GDI+ drawing in the released Archipelago | verified (drawing in game with GDI+: to confirm) |
| Map tracker: logic, handedness (in game), map built from the dump in the released Archipelago | verified |
| Universal Tracker without a YAML | verified (same in-logic set as the map tracker) |
| Urbain's miracles without the faith | built, to confirm in play |
| Boss souls, scripted rewards, one-time enemy drops, buying a shop item, DeathLink with two players, the goal | the first playthrough (`PLAYTEST.md`) |
