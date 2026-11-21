# Demon's Souls Remake Setup Guide

This world needs the PS5 remake (PPSA01341, game version 01.007.000) running on the KytyPS5 emulator
(chenxiao07 fork), on Windows. The client is in testing: expect rough edges.

## What you need

- KytyPS5 (chenxiao07 fork) with the game working.
- Archipelago 0.6.0 or newer, with `demons_souls.apworld` installed (double-click it, or put it in
  `custom_worlds`).

## Starting a game

1. Turn on the emulator's live control: in KytyLauncher's extra options (Advanced page) add
   `-Set KYTY_LIVE_FILE=%LOCALAPPDATA%\DemonsSoulsAP\live.txt` (write the folder out in full if the launcher does
   not expand it). The client looks for that file; `/livefile <path>` in the client changes it.
2. Start the game in the emulator.
3. Open the Archipelago Launcher, then **Demon's Souls Client**, and connect to the server with your slot name.
4. Start a **new character**. The client claims it for your slot in the tutorial. Keep using that save for this
   seed; the client refuses saves that belong to another slot. `/claim` uses a save that already has progress.
5. The first time, the client spends about 30 seconds finding the game's item tables, then places the items.
   Pickups lying in the area you are in change after its next loading screen; everything after that is
   randomized as you go.

## In play

- Items for other players appear as **Archipelago** and vanish from your inventory; your own items appear as
  themselves. Items you receive pop up like any pickup.
- Parts of the world you have not unlocked send you back to the Nexus.
- `/game` shows what the client sees (map, save, placement).
