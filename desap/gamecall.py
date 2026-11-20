"""Run game functions on the game's own thread, through a borrowed console command.

The emulator's live command `gamecmd +cp11_setShopLvl` runs that console command's callback (0x900452b40) on the
game's pad-reading thread. We patch the callback's first bytes to jump to a stub of ours, which calls a game
function with arguments from a data block and counts the calls. The original bytes go back on uninstall.

The function called: the first Lua GetRateItem binding's handler (0x900216980), (category, item id, count):
it adds the item and shows the game's "item get" popup (call to 0x900485740). Categories as in ItemLotParam:
0 weapon, 0x10000000 armor, 0x20000000 ring, 0x40000000 goods. Unverified in game until the test session.
"""

from __future__ import annotations

import struct
import subprocess
import sys
import time
from pathlib import Path

from .memory import GameMemory, PAGE_EXECUTE_READWRITE

TRIGGER_CALLBACK = 0x900452B40  # cp11_setShopLvl's callback
TRIGGER_COMMAND = "+cp11_setShopLvl"
GIVE_ITEM_FN = 0x900216980
TRIGGER_EXPECTED = bytes.fromhex("554889e5415653488d05fa3d3902")  # the callback's original start
JUMP_SIZE = 12  # mov rax, imm64; jmp rax

DATA = 0x100  # in the stub page: u32 category, id, count, calls


def _stub(base: int) -> bytes:
    code = bytearray()

    def rip_disp(field: int, length: int) -> bytes:  # disp32 to DATA + field from the end of the instruction
        return struct.pack("<i", base + DATA + field - (base + len(code) + length))

    code += b"\x55\x48\x89\xe5"  # push rbp; mov rbp, rsp (aligns the stack for the call)
    code += b"\x8b\x35" + rip_disp(0, 6)  # mov esi, [category]
    code += b"\x8b\x15" + rip_disp(4, 6)  # mov edx, [id]
    code += b"\x8b\x0d" + rip_disp(8, 6)  # mov ecx, [count]
    code += b"\x31\xff"  # xor edi, edi
    code += b"\x48\xb8" + struct.pack("<Q", GIVE_ITEM_FN)  # mov rax, GIVE_ITEM_FN
    code += b"\xff\xd0"  # call rax
    code += b"\xff\x05" + rip_disp(12, 6)  # inc dword [calls]
    code += b"\x31\xc0\x5d\xc3"  # xor eax, eax; pop rbp; ret
    assert len(code) < DATA
    return bytes(code)


class GameCall:
    def __init__(self, game: GameMemory):
        self.game = game
        self.stub = 0
        self.original = b""

    def install(self) -> None:
        current = self.game.read(TRIGGER_CALLBACK, len(TRIGGER_EXPECTED))
        if current[:2] == b"\x48\xb8":
            raise RuntimeError("the trigger is already patched (an earlier run did not uninstall)")
        if current != TRIGGER_EXPECTED:
            raise RuntimeError(f"unexpected code at the trigger ({current.hex()}): another game version?")
        self.stub = self.game.alloc(0x1000)
        self.game.write(self.stub, _stub(self.stub))
        self.original = self.game.read(TRIGGER_CALLBACK, JUMP_SIZE)
        jump = b"\x48\xb8" + struct.pack("<Q", self.stub) + b"\xff\xe0"
        old = self.game.protect(TRIGGER_CALLBACK, JUMP_SIZE, PAGE_EXECUTE_READWRITE)
        self.game.write(TRIGGER_CALLBACK, jump)
        self.game.protect(TRIGGER_CALLBACK, JUMP_SIZE, old)

    def uninstall(self) -> None:
        if self.original:
            old = self.game.protect(TRIGGER_CALLBACK, JUMP_SIZE, PAGE_EXECUTE_READWRITE)
            self.game.write(TRIGGER_CALLBACK, self.original)
            self.game.protect(TRIGGER_CALLBACK, JUMP_SIZE, old)
            self.original = b""

    def give_item(self, category: int, item_id: int, count: int, timeout: float = 10.0) -> None:
        calls = self.game.u32(self.stub + DATA + 12)
        self.game.write(self.stub + DATA, struct.pack("<III", category, item_id, count))
        live = Path(__file__).resolve().parent.parent / "tools" / "live.py"
        subprocess.run([sys.executable, "-I", str(live), f"gamecmd {TRIGGER_COMMAND}"], check=True,
                       capture_output=True)
        deadline = time.monotonic() + timeout
        while self.game.u32(self.stub + DATA + 12) == calls:
            if time.monotonic() > deadline:
                raise TimeoutError("the game did not run the stub")
            time.sleep(0.05)
