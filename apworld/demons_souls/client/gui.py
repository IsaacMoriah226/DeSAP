"""The Demon's Souls Archipelago launcher window (Kivy), styled after KytyLauncher: a sidebar of pages, cards, the
gold serif headings and the red PLAY button. Archipelago's own client view (log, hints, command line) is the
"Archipelago" page. Imported only when the GUI starts (Kivy is set up by then)."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
from pathlib import Path

from kvui import GameManager  # (first: kvui sets Kivy up)

from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout

import Utils


def _rgba(hex_color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, alpha


# KytyLauncher's Theme.xaml
WINDOW, SIDEBAR, BAR, CARD = _rgba("#101012"), _rgba("#16161A"), _rgba("#141417"), _rgba("#18181C")
INPUT, INPUT_HOVER, BORDER = _rgba("#222228"), _rgba("#2A2A31"), _rgba("#2E2E35")
TEXT, TEXT_DIM, TEXT_FAINT = _rgba("#E8E5DF"), _rgba("#9A968F"), _rgba("#6B6863")
GOLD, GOOD, WARN, BAD = _rgba("#C9A45C"), _rgba("#86B36F"), _rgba("#D9A441"), _rgba("#D2604F")
PLAY, PLAY_HOVER = _rgba("#8E1B1B"), _rgba("#AD2626")

FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
SERIF, UI, UI_BOLD, SYMBOLS = "Roboto", "Roboto", "Roboto", "Roboto"


def _register_fonts() -> None:
    global SERIF, UI, UI_BOLD, SYMBOLS
    found = {}
    for name, file in (("DesSerif", "georgia.ttf"), ("DesUi", "segoeui.ttf"), ("DesUiBold", "segoeuib.ttf"),
                       ("DesSymbols", "seguisym.ttf")):
        if (FONTS / file).exists():
            LabelBase.register(name, str(FONTS / file))
            found[name] = True
    SERIF = "DesSerif" if "DesSerif" in found else "Roboto"
    UI = "DesUi" if "DesUi" in found else "Roboto"
    UI_BOLD = "DesUiBold" if "DesUiBold" in found else "Roboto"
    SYMBOLS = "DesSymbols" if "DesSymbols" in found else UI


# --- small widgets ---------------------------------------------------------------------------------------------


def paint(widget: Widget, color, radius: float = 0, border=None) -> Widget:
    with widget.canvas.before:
        Color(*color)
        shape = RoundedRectangle(radius=[radius]) if radius else Rectangle()
        if border:
            Color(*border)
            line = Line(width=1)
    def update(*_):
        shape.pos, shape.size = widget.pos, widget.size
        if border:
            line.rounded_rectangle = (widget.x, widget.y, widget.width, widget.height, radius or 1)
    widget.bind(pos=update, size=update)
    return widget


def text(value: str = "", size: float = 13.5, color=TEXT, font: str | None = None, halign: str = "left",
         height: float | None = None, markup: bool = False) -> Label:
    label = Label(text=value, font_size=dp(size), color=color, font_name=font or UI, halign=halign,
                  valign="middle", size_hint_y=None, markup=markup)
    label.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    if height is None:
        label.bind(texture_size=lambda w, v: setattr(w, "height", v[1]))
    else:
        label.height = dp(height)
    return label


class FlatButton(Button):
    def __init__(self, label: str, color=INPUT, hover=INPUT_HOVER, text_color=TEXT, font=None, points=13.5, **kw):
        super().__init__(text=label, background_normal="", background_down="", background_color=(0, 0, 0, 0),
                         color=text_color, font_name=font or UI, font_size=dp(points), **kw)
        self.base, self.hover = color, hover
        with self.canvas.before:
            self._color = Color(*color)
            self._rect = RoundedRectangle(radius=[dp(3)])
        self.bind(pos=self._update, size=self._update, state=self._pressed)

    def _update(self, *_):
        self._rect.pos, self._rect.size = self.pos, self.size

    def _pressed(self, *_):
        self._color.rgba = self.hover if self.state == "down" else self.base


class Field(TextInput):
    def __init__(self, value: str = "", password: bool = False, hint: str = "", **kw):
        super().__init__(text=value, password=password, hint_text=hint, multiline=False, write_tab=False,
                         background_normal="", background_active="", background_color=INPUT,
                         foreground_color=TEXT, cursor_color=GOLD, hint_text_color=TEXT_FAINT, font_name=UI,
                         font_size=dp(13.5), padding=[dp(10), dp(9)], size_hint_y=None, height=dp(38), **kw)


class Card(BoxLayout):
    def __init__(self, title: str, **kw):
        super().__init__(orientation="vertical", padding=[dp(20), dp(16)], spacing=dp(10), size_hint_y=None, **kw)
        paint(self, CARD, radius=dp(4), border=BORDER)
        self.add_widget(text(title, 16, GOLD, SERIF))
        self.bind(minimum_height=self.setter("height"))


class CheckRow(BoxLayout):
    MARKS = {"ok": ("✓", GOOD), "wait": ("…", TEXT_DIM), "bad": ("✗", BAD), "warn": ("!", WARN)}

    def __init__(self):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(24), spacing=dp(8))
        self.mark = text("", 14, GOOD, SYMBOLS, height=24)
        self.mark.size_hint_x = None
        self.mark.width = dp(18)
        self.label = text("", 13.5, TEXT, height=24)
        self.add_widget(self.mark)
        self.add_widget(self.label)

    def set(self, kind: str, value: str) -> None:
        mark, color = self.MARKS[kind]
        self.mark.text, self.mark.color = mark, color
        self.label.text = value


def choose_file(title: str, pattern: str) -> str:
    """The Windows open-file dialog (comdlg32); "" when cancelled."""
    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [("lStructSize", wt.DWORD), ("hwndOwner", wt.HWND), ("hInstance", wt.HINSTANCE),
                    ("lpstrFilter", wt.LPCWSTR), ("lpstrCustomFilter", wt.LPWSTR), ("nMaxCustFilter", wt.DWORD),
                    ("nFilterIndex", wt.DWORD), ("lpstrFile", wt.LPWSTR), ("nMaxFile", wt.DWORD),
                    ("lpstrFileTitle", wt.LPWSTR), ("nMaxFileTitle", wt.DWORD), ("lpstrInitialDir", wt.LPCWSTR),
                    ("lpstrTitle", wt.LPCWSTR), ("Flags", wt.DWORD), ("nFileOffset", wt.WORD),
                    ("nFileExtension", wt.WORD), ("lpstrDefExt", wt.LPCWSTR), ("lCustData", wt.LPARAM),
                    ("lpfnHook", ctypes.c_void_p), ("lpTemplateName", wt.LPCWSTR), ("pvReserved", ctypes.c_void_p),
                    ("dwReserved", wt.DWORD), ("FlagsEx", wt.DWORD)]
    buffer = ctypes.create_unicode_buffer(1024)
    dialog = OPENFILENAMEW()
    dialog.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    dialog.lpstrFilter = f"{pattern}\0{pattern}\0\0"
    dialog.lpstrFile = ctypes.cast(buffer, wt.LPWSTR)
    dialog.nMaxFile = 1024
    dialog.lpstrTitle = title
    dialog.Flags = 0x00001000 | 0x00000800 | 0x00000008  # FILEMUSTEXIST | PATHMUSTEXIST | NOCHANGEDIR
    if ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(dialog)):
        return buffer.value
    return ""


# --- pages -----------------------------------------------------------------------------------------------------


def page(*children, padding=None) -> ScrollView:
    column = BoxLayout(orientation="vertical", padding=padding or [dp(46), dp(36), dp(46), dp(24)], spacing=dp(18),
                       size_hint_y=None)
    column.bind(minimum_height=column.setter("height"))
    for child in children:
        column.add_widget(child)
    view = ScrollView(do_scroll_x=False, bar_width=dp(6))
    view.add_widget(column)
    return view


class PlayPage(BoxLayout):
    def __init__(self, ctx):
        super().__init__(orientation="vertical")
        self.ctx = ctx
        s = ctx.settings
        banner = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(130), padding=[dp(46), dp(36), dp(46), 0],
                           spacing=dp(4))
        banner.add_widget(text("Demon's Souls", 32, TEXT, SERIF, height=46))
        self.subtitle = text("Archipelago  ·  PPSA01341  ·  01.007.000", 12.5, TEXT_DIM, height=20)
        banner.add_widget(self.subtitle)
        self.add_widget(banner)

        columns = BoxLayout(orientation="horizontal", spacing=dp(18), size_hint_y=None,
                            padding=[dp(46), dp(18), dp(46), dp(18)])
        left = BoxLayout(orientation="vertical", spacing=dp(18), size_hint_y=None)
        left.bind(minimum_height=left.setter("height"))
        right = BoxLayout(orientation="vertical", spacing=dp(18), size_hint_y=None)
        right.bind(minimum_height=right.setter("height"))

        checks = Card("Checks")
        self.rows = {}
        for key in ("emulator", "server", "game", "items", "save", "progress"):
            self.rows[key] = CheckRow()
            checks.add_widget(self.rows[key])
        left.add_widget(checks)

        connection = Card("Archipelago")
        connection.add_widget(text("Server (address:port)", 12, TEXT_DIM, height=18))
        self.server = Field(s.server, hint="archipelago.gg:38281")
        connection.add_widget(self.server)
        connection.add_widget(text("Slot name", 12, TEXT_DIM, height=18))
        self.slot = Field(s.slot, hint="your slot name")
        connection.add_widget(self.slot)
        connection.add_widget(text("Password (if the room has one)", 12, TEXT_DIM, height=18))
        self.password = Field(s.password, password=True)
        connection.add_widget(self.password)
        right.add_widget(connection)

        game = Card("Emulator")
        game.add_widget(text("KytyLauncher.exe (its settings are used as they are)", 12, TEXT_DIM, height=18))
        self.launcher = Field(s.kyty_launcher, hint=r"...\KytyPS5\KytyLauncher.exe")
        game.add_widget(self.launcher)
        browse = FlatButton("Browse...", size_hint=(None, None), size=(dp(110), dp(34)))
        browse.bind(on_release=self.browse)
        game.add_widget(browse)
        self.settings_text = text("", 12.5, TEXT_DIM)
        game.add_widget(self.settings_text)
        right.add_widget(game)

        for column in (left, right):
            holder = AnchorLayout(anchor_y="top")
            holder.add_widget(column)
            columns.add_widget(holder)
        def fit(*_):
            columns.height = max(left.height, right.height) + dp(36)
        left.bind(height=fit)
        right.bind(height=fit)
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(6))
        scroll.add_widget(columns)
        self.add_widget(scroll)

        bar = paint(BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(72),
                              padding=[dp(28), dp(14), dp(28), dp(14)], spacing=dp(14)), BAR)
        self.status = text("", 12.5, TEXT_DIM, height=40)
        bar.add_widget(self.status)
        self.play = FlatButton("PLAY", color=PLAY, hover=PLAY_HOVER, font=SERIF, points=19, size_hint=(None, 1),
                               width=dp(220))
        self.play.bind(on_release=self.on_play)
        bar.add_widget(self.play)
        self.add_widget(bar)
        Clock.schedule_interval(self.refresh, 0.5)
        self.refresh()

    def store(self) -> None:
        s = self.ctx.settings
        s.server, s.slot, s.password = self.server.text.strip(), self.slot.text.strip(), self.password.text
        s.kyty_launcher = self.launcher.text.strip().strip('"')
        s.save()

    def browse(self, *_):
        path = choose_file("KytyLauncher.exe", "KytyLauncher.exe")
        if path:
            self.launcher.text = path
            self.store()

    def on_play(self, *_):
        self.store()
        Utils.async_start(self.ctx.launch(), name="launch")

    def refresh(self, *_):
        st = self.ctx.status()
        rows = self.rows
        from .profile import Emulator
        emulator = Emulator(Path(self.launcher.text.strip().strip('"'))) if self.launcher.text.strip() else None
        problems = emulator.check() if emulator else ["choose KytyLauncher.exe"]
        rows["emulator"].set("ok" if not problems else "bad",
                             "KytyPS5 found" if not problems else problems[0])
        if st["connected"]:
            rows["server"].set("ok", f"Connected as {st['slot']}  ·  {st['scouted']} locations scouted")
        else:
            rows["server"].set("wait", "Not connected (PLAY connects)")
        if st["attached"]:
            rows["game"].set("ok" if st["launcher_mode"] else "warn",
                             "Demon's Souls 01.007.000 running" + ("" if st["launcher_mode"] else
                                                                  " outside the Archipelago profile"))
        else:
            rows["game"].set("wait", "Game not running")
        rows["items"].set("ok" if st["placed"] else "wait",
                          "Items placed" if st["placed"] else "Items are placed at the title screen")
        if st["save_ok"]:
            rows["save"].set("ok", "This slot's save is loaded")
        elif st["save_problem"]:
            rows["save"].set("bad", "Loaded save: " + st["save_problem"])
        else:
            rows["save"].set("wait", "Start a new character, or load this slot's save")
        rows["progress"].set("ok" if st["goal"] else "wait",
                             f"{st['checked']} / {st['locations']} locations checked  ·  {st['received']} items received"
                             + ("  ·  goal done" if st["goal"] else ""))
        if emulator and not problems:
            es = emulator.settings()
            parts = [es.get("resolution", ""), "fullscreen" if es.get("fullscreen") else "window"]
            if es.get("upscaler"):
                parts.append(str(es.get("upscaler")).upper())
            self.settings_text.text = "Uses your KytyLauncher settings: " + "  ·  ".join(p for p in parts if p)
        running = st["attached"]
        self.play.text = "RUNNING" if running else "PLAY"
        self.play.disabled = running
        self.status.text = st["launch"] or ("Archipelago saves are kept apart from your vanilla saves and backed up "
                                            "while you play.")


class SavesPage(BoxLayout):
    def __init__(self, ctx):
        super().__init__(orientation="vertical")
        self.ctx = ctx
        info = Card("Archipelago saves")
        info.add_widget(text("Separate from your vanilla saves: the Archipelago profile is a mirror of the emulator "
                             "folder with a save folder of its own. Saves are backed up at every PLAY and every few "
                             "minutes while the game runs.", 13, TEXT_DIM))
        self.path = text("", 12.5, TEXT_FAINT)
        info.add_widget(self.path)
        buttons = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(10))
        for label, action in (("Open saves folder", self.open_saves), ("Open backups", self.open_backups),
                              ("Back up now", self.backup_now)):
            button = FlatButton(label, size_hint_x=None, width=dp(160))
            button.bind(on_release=action)
            buttons.add_widget(button)
        buttons.add_widget(Widget())
        info.add_widget(buttons)
        self.backups = Card("Backups (newest first)")
        self.add_widget(page(info, self.backups))
        Clock.schedule_interval(self.refresh, 3)
        self.refresh()

    def open_saves(self, *_):
        self.ctx.profile.save_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(self.ctx.profile.save_dir)

    def open_backups(self, *_):
        self.ctx.profile.backup_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(self.ctx.profile.backup_dir)

    def backup_now(self, *_):
        made = self.ctx.profile.backup("manual")
        self.ctx.launch_status = f"Backed up to {made.name}." if made else "Nothing new to back up."
        self.refresh()

    def restore(self, backup: Path) -> None:
        if self.ctx.bridge.attached:
            self.ctx.launch_status = "Close the game before restoring a backup."
            return
        self.ctx.profile.restore(backup)
        self.ctx.launch_status = f"Restored {backup.name}."
        self.refresh()

    def refresh(self, *_):
        self.path.text = f"Profile: {self.ctx.profile.root}"
        backups = self.ctx.profile.backups()[:12]
        names = [b.name for b in backups]
        if getattr(self, "_shown", None) == names:
            return
        self._shown = names
        while len(self.backups.children) > 1:
            self.backups.remove_widget(self.backups.children[0])
        if not backups:
            self.backups.add_widget(text("No backups yet.", 13, TEXT_DIM))
        for backup in backups:
            row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(10))
            row.add_widget(text(backup.name, 13, TEXT, height=34))
            button = FlatButton("Restore", size_hint_x=None, width=dp(100))
            button.bind(on_release=lambda *_, b=backup: self.restore(b))
            row.add_widget(button)
            self.backups.add_widget(row)


class Sidebar(BoxLayout):
    def __init__(self, pages: list[str], select):
        super().__init__(orientation="vertical", size_hint_x=None, width=dp(230), padding=[0, dp(30), 0, dp(20)],
                         spacing=dp(2))
        paint(self, SIDEBAR)
        head = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(96), padding=[dp(25), 0], spacing=dp(2))
        head.add_widget(text("Demon's Souls", 21, GOLD, SERIF, height=30))
        head.add_widget(text("Archipelago", 13, TEXT, height=20))
        head.add_widget(text("KytyPS5  ·  randomizer", 11.5, TEXT_FAINT, height=18))
        self.add_widget(head)
        self.select = select
        self.buttons = {}
        for name in pages:
            button = Button(text=name, background_normal="", background_down="", background_color=(0, 0, 0, 0),
                            color=TEXT_DIM, font_name=UI, font_size=dp(14), halign="left", valign="middle",
                            size_hint_y=None, height=dp(42), padding=[dp(25), 0])
            button.bind(size=lambda w, v: setattr(w, "text_size", v))
            with button.canvas.before:
                button.bg = Color(0, 0, 0, 0)
                rect = Rectangle()
                button.accent = Color(0, 0, 0, 0)
                bar = Rectangle()
            def place(w, *_, rect=rect, bar=bar):
                rect.pos, rect.size = w.pos, w.size
                bar.pos, bar.size = w.pos, (dp(3), w.height)
            button.bind(pos=place, size=place)
            button.bind(on_release=lambda w, n=name: self.choose(n))
            self.buttons[name] = button
            self.add_widget(button)
        self.add_widget(Widget())
        self.footer = text("", 11, TEXT_FAINT, height=40)
        self.footer.padding = [dp(25), 0]
        self.add_widget(self.footer)

    def choose(self, name: str) -> None:
        for other, button in self.buttons.items():
            on = other == name
            button.color = TEXT if on else TEXT_DIM
            button.bg.rgba = _rgba("#1E1E23") if on else (0, 0, 0, 0)
            button.accent.rgba = GOLD if on else (0, 0, 0, 0)
        self.select(name)


def make_manager(ctx):
    _register_fonts()

    class DemonsSoulsManager(GameManager):
        logging_pairs = [("Client", "Archipelago")]
        base_title = "Demon's Souls - Archipelago"

        def set_colors(self):
            super().set_colors()
            self.theme_cls.theme_style = "Dark"
            self.theme_cls.primary_palette = "Darkgoldenrod"  # the Archipelago page in the launcher's tones
            self.theme_cls.dynamic_scheme_name = "MONOCHROME"

        def build(self):
            client_view = super().build()  # Archipelago's log, hints and command line
            root = MDBoxLayout(orientation="horizontal")
            self.pages = ScreenManager(transition=NoTransition())
            content = {
                "Play": PlayPage(ctx),
                "Archipelago": client_view,
                "Saves": SavesPage(ctx),
            }
            for name, widget in content.items():
                screen = Screen(name=name)
                screen.add_widget(paint(BoxLayout(), WINDOW) if name != "Archipelago" else Widget(size_hint=(0, 0)))
                screen.add_widget(widget)
                self.pages.add_widget(screen)
            self.sidebar = Sidebar(list(content), lambda name: setattr(self.pages, "current", name))
            root.add_widget(self.sidebar)
            root.add_widget(self.pages)
            self.sidebar.choose("Play")
            from .. import DemonsSoulsWorld
            self.sidebar.footer.text = f"World version {DemonsSoulsWorld.world_version.as_simple_string()}"
            return root

    return DemonsSoulsManager(ctx)
