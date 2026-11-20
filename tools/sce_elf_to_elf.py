"""Turn a decrypted PS5 eboot (SCE ELF, e_type 0xFE10) into a plain x86-64 ELF that Ghidra's stock loader accepts.

- e_type becomes ET_DYN so Ghidra treats it as position independent (import it with image base 0x900000000,
  where KytyPS5 maps the game, so addresses match the emulator's and the fork's notes).
- R_X86_64_RELATIVE relocations are applied for image base 0x900000000 (pointer tables are zero without them).
- Program headers of SCE-only types become PT_NULL; PT_DYNAMIC also becomes PT_NULL because its tags point
  into SCE dynlib data Ghidra cannot parse.
- The section header fields are cleared (the stored offset points past the end of the file).

Usage: python -I sce_elf_to_elf.py <eboot.bin> <out.elf>
"""

import struct
import sys

PT_LOAD, PT_DYNAMIC, PT_INTERP, PT_NOTE, PT_TLS = 1, 2, 3, 4, 7
PT_GNU_EH_FRAME, PT_GNU_RELRO = 0x6474E550, 0x6474E552
KEEP = {PT_LOAD, PT_NOTE, PT_TLS, PT_GNU_EH_FRAME, PT_GNU_RELRO}


BASE = 0x900000000  # where KytyPS5 maps the eboot
DT_RELA, DT_RELASZ = 7, 8
R_X86_64_RELATIVE = 8


def _segments(data: bytes) -> list[tuple[int, int, int, int, int]]:
    e_phoff = struct.unpack_from("<Q", data, 32)[0]
    phnum = struct.unpack_from("<H", data, 56)[0]
    return [struct.unpack_from("<IIQQQQ", data, e_phoff + i * 56)[:6] for i in range(phnum)]


def _file_offset(segments, vaddr: int) -> int | None:
    for p_type, _flags, offset, va, _pa, filesz in segments:
        if p_type == PT_LOAD and va <= vaddr < va + filesz:
            return offset + (vaddr - va)
    return None


def apply_relative_relocations(data: bytearray) -> list[str]:
    """Fill in the pointers the loader would (R_X86_64_RELATIVE: base + addend) so data tables such as the Lua
    function registry point at their strings and functions. Imports (symbol relocations) stay unresolved."""
    segments = _segments(data)
    dynamic = [s for s in segments if s[0] == PT_DYNAMIC]
    if not dynamic:
        return ["no PT_DYNAMIC: relocations not applied"]
    _t, _f, offset, _va, _pa, filesz = dynamic[0]
    tags: dict[int, int] = {}
    for i in range(filesz // 16):
        tag, value = struct.unpack_from("<qQ", data, offset + i * 16)
        if tag == 0:
            break
        tags.setdefault(tag, value)
    rela = _file_offset(segments, tags[DT_RELA])
    applied = skipped = other = 0
    for i in range(tags[DT_RELASZ] // 24):
        r_offset, r_info, addend = struct.unpack_from("<QQq", data, rela + i * 24)
        if r_info & 0xFFFFFFFF != R_X86_64_RELATIVE:
            other += 1
            continue
        target = _file_offset(segments, r_offset)
        if target is None:  # in .bss (not in the file)
            skipped += 1
            continue
        struct.pack_into("<Q", data, target, BASE + addend)
        applied += 1
    return [f"relocations: {applied} relative applied, {skipped} in .bss skipped, {other} symbol ones left"]


def convert(data: bytearray) -> list[str]:
    if data[:4] != b"\x7fELF" or data[4] != 2:
        raise SystemExit("not a 64-bit ELF")
    e_type, e_machine = struct.unpack_from("<HH", data, 16)
    if e_machine != 62:
        raise SystemExit(f"not x86-64 (e_machine {e_machine})")
    notes = apply_relative_relocations(data)
    notes.append(f"e_type {e_type:#x} -> 0x3")
    struct.pack_into("<H", data, 16, 3)
    e_phoff = struct.unpack_from("<Q", data, 32)[0]
    phnum = struct.unpack_from("<H", data, 56)[0]
    struct.pack_into("<Q", data, 40, 0)  # e_shoff
    struct.pack_into("<HHH", data, 58, 64, 0, 0)  # e_shentsize, e_shnum, e_shstrndx
    for i in range(phnum):
        at = e_phoff + i * 56
        p_type = struct.unpack_from("<I", data, at)[0]
        if p_type not in KEEP:
            struct.pack_into("<I", data, at, 0)
            notes.append(f"phdr {i}: type {p_type:#x} -> PT_NULL")
    return notes


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    data = bytearray(open(sys.argv[1], "rb").read())
    for note in convert(data):
        print(note)
    open(sys.argv[2], "wb").write(data)
    print(f"wrote {sys.argv[2]} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
