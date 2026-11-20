"""Turn a decrypted PS5 eboot (SCE ELF, e_type 0xFE10) into a plain x86-64 ELF that Ghidra's stock loader accepts.

- e_type becomes ET_DYN so Ghidra treats it as position independent (import it with image base 0x900000000,
  where KytyPS5 maps the game, so addresses match the emulator's and the fork's notes).
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


def convert(data: bytearray) -> list[str]:
    if data[:4] != b"\x7fELF" or data[4] != 2:
        raise SystemExit("not a 64-bit ELF")
    e_type, e_machine = struct.unpack_from("<HH", data, 16)
    if e_machine != 62:
        raise SystemExit(f"not x86-64 (e_machine {e_machine})")
    notes = [f"e_type {e_type:#x} -> 0x3"]
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
