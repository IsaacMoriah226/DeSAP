"""The in-game message overlay: a borderless, always-on-top, per-pixel transparent window over Demon's Souls that
shows the items this player finds, sends and receives (everything else stays in the launcher's log).

Windows only, ctypes and GDI+ (gdiplus.py; Archipelago's frozen build has no Pillow). The window is a layered
window (UpdateLayeredWindow with a premultiplied BGRA bitmap): crisp text over a background of any opacity. It never takes the focus
(WS_EX_NOACTIVATE), shows only while the emulator's window is in front, can be dragged anywhere, and its gear icon
opens the launcher's overlay settings. KytyPS5's fullscreen is SDL's desktop (borderless) fullscreen, which other
windows can draw over.

Font: Jost Medium (data/fonts/Jost-Medium.ttf, a static instance of the variable Jost.ttf, SIL Open Font License, the
free Futura-style face), loaded from memory (it works from a packed .apworld); Segoe UI only if it were missing.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import pkgutil
import queue
import re
import threading
import time
from dataclasses import dataclass

from . import gdiplus
from .settings import OverlaySettings

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WS_POPUP = 0x80000000
WS_EX_LAYERED, WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80000, 0x8, 0x80, 0x08000000
WM_DESTROY, WM_NCHITTEST, WM_LBUTTONUP, WM_MOUSEACTIVATE, WM_EXITSIZEMOVE, WM_TIMER = 0x2, 0x84, 0x202, 0x21, 0x232, 0x113
WM_APP_QUIT = 0x8001
HTCAPTION, HTCLIENT, MA_NOACTIVATE = 2, 1, 3
ULW_ALPHA, AC_SRC_OVER, AC_SRC_ALPHA = 2, 0, 1
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
user32.GetForegroundWindow.restype = wt.HWND
user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
kernel32.GetModuleHandleW.restype = wt.HMODULE
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE), wt.HDC,
                                       ctypes.POINTER(wt.POINT), wt.COLORREF, ctypes.c_void_p, wt.DWORD]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), wt.HANDLE,
                                   wt.DWORD]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.DeleteDC.argtypes = [wt.HDC]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte), ("SourceConstantAlpha", ctypes.c_ubyte),
                ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


# Archipelago's own text colours (the text client's)
COLORS = {
    "self": (238, 0, 238), "player": (250, 250, 210), "location": (0, 255, 127), "text": (232, 229, 223),
    "progression": (175, 153, 239), "useful": (109, 139, 232), "filler": (0, 238, 238), "trap": (250, 128, 114),
    "dim": (154, 150, 143), "gold": (201, 164, 92),
}


def item_color(flags: int) -> str:
    if flags & 0b001:
        return "progression"
    if flags & 0b010:
        return "useful"
    if flags & 0b100:
        return "trap"
    return "filler"


@dataclass
class Message:
    parts: list[tuple[str, str]]  # (text, colour key)
    born: float


FONT_FILE = "data/fonts/Jost-Medium.ttf"
_font_file: gdiplus.FontFile | None | bool = None
_measure: gdiplus.Canvas | None = None


def load_font(size: float) -> gdiplus.Font:
    """Jost Medium at `size` pixels (Segoe UI if the font file were missing)."""
    global _font_file
    with gdiplus.LOCK:
        if _font_file is None:
            data = pkgutil.get_data(__name__.rsplit(".", 2)[0], FONT_FILE)
            try:
                _font_file = gdiplus.FontFile(data) if data else False
            except OSError:
                _font_file = False
        if _font_file:
            return _font_file.size(size)
        return gdiplus.Font.system("Segoe UI", size)


def text_width(text: str, font: gdiplus.Font) -> float:
    global _measure
    with gdiplus.LOCK:
        if _measure is None:
            _measure = gdiplus.Canvas(1, 1)
        return _measure.textlength(text, font)


class Overlay:
    GEAR = 26  # the gear's square, top right (pixels)
    HEADER = 30

    def __init__(self, settings: OverlaySettings, on_settings, emulator_pid=lambda: 0, on_moved=lambda: None):
        self.settings = settings
        self.on_settings = on_settings  # the gear icon was clicked (called on the overlay thread)
        self.on_moved = on_moved
        self.emulator_pid = emulator_pid
        self.messages: list[Message] = []
        self.banner: tuple[list[tuple[str, str]], float] | None = None  # (parts, until; inf: until removed)
        self.inbox: queue.Queue = queue.Queue()
        self.hwnd = None
        self.thread: threading.Thread | None = None
        self.dirty = True
        self.visible = False
        self.size = (1, 1)

    # --- API (any thread) ----------------------------------------------------------------------------------------

    def start(self) -> None:
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name="overlay", daemon=True)
            self.thread.start()

    def stop(self) -> None:
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_APP_QUIT, 0, 0)

    def push(self, parts: list[tuple[str, str]]) -> None:
        self.inbox.put(parts)

    def set_banner(self, parts: list[tuple[str, str]] | None, seconds: float | None = None) -> None:
        """Pin a notice above the messages (for `seconds`, or until replaced or removed with None). It shows even
        when the messages are turned off: it says whether the game is ready to play."""
        self.banner = None if parts is None else (parts, time.monotonic() + seconds if seconds else float("inf"))
        self.dirty = True

    def refresh(self) -> None:
        """Settings changed: redraw."""
        self.dirty = True

    # --- the window's thread -------------------------------------------------------------------------------------

    def _run(self) -> None:
        instance = kernel32.GetModuleHandleW(None)
        self._proc = WNDPROC(self._wndproc)  # (kept alive)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._proc
        wc.hInstance = instance
        wc.lpszClassName = "DemonsSoulsArchipelagoOverlay"
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))
        user32.RegisterClassW(ctypes.byref(wc))
        s = self.settings
        self.hwnd = user32.CreateWindowExW(WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                                           wc.lpszClassName, "Archipelago", WS_POPUP, s.x, s.y, s.width, 100,
                                           None, None, instance, None)
        user32.SetTimer(self.hwnd, 1, 100, None)
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _wndproc(self, hwnd, message, wparam, lparam):
        if message == WM_NCHITTEST:
            x, y = ctypes.c_short(lparam & 0xFFFF).value, ctypes.c_short(lparam >> 16 & 0xFFFF).value
            rect = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            if rect.right - self.GEAR - 8 <= x <= rect.right and rect.top <= y <= rect.top + self.HEADER:
                return HTCLIENT  # the gear: a click
            return HTCAPTION  # anywhere else: drag
        if message == WM_LBUTTONUP:
            try:
                self.on_settings()
            except Exception:
                pass
            return 0
        if message == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        if message == WM_EXITSIZEMOVE:
            rect = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            self.settings.x, self.settings.y = rect.left, rect.top
            self.on_moved()
            return 0
        if message == WM_TIMER:
            self._tick()
            return 0
        if message == WM_APP_QUIT:
            user32.DestroyWindow(hwnd)
            return 0
        if message == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _game_in_front(self) -> bool:
        pid = self.emulator_pid()
        if not pid:
            return False
        foreground = user32.GetForegroundWindow()
        owner = wt.DWORD()
        user32.GetWindowThreadProcessId(foreground, ctypes.byref(owner))
        return owner.value in (pid, os.getpid())

    def _tick(self) -> None:
        s = self.settings
        while not self.inbox.empty():
            self.messages.append(Message(self.inbox.get(), time.monotonic()))
            self.dirty = True
        if s.seconds > 0:
            alive = [m for m in self.messages if time.monotonic() - m.born < s.seconds + 1.5]
            if len(alive) != len(self.messages) or alive:
                self.dirty = True  # (fading)
            self.messages = alive
        self.messages = self.messages[-max(1, s.lines):]
        if self.banner is not None and time.monotonic() > self.banner[1]:
            self.banner = None
            self.dirty = True
        show = (s.enabled or self.banner is not None) and self._game_in_front()
        if show != self.visible:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE if show else SW_HIDE)
            self.visible = show
            self.dirty = True
        if show and self.dirty:
            self.dirty = False
            self._draw()

    # --- drawing -------------------------------------------------------------------------------------------------

    def render(self) -> gdiplus.Canvas:
        """The overlay drawn on a transparent canvas (also used by tests and the settings preview)."""
        with gdiplus.LOCK:
            return self._render()

    def _render(self) -> gdiplus.Canvas:
        s = self.settings
        size = max(10, s.font_size)
        font = load_font(size)
        small = load_font(max(10, int(size * 0.7)))
        pad, line_gap = 14, int(size * 0.35)
        width = max(240, s.width)
        banner = self.banner
        banner_lines = self._wrap([Message(banner[0], 0.0)], font, width - 2 * pad - 12) if banner else []
        messages = self.messages if s.enabled else []
        lines = self._wrap(messages, font, width - 2 * pad)
        line_height = size + line_gap
        banner_height = len(banner_lines) * line_height + (line_gap + 12 if lines else 6) if banner_lines else 0
        height = (self.HEADER + pad // 2 + banner_height + max(0, len(lines)) * line_height
                  + (pad if lines else 8 if banner_lines else 4))
        draw = gdiplus.Canvas(width, height)
        r, g, b = (int(s.background.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=10, fill=(r, g, b, s.background_alpha))
        gold = COLORS["gold"]
        draw.text((pad, 7), "Archipelago", small, (*gold, s.text_alpha))
        self._gear(draw, width - self.GEAR - 6, 2, self.GEAR, (*COLORS["dim"], s.text_alpha))
        y = self.HEADER + pad // 2
        if banner_lines:  # a gold-edged box, never faded
            box = (pad - 6, y - 4, width - pad + 6, y + len(banner_lines) * line_height + 4)
            draw.rounded_rectangle(box, radius=7, fill=(*gold, int(s.text_alpha * 0.16)),
                                   outline=(*gold, int(s.text_alpha * 0.8)), width=2)
            for line, _born in banner_lines:
                x = pad + 4
                for chunk, key in line:
                    draw.text((x + 1, y + 1), chunk, font, (0, 0, 0, int(s.text_alpha * 0.6)))
                    draw.text((x, y), chunk, font, (*COLORS.get(key, COLORS["text"]), s.text_alpha))
                    x += draw.textlength(chunk, font)
                y += line_height
            y += line_gap + 12
        now = time.monotonic()
        for line, born in lines:
            fade = 1.0
            if s.seconds > 0:
                age = now - born
                fade = max(0.0, min(1.0, (s.seconds + 1.5 - age) / 1.5))
            x = pad
            for chunk, key in line:
                alpha = int(s.text_alpha * fade)
                draw.text((x + 1, y + 1), chunk, font, (0, 0, 0, int(alpha * 0.6)))  # shadow
                draw.text((x, y), chunk, font, (*COLORS.get(key, COLORS["text"]), alpha))
                x += draw.textlength(chunk, font)
            y += line_height
        return draw

    @staticmethod
    def _gear(draw: gdiplus.Canvas, x: int, y: int, size: int, color) -> None:
        import math
        cx, cy, outer, inner = x + size / 2, y + size / 2, size * 0.42, size * 0.28
        points = []
        for i in range(16):
            angle = i * math.pi / 8
            radius = outer if i % 2 == 0 else inner
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        draw.polygon(points, color)
        draw.ellipse((cx - inner * 0.55, cy - inner * 0.55, cx + inner * 0.55, cy + inner * 0.55), (0, 0, 0, 0),
                     replace=True)

    @staticmethod
    def _wrap(messages: list[Message], font, width: int) -> list[tuple[list[tuple[str, str]], float]]:
        """Messages broken into lines of (text, colour) chunks that fit `width`."""
        out = []
        for message in messages:
            line: list[tuple[str, str]] = []
            used = 0.0
            for text, key in message.parts:
                for token in re.findall(r"\s*\S+|\s+$", text):  # words with the spaces before them
                    w = text_width(token, font)
                    if line and used + w > width:
                        out.append((line, message.born))
                        line, used = [], 0.0
                        token = token.lstrip()
                        w = text_width(token, font)
                    if line and line[-1][1] == key:
                        line[-1] = (line[-1][0] + token, key)
                    else:
                        line.append((token, key))
                    used += w
            if line:
                out.append((line, message.born))
        return out

    def _draw(self) -> None:
        canvas = self.render()
        width, height = canvas.size
        data = canvas.bgra(premultiplied=True)  # top-down rows (negative height below)
        canvas.close()
        header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        screen = user32.GetDC(None)
        memory = gdi32.CreateCompatibleDC(screen)
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(memory, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        ctypes.memmove(bits, data, len(data))
        old = gdi32.SelectObject(memory, bitmap)
        rect = wt.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        position, size, source = wt.POINT(rect.left, rect.top), wt.SIZE(width, height), wt.POINT(0, 0)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(position), ctypes.byref(size), memory,
                                   ctypes.byref(source), 0, ctypes.byref(blend), ULW_ALPHA)
        gdi32.SelectObject(memory, old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(None, screen)
        self.size = (width, height)
