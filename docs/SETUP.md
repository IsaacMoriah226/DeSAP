# Developing

How to work on DeSAP: the workspace, the tools, the tests, and building a release. Players need none of this
(see `PLAYER_GUIDE.md`).

## The workspace

The tools expect a workspace folder that holds this repository and its neighbours:

| Path (in the workspace) | What |
| --- | --- |
| `DeSAP\` | this repository |
| `repos\Archipelago\` | an [Archipelago](https://github.com/ArchipelagoMW/Archipelago) source checkout |
| `repos\Paramdex\` | [Paramdex](https://github.com/soulsmods/Paramdex) (param definitions; Demon's Souls is `DES`) |
| `repos\KytyPS5\` | the emulator's source (chenxiao07 fork), for reference |
| `venv\` | a Python 3.12 virtual environment with Archipelago's requirements |
| `work\` | scratch output: the converted eboot, research output, logs, the live-control file |
| `tools\` | Ghidra 12.2 and its JDK 25 (`ghidra_12.2_PUBLIC\`, `jdk-25.0.5.1+2\`), optionally Smithbox |
| `ghidra_projects\` | the analyzed eboot (`DeS_01.007.000`, image base `0x900000000`) |

Paths that differ on your PC go in `DeSAP\local_paths.json` (git-ignored; copy `local_paths.example.json`) or in
environment variables (`DESAP_GAME`, `DESAP_WORK`, `DESAP_ARCHIPELAGO`, `DESAP_PARAMDEX`, `DESAP_PYTHON`,
`DESAP_EMULATOR`); `desap/local.py` reads them. Only two have no default:

- `game`: your dump of the game (the `PPSA01341-app0` folder: original data in `cp11demonssouls\dvdroot`, the
  decrypted executable in `decrypted\eboot.bin`);
- `emulator`: the KytyPS5 build you test with (for `tools/live.py`).

## Archipelago from source

Link the world into the checkout once (a directory junction, so edits apply at once):

    mklink /J repos\Archipelago\worlds\demons_souls DeSAP\apworld\demons_souls

Then, from the workspace:

    venv\Scripts\python repos\Archipelago\Launcher.py

The tests (the game-dependent ones skip without `game`):

    cd repos\Archipelago
    ..\..\venv\Scripts\python -m pytest worlds\demons_souls\test

## The world's data

`tools/build_world_data.py` writes `apworld/demons_souls/data/items.json`, `locations.json` and `equipment.json`
from the game files, the research notes in `work\research\out`, and the measured treasure flags
(`data/treasure_flags.json`). Run it after changing what counts as a location or an item; the JSON files are never
edited by hand. `tools/build_docs.py` writes the location guide (`apworld/demons_souls/docs/locations_en.md`).

## In-game sessions

The client's game access works without Archipelago: `tools/session.py` drives it by hand (state, give, warp,
tables, ...), and `tools/live.py` sends live-control commands. The emulator must run with live control on
(`-Set KYTY_LIVE_FILE=<work>\live.txt` in KytyLauncher's extra options, or the Demon's Souls Launcher's profile).
Don't run `tools/session.py` while the client runs.

## Reverse engineering

Convert the decrypted eboot and import it into Ghidra (how the project was made):

    set TEMP=work\tmp
    set TMP=work\tmp
    venv\Scripts\python -I DeSAP\tools\sce_elf_to_elf.py <game>\decrypted\eboot.bin work\eboot_01.007.000.elf
    tools\ghidra_12.2_PUBLIC\support\analyzeHeadless.bat ghidra_projects DeS_01.007.000 -import work\eboot_01.007.000.elf -loader ElfLoader -loader-imagebase 900000000 -processor x86:LE:64:default -cspec gcc

Ghidra 12.2 needs JDK 25; headless OSGi fails with the default settings folder, so set `application.settingsdir`,
`cachedir` and `tempdir` (VMARGS in `support\launch.properties`) to folders under `work\`.
`tools\ghidra_run.ps1 <Script.java> <args>` runs one of `ghidra_scripts\` on the project, read-only.

## Building a release

1. Run the tests.
2. Set the version in `apworld/demons_souls/archipelago.json` (`world_version`; `minimum_ap_version` is the oldest
   Archipelago it was tested with).
3. Build the kit:

       venv\Scripts\python -I DeSAP\tools\build_apworld.py

   It writes `dist\DeSAP-<version>\` (the `.apworld`, the options template, the guides, the font licence) and
   `dist\DeSAP-<version>.zip`.
4. Check it in a released Archipelago (not the source checkout): copy the `.apworld` into its `custom_worlds`,
   generate with the template (`ArchipelagoGenerate.exe --player_files_path <folder>`), and open the Demon's Souls
   Launcher from its launcher. The released build leaves out some libraries (Pillow, numpy): the client must not
   use them.
5. Publish a GitHub release `v<version>` with `DeSAP-<version>.zip` (and the `.apworld` on its own) attached.
