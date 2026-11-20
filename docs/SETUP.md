# Setup on this PC

Everything lives under `C:\Dev\DeSArchi`.

| Path | What |
| --- | --- |
| `DeSAP\` | this repo (local git, identity isaacmoriah226@gmail.com) |
| `KytyPS5-v20261118\` | the emulator build you play on (saves, shader caches) |
| `KytyPS5-v20261120\` | the latest release, for our testing (no saves or caches yet) |
| `repos\KytyPS5\` | emulator source (chenxiao07 fork, blobless clone) |
| `repos\Archipelago\` | Archipelago source (ArchipelagoMW, blobless clone) |
| `repos\Paramdex\` | param definitions and row names (Demon's Souls is `DES`) |
| `repos\SoulsFormatsNEXT\` | FromSoftware file formats (C#), reference for BND3/PARAM/MSB/DCX |
| `repos\DSAP\` | Dark Souls Remastered Archipelago (MIT), design reference |
| `venv\` | Python 3.12 venv with Archipelago's requirements |
| `tools\ghidra_12.2_PUBLIC\` | Ghidra 12.2 (uses `tools\jdk-25.0.5.1+2`; settings in `work\ghidra-user`) |
| `tools\smithbox\` | Smithbox 2.2.6 (param, map and text editor with Demon's Souls support) |
| `ghidra_projects\DeS_01.007.000` | the analyzed eboot, image base `0x900000000` |
| `work\` | scratch output (converted eboot, logs, live file) |

The game dump is at `C:\Users\Isaac Moriah\Desktop\PPSA01341-app0` (original data in `cp11demonssouls\dvdroot`,
decrypted executable in `decrypted\eboot.bin`).

## Starting things

Archipelago from source:

    C:\Dev\DeSArchi\venv\Scripts\python C:\Dev\DeSArchi\repos\Archipelago\Launcher.py

Ghidra (GUI): `C:\Dev\DeSArchi\tools\ghidra_12.2_PUBLIC\ghidraRun.bat`, then open the project
`C:\Dev\DeSArchi\ghidra_projects\DeS_01.007.000`.

Headless analysis (how the project was made):

    set TEMP=C:\Dev\DeSArchi\work\tmp
    set TMP=C:\Dev\DeSArchi\work\tmp
    python -I DeSAP\tools\sce_elf_to_elf.py <dump>\decrypted\eboot.bin work\eboot_01.007.000.elf
    tools\ghidra_12.2_PUBLIC\support\analyzeHeadless.bat ghidra_projects DeS_01.007.000 -import work\eboot_01.007.000.elf -loader ElfLoader -loader-imagebase 900000000 -processor x86:LE:64:default -cspec gcc

Live control: add `-Set KYTY_LIVE_FILE=C:\Dev\DeSArchi\work\live.txt` to the launcher's extra options (Advanced
page), start the game, then e.g. `python -I DeSAP\tools\live.py "where"`.

## Not installed yet

Building the emulator ourselves (to bring back the F8-F10 warp keys or add a bridge) needs Visual Studio 2022
Build Tools with the C++ workload, LLVM 19.1.7 (clang-cl), and glslang (Vulkan SDK). See
`repos\KytyPS5\build-windows.cmd`.
