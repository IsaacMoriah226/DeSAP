# Demon's Souls (PS5) for Archipelago

An [Archipelago](https://archipelago.gg) randomizer for the **Demon's Souls remake** (PPSA01341, game version
01.007.000) running on the [KytyPS5](https://github.com/chenxiao07/KytyPS5) emulator (chenxiao07 fork), on Windows.
Every corpse, chest, boss reward, one-time enemy drop and limited shop item can hold anyone's item, and the five
worlds open as you find their archstones.

**Status: playtest (0.4.0).** Everything below has been built and played in short sessions; the first full
playthrough is next ([`docs/PLAYTEST.md`](docs/PLAYTEST.md)).

## What you get

- **A launcher** in the Archipelago Launcher (*Demon's Souls Launcher*): pick your KytyLauncher once, enter the
  server and slot, press PLAY. It uses your emulator settings, keeps its own save folder (your normal saves are
  never touched), backs saves up while you play, and pauses the game for a few seconds at the title while it
  places the items, then says **Ready!**
- **World locks**: each part past 1-1 needs its archstone item (`1-2 The Lord's Path` ... `5-3 Rotting Haven`).
- **Items for other players** look like a Nexial Binding and, on corpses and chests, carry their real name
  ("Friend's Moonlight Greatsword"); items you receive pop up as in the game.
- **656 locations**: corpses and chests, boss souls and scripted rewards, one-time enemy drops, limited shop items.
  Goal: the five archdemons, then False King Allant.
- **Options**: randomized starting gear per class (DS3-style), no stat requirements, received weapons upgraded to
  match yours, DeathLink.
- **An in-game overlay** of what you find, send and receive: draggable, adjustable, in a Futura-like face.
- **A 3D map tracker** in your browser: each world's walkable map, every location in or out of logic, your live
  position, your archstones and keys, with Blender-style navigation. The map is built from your own game files.
- **Universal Tracker** support (no YAML needed).

## Play

1. Get the latest **release** (`DeSAP-<version>.zip`): it has `demons_souls.apworld`, an options template and the
   guides.
2. Follow [`docs/PLAYER_GUIDE.md`](docs/PLAYER_GUIDE.md): Archipelago 0.6.8 or newer, KytyPS5 with your own dump of
   the game, then install, choose options, PLAY.

Testing a build? [`docs/PLAYTEST.md`](docs/PLAYTEST.md) lists what to look for.

## Documentation

| | |
| --- | --- |
| [`docs/PLAYER_GUIDE.md`](docs/PLAYER_GUIDE.md) | setting up and playing |
| [`docs/PLAYTEST.md`](docs/PLAYTEST.md) | the first-playthrough checklist |
| [`docs/DESIGN.md`](docs/DESIGN.md) | the design decisions (locations, locks, items, options) |
| [`docs/CLIENT.md`](docs/CLIENT.md) | how the client works: placement, checks, items, the launcher, overlay, tracker |
| [`docs/FINDINGS.md`](docs/FINDINGS.md) | the research log: addresses, flags, file formats, test sessions |
| [`docs/IN_GAME_CHECKS.md`](docs/IN_GAME_CHECKS.md) | location hints still to confirm in game |
| [`docs/SETUP.md`](docs/SETUP.md) | developing: workspace, tools, tests, building a release |

## Repository

- `apworld/demons_souls/`: the world (items, locations, logic, options) and its client (`client/`): everything a
  player installs, as one `.apworld`.
- `desap/`: readers for the game's files (BND3, PARAM, FMG, MSB, Lua events), for the tools.
- `tools/`: building the world's data from the game, research and test-session helpers, the release build.
- `ghidra_scripts/`: scripts used while reverse engineering the eboot.

Nothing from the game is in this repository or in a release: the world's tables are names, ids and flags, and the
tracker's map is built on each player's PC from their own dump.

## Credits

- [Archipelago](https://github.com/ArchipelagoMW/Archipelago) and its community; the Dark Souls Remastered and
  Dark Souls III worlds, for ideas.
- [KytyPS5](https://github.com/chenxiao07/KytyPS5) (chenxiao07 fork), [Paramdex](https://github.com/soulsmods/Paramdex)
  and [SoulsFormats](https://github.com/soulsmods/SoulsFormatsNEXT) for the file formats.
- [Jost](https://github.com/indestructible-type/Jost) by the Jost Project Authors, SIL Open Font License
  (`apworld/demons_souls/data/fonts/Jost-OFL.txt`).
- [three.js](https://threejs.org) (MIT) for the map tracker, loaded from a CDN.
