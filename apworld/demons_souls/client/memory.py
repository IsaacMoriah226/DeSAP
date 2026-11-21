"""Read and write the game's memory in a running kyty_emulator.exe (Windows, ctypes only; no Archipelago imports,
so DeSAP's tools use this module too).

KytyPS5 runs the game's code natively and maps the eboot at 0x900000000, so a game address is the same number
in the emulator's address space (as in KytyPS5's src/loader/demonsSoulsWarp.cpp and the Ghidra project).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct
from dataclasses import dataclass

EBOOT_BASE = 0x900000000
PROCESS_VM_READ, PROCESS_VM_WRITE, PROCESS_VM_OPERATION, PROCESS_QUERY_INFORMATION = 0x10, 0x20, 0x08, 0x400
TH32CS_SNAPPROCESS = 0x2
MEM_COMMIT = 0x1000
PAGE_NOACCESS, PAGE_GUARD = 0x01, 0x100

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


class _MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_uint64), ("AllocationBase", ctypes.c_uint64),
                ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD), ("RegionSize", ctypes.c_uint64),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]


_k32.OpenProcess.restype = wt.HANDLE
_k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
_k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t,
                                   ctypes.POINTER(ctypes.c_size_t)]
_k32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t,
                                    ctypes.POINTER(ctypes.c_size_t)]
_k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_uint64, ctypes.POINTER(_MEMORY_BASIC_INFORMATION),
                                ctypes.c_size_t]
_k32.VirtualQueryEx.restype = ctypes.c_size_t
_k32.VirtualAllocEx.argtypes = [wt.HANDLE, ctypes.c_uint64, ctypes.c_size_t, wt.DWORD, wt.DWORD]
_k32.VirtualAllocEx.restype = ctypes.c_uint64
_k32.VirtualProtectEx.argtypes = [wt.HANDLE, ctypes.c_uint64, ctypes.c_size_t, wt.DWORD, ctypes.POINTER(wt.DWORD)]
MEM_RESERVE, MEM_PRIVATE = 0x2000, 0x20000
PAGE_EXECUTE_READWRITE, PAGE_READWRITE = 0x40, 0x04
_READABLE = 0x02 | 0x04 | 0x08 | 0x20 | 0x40 | 0x80  # R, RW, WC, XR, XRW, XWC
PAGE_WRITECOMBINE = 0x400
PAGE = 0x1000


class _WSEX(ctypes.Structure):  # PSAPI_WORKING_SET_EX_INFORMATION
    _fields_ = [("VirtualAddress", ctypes.c_uint64), ("Attributes", ctypes.c_uint64)]


_k32.K32QueryWorkingSetEx.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD]
_k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
_k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_wchar_p, ctypes.POINTER(wt.DWORD)]
STILL_ACTIVE = 259


def find_pid(exe: str = "kyty_emulator.exe") -> int:
    snap = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    entry = _PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        ok = _k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == exe.lower():
                return entry.th32ProcessID
            ok = _k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snap)
    raise LookupError(f"{exe} is not running")


@dataclass
class Region:
    base: int
    size: int
    protect: int


class GameMemory:
    def __init__(self, pid: int | None = None, write: bool = False):
        self.pid = pid or find_pid()
        access = PROCESS_VM_READ | PROCESS_QUERY_INFORMATION
        if write:
            access |= PROCESS_VM_WRITE | PROCESS_VM_OPERATION
        self.handle = _k32.OpenProcess(access, False, self.pid)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), f"OpenProcess({self.pid}) failed")

    def close(self) -> None:
        if self.handle:
            _k32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> "GameMemory":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def read(self, address: int, size: int) -> bytes:
        buffer = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t()
        if not _k32.ReadProcessMemory(self.handle, address, buffer, size, ctypes.byref(got)) or got.value != size:
            raise OSError(ctypes.get_last_error(), f"read {size} bytes at {address:#x} failed")
        return buffer.raw

    def write(self, address: int, data: bytes) -> None:
        got = ctypes.c_size_t()
        if not _k32.WriteProcessMemory(self.handle, address, data, len(data), ctypes.byref(got)) or got.value != len(data):
            raise OSError(ctypes.get_last_error(), f"write {len(data)} bytes at {address:#x} failed")

    def u8(self, address: int) -> int:
        return self.read(address, 1)[0]

    def u32(self, address: int) -> int:
        return int.from_bytes(self.read(address, 4), "little")

    def u64(self, address: int) -> int:
        return int.from_bytes(self.read(address, 8), "little")

    def i32(self, address: int) -> int:
        return struct.unpack("<i", self.read(address, 4))[0]

    def write_u32(self, address: int, value: int) -> None:
        self.write(address, struct.pack("<I", value & 0xFFFFFFFF))

    def write_u64(self, address: int, value: int) -> None:
        self.write(address, struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF))

    def pointer(self, address: int, *offsets: int) -> int:
        """Follow a pointer chain: [[address] + offsets[0]] + ...; the last offset is added, not read.
        Raises LookupError on a null pointer."""
        value = self.u64(address)
        for offset in offsets:
            if value == 0:
                raise LookupError(f"null pointer in the chain from {address:#x}")
            value = self.u64(value + offset)
        if value == 0:
            raise LookupError(f"null pointer in the chain from {address:#x}")
        return value

    def alive(self) -> bool:
        code = wt.DWORD()
        return bool(_k32.GetExitCodeProcess(self.handle, ctypes.byref(code))) and code.value == STILL_ACTIVE

    def image_path(self) -> str:
        """The full path of the emulator's executable."""
        size = wt.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not _k32.QueryFullProcessImageNameW(self.handle, 0, buffer, ctypes.byref(size)):
            raise OSError(ctypes.get_last_error(), "QueryFullProcessImageNameW failed")
        return buffer.value

    def alloc(self, size: int, protect: int = PAGE_EXECUTE_READWRITE) -> int:
        address = _k32.VirtualAllocEx(self.handle, 0, size, MEM_COMMIT | MEM_RESERVE, protect)
        if not address:
            raise OSError(ctypes.get_last_error(), f"VirtualAllocEx({size}) failed")
        return address

    def protect(self, address: int, size: int, protect: int) -> int:
        old = wt.DWORD()
        if not _k32.VirtualProtectEx(self.handle, address, size, protect, ctypes.byref(old)):
            raise OSError(ctypes.get_last_error(), f"VirtualProtectEx({address:#x}) failed")
        return old.value

    def find(self, pattern: bytes, start: int = 0, end: int = 1 << 47, limit: int = 16,
             chunk: int = 16 << 20, private_only: bool = True) -> list[int]:
        """Addresses of `pattern` in committed readable memory (the game's heap is private memory)."""
        hits: list[int] = []
        info = _MEMORY_BASIC_INFORMATION()
        address = start
        while address < end and len(hits) < limit and _k32.VirtualQueryEx(
                self.handle, address, ctypes.byref(info), ctypes.sizeof(info)):
            base, size = info.BaseAddress, info.RegionSize
            if (info.State == MEM_COMMIT and info.Protect & _READABLE and not info.Protect & PAGE_GUARD
                    and (not private_only or info.Type == MEM_PRIVATE)):
                at = base
                while at < base + size and len(hits) < limit:
                    n = min(chunk + len(pattern), base + size - at)
                    try:
                        block = self.read(at, n)
                    except OSError:
                        break
                    i = block.find(pattern)
                    while i != -1 and len(hits) < limit:
                        hits.append(at + i)
                        i = block.find(pattern, i + 1)
                    at += chunk
            address = base + size
        return hits

    def resident(self, start: int, end: int, batch: int = 1 << 16) -> list[tuple[int, int]]:
        """(start, end) runs of pages in [start, end) that are in the process's working set (touched memory).
        Reading only these avoids faulting in gigabytes of untouched guest memory."""
        runs: list[tuple[int, int]] = []
        for first in range(start, end, batch * PAGE):
            n = min(batch, (end - first) // PAGE)
            entries = (_WSEX * n)()
            for i in range(n):
                entries[i].VirtualAddress = first + i * PAGE
            if not _k32.K32QueryWorkingSetEx(self.handle, entries, ctypes.sizeof(entries)):
                raise OSError(ctypes.get_last_error(), "QueryWorkingSetEx failed")
            for i in range(n):
                if entries[i].Attributes & 1:
                    page = first + i * PAGE
                    if runs and runs[-1][1] == page:
                        runs[-1] = (runs[-1][0], page + PAGE)
                    else:
                        runs.append((page, page + PAGE))
        return runs

    def find_guest(self, patterns: list[bytes], limit: int = 64) -> dict[bytes, list[int]]:
        """Addresses of each pattern in touched, readable memory (one pass for all patterns). GPU (write-combined)
        and guard pages are skipped; the game's data lives in mapped views at 0x2_0000_0000 and up."""
        import re
        regex = re.compile(b"|".join(re.escape(p) for p in patterns))
        hits: dict[bytes, list[int]] = {p: [] for p in patterns}
        longest = max(len(p) for p in patterns)
        runs = []
        info = _MEMORY_BASIC_INFORMATION()
        address = 0
        while _k32.VirtualQueryEx(self.handle, address, ctypes.byref(info), ctypes.sizeof(info)):
            base, size = info.BaseAddress, info.RegionSize
            if (info.State == MEM_COMMIT and info.Protect & _READABLE
                    and not info.Protect & (PAGE_GUARD | PAGE_WRITECOMBINE)):
                runs += self.resident(base, base + size)
            address = base + size
        for run_start, run_end in runs:
            at = run_start
            while at < run_end:
                n = min((16 << 20) + longest, run_end - at)
                try:
                    block = self.read(at, n)
                except OSError:
                    at += 16 << 20
                    continue
                for m in regex.finditer(block):
                    found = hits[m.group(0)]
                    if len(found) < limit and (not found or found[-1] != at + m.start()):
                        found.append(at + m.start())
                at += 16 << 20
        return hits

    def regions(self, start: int = 0, end: int = 1 << 47) -> list[Region]:
        out = []
        info = _MEMORY_BASIC_INFORMATION()
        address = start
        while address < end and _k32.VirtualQueryEx(self.handle, address, ctypes.byref(info), ctypes.sizeof(info)):
            if info.State == MEM_COMMIT and not info.Protect & (PAGE_NOACCESS | PAGE_GUARD):
                out.append(Region(info.BaseAddress, info.RegionSize, info.Protect))
            address = info.BaseAddress + info.RegionSize
        return out
