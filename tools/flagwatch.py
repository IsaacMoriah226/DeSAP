"""Print every change of the game's event flags while it runs (Demon's Souls 01.007.000 on KytyPS5).

The flag manager (pointer at 0x9027bf328; setter 0x9002a7460, Lua SetEventFlag's): 3200 bits per world (1..8),
the current world's live bits at +0 (400 bytes), each world's stored bits at +0x8d0 + (world - 1) * 0x190,
the current world's number at +0x3cd3. A bit n of a block is byte n // 8, bit n % 8 (LSB first).

Usage: python -I flagwatch.py [seconds]   (default: until Ctrl+C); also logs the player's position for context.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apworld" / "demons_souls"))
from client.memory import GameMemory  # noqa: E402

FLAG_MAN_PTR = 0x9027bf328
LIVE, STORED, WORLD = 0x0, 0x8D0, 0x3CD3
BLOCK = 0x190
SIZE = 0x3D00


def describe(offset: int, bit: int) -> str:
    if offset < BLOCK:
        return f"live flag {offset * 8 + bit}"
    if STORED <= offset < STORED + 8 * BLOCK:
        world = (offset - STORED) // BLOCK + 1
        return f"world {world} stored flag {((offset - STORED) % BLOCK) * 8 + bit}"
    return f"manager +{offset:#x} bit {bit}"


def main() -> None:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else float("inf")
    with GameMemory() as game:
        manager = game.u64(FLAG_MAN_PTR)
        print(f"flag manager {manager:#x}, world {game.u8(manager + WORLD)}", flush=True)
        before = game.read(manager, SIZE)
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            time.sleep(0.25)
            try:
                current = game.u64(FLAG_MAN_PTR)
                if current != manager:  # (a reload may make a new manager)
                    manager = current
                    print(f"{time.strftime('%H:%M:%S')} new flag manager {manager:#x}", flush=True)
                    before = game.read(manager, SIZE)
                    continue
                now = game.read(manager, SIZE)
            except OSError:
                continue  # between areas
            if now == before:
                continue
            stamp = time.strftime("%H:%M:%S")
            for i, (a, b) in enumerate(zip(before, now)):
                if a == b:
                    continue
                for bit in range(8):
                    if (a ^ b) >> bit & 1:
                        state = "ON " if b >> bit & 1 else "off"
                        print(f"{stamp} {state} {describe(i, bit)}", flush=True)
            before = now


if __name__ == "__main__":
    main()
