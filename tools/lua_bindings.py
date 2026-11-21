"""List the event scripts' `proxy:` functions (Lua bindings) and their native handlers in the eboot.

Each binding is a static 0x18-byte object (+0x0 a type pointer, +0x8 the handler, +0x10 zero) registered by
    mov rax, [rdi]; lea rsi, [binding]; lea rdx, [name]; lea rcx, [UTF-16 name]; call [rax + 0x58]
The object's fields are written by `lea rax, [rip + value]; mov [rip + field], rax` pairs; the code fills the
NEXT binding's fields right after registering one, so the handler is read by the object's address, not by
position. Checked: WarpNextStage's handler (0x900216300) builds a map id from its first four arguments.

  python -I tools/lua_bindings.py [<eboot.elf>] > work/lua_bindings.txt
"""

from __future__ import annotations

import re
import struct
import sys

BASE = 0x900000000
FILE_OFFSET = 0x4000  # the converted ELF's code starts at file offset 0x4000 for address BASE


def main() -> None:
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from desap import local
        path = str(local.path("work") / "eboot_01.007.000.elf")
    data = open(path, "rb").read()

    def address(offset: int) -> int:
        return BASE + offset - FILE_OFFSET

    def cstring(at: int) -> str:
        raw = data[FILE_OFFSET + at - BASE:FILE_OFFSET + at - BASE + 256]
        return raw[:raw.index(b"\0")].decode("latin-1") if b"\0" in raw else "?"

    # lea rax, [rip + a]; mov [rip + b], rax
    stores: dict[int, int] = {}
    for m in re.finditer(rb"\x48\x8d\x05(.{4})\x48\x89\x05(.{4})", data, re.S):
        lea = address(m.start())
        value = lea + 7 + struct.unpack("<i", m.group(1))[0]
        field = lea + 14 + struct.unpack("<i", m.group(2))[0]
        stores[field] = value

    out = []
    # lea rsi, [binding]; lea rdx, [name]; lea rcx, [wide name]; call [rax + 0x58]
    for m in re.finditer(rb"\x48\x8d\x35(.{4})\x48\x8d\x15(.{4})\x48\x8d\x0d(.{4})\xff\x50\x58", data, re.S):
        at = address(m.start())
        binding = at + 7 + struct.unpack("<i", m.group(1))[0]
        name = cstring(at + 14 + struct.unpack("<i", m.group(2))[0])
        if name.isidentifier():
            out.append((name, stores.get(binding + 8), binding, at + 21))
    for name, handler, binding, call in sorted(out, key=lambda e: (e[0], e[2])):
        print(f"{name:40} {hex(handler) if handler else '?':14} binding {binding:#x} reg {call:#x}")


if __name__ == "__main__":
    main()
