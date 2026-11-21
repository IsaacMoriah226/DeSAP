"""Check that the event flags the client keeps its state in (apworld client/flags.py: 16964-17799) are used by
nothing in the game: no number literal in the Lua scripts (comments stripped), no param flag field, and no call of
the eboot's flag functions with a constant id in that range.

  python -I tools/check_free_flags.py [<eboot.elf>]
"""

from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

import capstone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from desap import souls  # noqa: E402
from desap.events import read_script  # noqa: E402
from desap.gamedata import GameData  # noqa: E402

FREE = range(16964, 17800)
FLAG_FUNCTIONS = {0x9002A7400, 0x9002A7460, 0x9002A7550, 0x9002A7600}  # set/get by id and their callers' helpers
BASE, FILE_OFFSET = 0x900000000, 0x4000


def main() -> None:
    game = GameData()
    problems = []
    for path in sorted((game.dvdroot / "script").glob("*.lua")):
        for m in re.finditer(r"(?<![\w.])(\d{5})(?![\w.])", read_script(path)):
            if int(m.group(1)) in FREE:
                problems.append(f"lua {path.name}: {m.group(1)}")
    for name, file in game.params.items():
        try:
            paramdef = souls.load_paramdef(name)
            rows = souls.read_param(file.data, paramdef, extended=True).rows
        except (KeyError, FileNotFoundError, ValueError):
            continue
        fields = [f.name for f in paramdef.fields if "flag" in f.name.lower() or "event" in f.name.lower()]
        for row in rows:
            for field in fields:
                if row[field] in FREE:
                    problems.append(f"param {name} row {row.id} {field} = {row[field]}")
    elf = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Dev\DeSArchi\work\eboot_01.007.000.elf").read_bytes()
    code = elf[FILE_OFFSET:FILE_OFFSET + 0x2000000]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for m in re.finditer(rb"[\xb8-\xbf](.{4})", code, re.S):  # mov r32, imm32
        value = struct.unpack("<I", m.group(1))[0]
        if value not in FREE:
            continue
        address = BASE + m.start()
        for ins in md.disasm(code[m.start():m.start() + 48], address):
            if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
                if int(ins.op_str, 16) in FLAG_FUNCTIONS:
                    problems.append(f"eboot {address:#x}: flag call with {value}")
                break
    for problem in problems:
        print(problem)
    print(f"{len(problems)} uses of flags {FREE.start}-{FREE.stop - 1}")


if __name__ == "__main__":
    main()
