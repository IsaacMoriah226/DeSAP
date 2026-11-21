"""Run game functions on the game's own thread, through a borrowed dev console command.

The emulator's live command `gamecmd +cp11_setShopLvl` runs that console command's callback on the game's
pad-reading thread (KytyPS5 live control, see live.py). We patch the callback's first bytes to jump to a stub of
ours, which runs a batch of calls (function address and six integer arguments each) from a data block, then counts
the run. The original bytes go back on uninstall; the stub page stays (a later client reuses it).

Verified in game (2026-11-20, single calls): GIVE_ITEM gives the item with the "item get" popup, no crash.

Data block (at STUB + DATA):
  +0x00  u64 magic MAGIC
  +0x08  u32 number of calls queued (the stub zeroes it when done)
  +0x0c  u32 runs (incremented after each batch)
  +0x10  CALLS x 64-byte entries: function, rdi, rsi, rdx, rcx, r8, r9, return value (rax)
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass

from . import addresses
from .memory import PAGE_EXECUTE_READWRITE, GameMemory

DATA = 0x200
MAGIC = 0x3143475041534544  # "DESAPGC1"
CALLS = 16
ENTRY = 64
JUMP_SIZE = 12  # mov rax, imm64; jmp rax
ORIGINAL = bytes.fromhex(addresses.SIGNATURES[addresses.TRIGGER_CALLBACK])[:JUMP_SIZE]


def build_stub(base: int) -> bytes:
    """The stub's machine code for a page at `base` (rip-relative, so only the data block's place matters)."""
    code = bytearray()

    def rip(target: int, instruction_length: int) -> bytes:
        """disp32 from the end of the instruction being emitted (its first byte is at len(code))."""
        return struct.pack("<i", target - (base + len(code) + instruction_length))

    data = base + DATA
    code += b"\x55"  # push rbp
    code += b"\x48\x89\xe5"  # mov rbp, rsp
    code += b"\x53"  # push rbx
    code += b"\x41\x54"  # push r12        (rsp is 16-byte aligned here: return address + 3 pushes)
    code += b"\x48\x8d\x1d" + rip(data + 0x10, 7)  # lea rbx, [entries]
    code += b"\x44\x8b\x25" + rip(data + 0x08, 7)  # mov r12d, [count]
    code += b"\x41\x83\xfc" + bytes([CALLS])  # cmp r12d, CALLS
    code += b"\x76\x06"  # jbe +6
    code += b"\x41\xbc" + struct.pack("<I", CALLS)  # mov r12d, CALLS (never run past the entries)
    loop = len(code)
    code += b"\x45\x85\xe4"  # test r12d, r12d
    jz_at = len(code)
    code += b"\x74\x00"  # jz done (patched below)
    code += b"\x48\x8b\x7b\x08"  # mov rdi, [rbx + 8]
    code += b"\x48\x8b\x73\x10"  # mov rsi, [rbx + 16]
    code += b"\x48\x8b\x53\x18"  # mov rdx, [rbx + 24]
    code += b"\x48\x8b\x4b\x20"  # mov rcx, [rbx + 32]
    code += b"\x4c\x8b\x43\x28"  # mov r8, [rbx + 40]
    code += b"\x4c\x8b\x4b\x30"  # mov r9, [rbx + 48]
    code += b"\x48\x8b\x03"  # mov rax, [rbx]
    code += b"\xff\xd0"  # call rax
    code += b"\x48\x89\x43\x38"  # mov [rbx + 56], rax
    code += b"\x48\x83\xc3" + bytes([ENTRY])  # add rbx, ENTRY
    code += b"\x41\xff\xcc"  # dec r12d
    code += b"\xeb" + struct.pack("<b", loop - (len(code) + 2))  # jmp loop
    done = len(code)
    code[jz_at + 1] = done - (jz_at + 2)
    code += b"\xc7\x05" + rip(data + 0x08, 10) + b"\0\0\0\0"  # mov dword [count], 0
    code += b"\xff\x05" + rip(data + 0x0C, 6)  # inc dword [runs]
    code += b"\x41\x5c"  # pop r12
    code += b"\x5b"  # pop rbx
    code += b"\x31\xc0"  # xor eax, eax
    code += b"\x5d"  # pop rbp
    code += b"\xc3"  # ret
    assert len(code) < DATA
    return bytes(code)


@dataclass
class Call:
    function: int
    args: tuple[int, ...] = ()

    def entry(self) -> bytes:
        if len(self.args) > 6:
            raise ValueError("at most six arguments")
        values = [self.function, *self.args] + [0] * (6 - len(self.args)) + [0]
        return struct.pack("<8Q", *(v & 0xFFFFFFFFFFFFFFFF for v in values))


class GameCall:
    def __init__(self, game: GameMemory, trigger):
        """`trigger(command)` runs a dev console command in the game (live.LiveControl.gamecmd)."""
        self.game = game
        self.trigger = trigger
        self.stub = 0

    def install(self) -> None:
        current = self.game.read(addresses.TRIGGER_CALLBACK, JUMP_SIZE)
        if current[:2] == b"\x48\xb8" and current[10:12] == b"\xff\xe0":
            stub = struct.unpack_from("<Q", current, 2)[0]
            try:
                ours = self.game.u64(stub + DATA) == MAGIC and self.game.read(stub, 64) == build_stub(stub)[:64]
            except OSError:
                ours = False
            if not ours:
                raise RuntimeError("the console callback is patched by something else")
            self.stub = stub  # an earlier client's stub: reuse it
            self.game.write_u32(self.stub + DATA + 8, 0)
            return
        if current != ORIGINAL:
            raise RuntimeError(f"unexpected code at the console callback ({current.hex()}): another game version?")
        stub = self.game.alloc(0x1000)
        self.game.write(stub + DATA, struct.pack("<QII", MAGIC, 0, 0))
        self.game.write(stub, build_stub(stub))
        jump = b"\x48\xb8" + struct.pack("<Q", stub) + b"\xff\xe0"
        old = self.game.protect(addresses.TRIGGER_CALLBACK, JUMP_SIZE, PAGE_EXECUTE_READWRITE)
        self.game.write(addresses.TRIGGER_CALLBACK, jump)
        self.game.protect(addresses.TRIGGER_CALLBACK, JUMP_SIZE, old)
        self.stub = stub

    def uninstall(self) -> None:
        current = self.game.read(addresses.TRIGGER_CALLBACK, JUMP_SIZE)
        if current[:2] == b"\x48\xb8":
            old = self.game.protect(addresses.TRIGGER_CALLBACK, JUMP_SIZE, PAGE_EXECUTE_READWRITE)
            self.game.write(addresses.TRIGGER_CALLBACK, ORIGINAL)
            self.game.protect(addresses.TRIGGER_CALLBACK, JUMP_SIZE, old)

    def run(self, calls: list[Call], timeout: float = 10.0) -> list[int]:
        """Run the calls on the game's thread, in order; their return values (rax). Blocking."""
        if not self.stub:
            raise RuntimeError("not installed")
        if not 0 < len(calls) <= CALLS:
            raise ValueError(f"1 to {CALLS} calls at a time")
        if self.game.u32(self.stub + DATA + 8):
            raise RuntimeError("an earlier batch is still queued")
        runs = self.game.u32(self.stub + DATA + 12)
        self.game.write(self.stub + DATA + 0x10, b"".join(call.entry() for call in calls))
        self.game.write_u32(self.stub + DATA + 8, len(calls))  # last: the stub reads the count first
        self.trigger(addresses.TRIGGER_COMMAND)
        deadline = time.monotonic() + timeout
        while self.game.u32(self.stub + DATA + 12) == runs:
            if time.monotonic() > deadline:
                self.game.write_u32(self.stub + DATA + 8, 0)  # (a late run then does nothing)
                raise TimeoutError("the game did not run the calls (is live control on?)")
            time.sleep(0.02)
        results = self.game.read(self.stub + DATA + 0x10, len(calls) * ENTRY)
        return [struct.unpack_from("<Q", results, i * ENTRY + 56)[0] for i in range(len(calls))]
