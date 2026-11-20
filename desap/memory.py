"""Read and write the game's memory in a running kyty_emulator.exe (Windows, ctypes only).

KytyPS5 runs the game's code natively and maps the eboot at 0x900000000, so a game address is the same number
in the emulator's address space (as in KytyPS5's src/loader/demonsSoulsWarp.cpp and the Ghidra project).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
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

    def regions(self, start: int = 0, end: int = 1 << 47) -> list[Region]:
        out = []
        info = _MEMORY_BASIC_INFORMATION()
        address = start
        while address < end and _k32.VirtualQueryEx(self.handle, address, ctypes.byref(info), ctypes.sizeof(info)):
            if info.State == MEM_COMMIT and not info.Protect & (PAGE_NOACCESS | PAGE_GUARD):
                out.append(Region(info.BaseAddress, info.RegionSize, info.Protect))
            address = info.BaseAddress + info.RegionSize
        return out
