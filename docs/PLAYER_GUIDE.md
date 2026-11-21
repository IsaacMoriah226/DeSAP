# Demon's Souls (PS5) Archipelago — Player Guide

A randomizer for the Demon's Souls remake running on the KytyPS5 emulator, playable in an Archipelago multiworld.
Items anywhere in Boletaria can be anyone's, and other players' worlds hold yours.

## What you need

- **Windows 10 or 11.**
- **Archipelago 0.6.8 or newer**, installed from <https://github.com/ArchipelagoMW/Archipelago/releases>.
- **KytyPS5** (the chenxiao07 fork, a build from 2026-11-18 or later) with **KytyLauncher**, already set up so that
  Demon's Souls runs for you.
- **Your own dump of Demon's Souls, PPSA01341, game version 01.007.000.** Other versions are refused.
- From this kit: `demons_souls.apworld` and `Demon's Souls Remake.yaml`.

Your normal saves are never touched. The randomizer plays from its own copy of your emulator setup with its own save
folder (see [Saves](#saves)).

## What is randomized

656 locations: every corpse and chest pickup (521), the boss souls and scripted rewards (37), the fixed drops of
one-time enemies such as minibosses and black phantoms (85), and the limited shop entries (13). Any of them can hold
an item from your world or someone else's. Crystal Lizards, respawning enemies, NPC quest items and gifts, and the
remake's own additions stay as they are.

**Goal:** slay the five archdemons, then False King Allant below the Nexus.

**Missable locations** only ever hold filler, so you never lose something you need. They are the tutorial (it
cannot be revisited), items that need a world tendency (pure white or black), items behind NPCs who can die or
turn hostile (Biorr, Rydell, Blige, Patches, Yurt, Ostrava, ...), enemy drops lost if not picked up before the
area reloads, the shops, and Soulbrandt (after the final boss).

## 1. Install the world

Double-click `demons_souls.apworld`. Archipelago installs it (it goes in `Archipelago\custom_worlds`). If
double-clicking does nothing, open the **Archipelago Launcher** and choose **Install APWorld**, or copy the file into
`C:\ProgramData\Archipelago\custom_worlds` yourself. Restart the Archipelago Launcher afterwards.

## 2. Your options

Open `Demon's Souls Remake.yaml` in a text editor, or make one with the **Options Creator** in the Archipelago
Launcher (pick *Demon's Souls Remake*):

- `name`: your slot name (what you type in the launcher later).
- **Randomize Starting Loadout** (on by default): every class gets random weapons, shield and armor.
- **Remove Stat Requirements**: use any weapon, shield, catalyst or talisman you find right away, and learn God's
  Wrath, Anti-Magic Field and Recovery from Saint Urbain without the faith he asks. (Spells have no requirement to
  cast: their power comes from your catalyst or talisman.)
- **Auto-Upgrade Received Weapons**: received weapons arrive upgraded to match your best weapon.
- **DeathLink**: when you die, everyone with DeathLink dies, and the other way round.

Send the file to whoever generates the multiworld. They need the `.apworld` installed too.

## 3. Play

1. Open the **Archipelago Launcher** and click **Demon's Souls Launcher**.
2. The first time, click **Browse...** next to KytyLauncher and pick your `KytyLauncher.exe`. Your emulator settings
   (resolution, fullscreen, upscaler) are used as they are.
3. Enter the **server** (for example `archipelago.gg:38281`), your **slot name** and the **password** if there is
   one.
4. Click **PLAY**. The launcher connects, prepares its own copy of your emulator setup, and starts Demon's Souls.
5. **Wait for "Ready!"** On the title screen, a box at the top left of the screen says *Preparing Archipelago:
   wait for Ready!*. The game pauses for a few seconds while the items are placed, then the box says **Ready!**.
   The launcher's Play page says the same.
6. **New Game.** Pick a class: the launcher's **Classes** page shows each class's randomized gear. The game's own
   class preview still shows the usual gear. You get the new gear anyway.
7. The client recognises your new character in the tutorial and ties the save to your slot. Play.

Next time, open the Demon's Souls Launcher, click PLAY, wait for Ready!, and **Continue**.

## While you play

- **Items for other players** look like a Nexial Binding. On corpses and chests they are named after what they
  are when you are near ("Friend's Moonlight Greatsword"); boss and scripted rewards show "Archipelago Item", and
  shop entries "[AP] Item for another world". Pick them up or buy them: they are sent at once, and the client takes
  the token out of your inventory.
- **Items you receive** pop up in game as you'd expect ("item get"), even mid-fight.
- **World locks.** Each part beyond 1-1 needs its archstone item ("1-2 The Lord's Path", "2-1 Smithing Grounds"...).
  Entering a part you don't have sends you back to the Nexus. The game's own unlocks still apply on top: the other
  worlds open after Phalanx, each x-n needs the boss of x-(n-1) dead, and 1-3 (so 1-4) needs an archdemon of
  another world dead.
- **The overlay** shows what you find, send and receive. Drag it anywhere. The gear icon opens its settings:
  size, lines, colours, background opacity, how long messages stay.
- **The map tracker** (MAP TRACKER on the Play page, or type `/tracker` in the launcher) opens in your browser: a 3D
  map of each world with every location in logic (green), out of logic (red) or checked (grey), your position, your
  archstones and keys. Drag to orbit, Shift+drag to pan, scroll to zoom, numpad 1/3/7 for front/side/top, 5 for
  orthographic. It builds the map from your own game files the first time (a moment), and it needs internet (its
  3D library loads from the web).
- **Pickups that already sat in the area** when you connected change after the next loading screen (die, warp, or
  quit and continue). Bosses, scripted rewards and enemy drops are right away.

## Universal Tracker (optional)

[Universal Tracker](https://github.com/FarisTheAncient/Archipelago/releases) works with this world and needs no
YAML. From its latest `Tracker_v...` release, install `tracker.apworld` like this one, open **Universal Tracker** from the Archipelago Launcher and
connect with the same server, slot name and password. It lists what is in logic; it agrees with the map tracker.

## Saves

The randomizer's saves live in `%LOCALAPPDATA%\DemonsSoulsAP\profile\_SaveData`, apart from your normal saves. They are
backed up each time you press PLAY and every 10 minutes while you play (40 kept). The launcher's **Saves** page lists the newest backups and restores one
(close the game first).

One character per slot: the client refuses a save that belongs to another seed or slot, and a save with progress
that wasn't made with Archipelago (`/claim` overrides this for a save you want to use anyway).

## Launcher commands

Type these in the launcher's command line (Archipelago tab):

| Command | What |
| --- | --- |
| `/tracker` | open the map tracker |
| `/game` | what the client sees in the game right now |
| `/claim` | tie the loaded save to your slot anyway |
| `/deathlink` | turn DeathLink on or off for this session |

## If something goes wrong

- **The game seems frozen at the title for more than half a minute.** The client pauses the game only while it
  places items (a few seconds). If the launcher was closed or crashed during that, open it again: it resumes the game.
- **"Waiting for the game ..." forever.** Start the game with the launcher's PLAY button, not from KytyLauncher.
- **Wrong game version.** The client checks the game's code and supports 01.007.000 only.
- **Logs**: `C:\ProgramData\Archipelago\logs\DemonsSoulsLauncher_*.txt` (the newest one). Send it along with any bug
  report.

## Credits

Jost font by the Jost Project Authors (indestructible type), SIL Open Font License (`Jost-OFL.txt`). The map
tracker builds its shapes on your PC from your own game files (the walkable-floor navmeshes); nothing from the game
is included in this kit.
