# Demon's Souls Remake Setup Guide

This world needs the PS5 remake of Demon's Souls (PPSA01341, game version 01.007.000) running on the KytyPS5
emulator (chenxiao07 fork), on Windows.

## What you need

- Windows 10 or 11.
- Archipelago 0.6.8 or newer.
- KytyPS5 (chenxiao07 fork, a 2026-11-18 build or later) with KytyLauncher, set up so the game runs for you.
- Your own dump of the game (PPSA01341, 01.007.000).
- `demons_souls.apworld`, installed: double-click it, or put it in Archipelago's `custom_worlds` folder.

## Playing

1. Open the Archipelago Launcher and click **Demon's Souls Launcher**.
2. The first time, choose your `KytyLauncher.exe` (**Browse...**). Your emulator settings are used as they are.
3. Enter the server, your slot name and the password, if any, and click **PLAY**. The launcher connects, prepares
   its own copy of your emulator setup (with its own saves: your normal saves are never touched) and starts the
   game.
4. At the title, wait for **Ready!** (top left of the screen, and on the launcher): the game pauses for a few
   seconds while the items are placed.
5. Start a **New Game**. The client ties the new character to your slot in the tutorial. Next time: PLAY, wait for
   Ready!, Continue.

## In play

- Items for other players look like a Nexial Binding, named after what they are on nearby corpses and chests
  ("Archipelago Item" for boss rewards, "[AP] Item for another world" in shops); the client takes them out of your
  inventory once sent. Items you receive pop up like any pickup.
- Parts of the world you have not unlocked send you back to the Nexus. The game's own unlocks apply on top
  (Phalanx for the other worlds, the previous boss for x-n, another world's archdemon for 1-3).
- The overlay shows what you find, send and receive; drag it anywhere, its gear opens its settings.
- **MAP TRACKER** on the Play page (or `/tracker`) opens a 3D map of each world in your browser, with every
  location in or out of logic and your position.
- Universal Tracker works too, with no YAML.
- `/game` shows what the client sees; `/claim` uses a save with progress that was not started with Archipelago.
