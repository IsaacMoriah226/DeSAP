"""Just enough GDI+ (gdiplus.dll, part of every Windows) to draw the overlay: anti-aliased shapes and text in a
font loaded from memory, into a 32-bit bitmap read back as BGRA bytes (premultiplied for layered windows, straight
for Kivy). Archipelago's frozen build leaves out Pillow, so the overlay cannot use it.

GDI+ objects are not safe to use from two threads at once: every drawing goes through LOCK.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading

_gdip = ctypes.WinDLL("gdiplus")
LOCK = threading.RLock()

PIXEL_ARGB, PIXEL_PARGB = 0x26200A, 0xE200B
UNIT_PIXEL, UNIT_WORLD = 2, 0
SMOOTHING_ANTIALIAS, TEXT_ANTIALIAS_GRIDFIT, PIXEL_OFFSET_HALF = 4, 3, 4
COMPOSITE_OVER, COMPOSITE_COPY = 0, 1
FORMAT_MEASURE_TRAILING_SPACES, FORMAT_NO_WRAP = 0x800, 0x1000
LOCK_READ = 1

Color = tuple  # (r, g, b) or (r, g, b, a)


class _StartupInput(ctypes.Structure):
    _fields_ = [("GdiplusVersion", ctypes.c_uint32), ("DebugEventCallback", ctypes.c_void_p),
                ("SuppressBackgroundThread", wt.BOOL), ("SuppressExternalCodecs", wt.BOOL)]


class _RectF(ctypes.Structure):
    _fields_ = [("X", ctypes.c_float), ("Y", ctypes.c_float), ("Width", ctypes.c_float), ("Height", ctypes.c_float)]


class _Rect(ctypes.Structure):
    _fields_ = [("X", ctypes.c_int), ("Y", ctypes.c_int), ("Width", ctypes.c_int), ("Height", ctypes.c_int)]


class _PointF(ctypes.Structure):
    _fields_ = [("X", ctypes.c_float), ("Y", ctypes.c_float)]


class _BitmapData(ctypes.Structure):
    _fields_ = [("Width", ctypes.c_uint), ("Height", ctypes.c_uint), ("Stride", ctypes.c_int),
                ("PixelFormat", ctypes.c_int), ("Scan0", ctypes.c_void_p), ("Reserved", ctypes.c_size_t)]


_token = ctypes.c_size_t(0)
_handle = ctypes.c_void_p


def _check(status: int, what: str) -> None:
    if status != 0:
        raise OSError(f"GDI+ {what} failed (status {status})")


def _startup() -> None:
    if not _token.value:
        _check(_gdip.GdiplusStartup(ctypes.byref(_token), ctypes.byref(_StartupInput(1, None, False, False)), None),
               "startup")


def _argb(color: Color) -> int:
    r, g, b = color[:3]
    a = color[3] if len(color) > 3 else 255
    return (int(a) & 255) << 24 | (int(r) & 255) << 16 | (int(g) & 255) << 8 | (int(b) & 255)


class FontFile:
    """A font file's first family, loaded from bytes (kept alive as long as this object)."""

    def __init__(self, data: bytes):
        with LOCK:
            _startup()
            self._data = ctypes.create_string_buffer(data, len(data))
            self._collection = _handle()
            _check(_gdip.GdipNewPrivateFontCollection(ctypes.byref(self._collection)), "font collection")
            _check(_gdip.GdipPrivateAddMemoryFont(self._collection, self._data, len(data)), "add font")
            families = (_handle * 4)()
            found = ctypes.c_int()
            _check(_gdip.GdipGetFontCollectionFamilyList(self._collection, 4, families, ctypes.byref(found)),
                   "font families")
            if found.value < 1:
                raise OSError("GDI+: no font family in the file")
            self.family = _handle(families[0])
        self._sizes: dict[float, Font] = {}

    def size(self, pixels: float) -> "Font":
        pixels = float(pixels)
        if pixels not in self._sizes:
            self._sizes[pixels] = Font(self.family, pixels)
        return self._sizes[pixels]


class Font:
    def __init__(self, family, pixels: float):
        with LOCK:
            _startup()
            self.handle = _handle()
            _check(_gdip.GdipCreateFont(family, ctypes.c_float(pixels), 0, UNIT_PIXEL, ctypes.byref(self.handle)),
                   "font")
        self.pixels = pixels

    @staticmethod
    def system(name: str, pixels: float) -> "Font":
        with LOCK:
            _startup()
            family = _handle()
            _check(_gdip.GdipCreateFontFamilyFromName(ctypes.c_wchar_p(name), None, ctypes.byref(family)),
                   f"font family {name}")
            return Font(family, pixels)


_format = None


def _string_format():
    global _format
    if _format is None:
        typographic, clone = _handle(), _handle()
        _check(_gdip.GdipStringFormatGetGenericTypographic(ctypes.byref(typographic)), "string format")
        _check(_gdip.GdipCloneStringFormat(typographic, ctypes.byref(clone)), "string format")
        _check(_gdip.GdipSetStringFormatFlags(clone, FORMAT_MEASURE_TRAILING_SPACES | FORMAT_NO_WRAP), "format flags")
        _format = clone
    return _format


class Canvas:
    """A transparent width x height drawing surface."""

    def __init__(self, width: int, height: int):
        self.width, self.height = max(1, int(width)), max(1, int(height))
        with LOCK:
            _startup()
            self.bitmap, self.graphics = _handle(), _handle()
            _check(_gdip.GdipCreateBitmapFromScan0(self.width, self.height, 0, PIXEL_PARGB, None,
                                                   ctypes.byref(self.bitmap)), "bitmap")
            _check(_gdip.GdipGetImageGraphicsContext(self.bitmap, ctypes.byref(self.graphics)), "graphics")
            _gdip.GdipSetSmoothingMode(self.graphics, SMOOTHING_ANTIALIAS)
            _gdip.GdipSetTextRenderingHint(self.graphics, TEXT_ANTIALIAS_GRIDFIT)
            _gdip.GdipSetPixelOffsetMode(self.graphics, PIXEL_OFFSET_HALF)

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height

    def close(self) -> None:
        with LOCK:
            if self.graphics:
                _gdip.GdipDeleteGraphics(self.graphics)
                self.graphics = _handle()
            if self.bitmap:
                _gdip.GdipDisposeImage(self.bitmap)
                self.bitmap = _handle()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # --- shapes ------------------------------------------------------------------------------------------------

    def _brush(self, color: Color):
        brush = _handle()
        _check(_gdip.GdipCreateSolidFill(ctypes.c_uint32(_argb(color)), ctypes.byref(brush)), "brush")
        return brush

    def rounded_rectangle(self, box, radius: float, fill: Color | None = None, outline: Color | None = None,
                          width: float = 1.0) -> None:
        x0, y0, x1, y1 = (float(v) for v in box)
        d = min(2 * radius, x1 - x0, y1 - y0)
        f = ctypes.c_float
        with LOCK:
            path = _handle()
            _check(_gdip.GdipCreatePath(0, ctypes.byref(path)), "path")
            try:
                _gdip.GdipAddPathArc(path, f(x0), f(y0), f(d), f(d), f(180), f(90))
                _gdip.GdipAddPathArc(path, f(x1 - d), f(y0), f(d), f(d), f(270), f(90))
                _gdip.GdipAddPathArc(path, f(x1 - d), f(y1 - d), f(d), f(d), f(0), f(90))
                _gdip.GdipAddPathArc(path, f(x0), f(y1 - d), f(d), f(d), f(90), f(90))
                _gdip.GdipClosePathFigure(path)
                if fill is not None:
                    brush = self._brush(fill)
                    _gdip.GdipFillPath(self.graphics, brush, path)
                    _gdip.GdipDeleteBrush(brush)
                if outline is not None:
                    pen = _handle()
                    _check(_gdip.GdipCreatePen1(ctypes.c_uint32(_argb(outline)), f(width), UNIT_WORLD,
                                                ctypes.byref(pen)), "pen")
                    _gdip.GdipDrawPath(self.graphics, pen, path)
                    _gdip.GdipDeletePen(pen)
            finally:
                _gdip.GdipDeletePath(path)

    def polygon(self, points, fill: Color) -> None:
        array = (_PointF * len(points))(*[_PointF(float(x), float(y)) for x, y in points])
        with LOCK:
            brush = self._brush(fill)
            _gdip.GdipFillPolygon(self.graphics, brush, array, len(points), 0)
            _gdip.GdipDeleteBrush(brush)

    def ellipse(self, box, fill: Color, replace: bool = False) -> None:
        """`replace`: write the colour as it is (a transparent fill cuts a hole) instead of blending it."""
        x0, y0, x1, y1 = (float(v) for v in box)
        f = ctypes.c_float
        with LOCK:
            brush = self._brush(fill)
            if replace:
                _gdip.GdipSetCompositingMode(self.graphics, COMPOSITE_COPY)
            _gdip.GdipFillEllipse(self.graphics, brush, f(x0), f(y0), f(x1 - x0), f(y1 - y0))
            if replace:
                _gdip.GdipSetCompositingMode(self.graphics, COMPOSITE_OVER)
            _gdip.GdipDeleteBrush(brush)

    def fill(self, color: Color) -> None:
        with LOCK:
            _gdip.GdipGraphicsClear(self.graphics, ctypes.c_uint32(_argb(color)))

    def paste(self, other: "Canvas", x: int, y: int) -> None:
        with LOCK:
            _gdip.GdipDrawImageI(self.graphics, other.bitmap, int(x), int(y))

    # --- text --------------------------------------------------------------------------------------------------

    def text(self, xy, text: str, font: Font, fill: Color) -> None:
        if not text:
            return
        layout = _RectF(float(xy[0]), float(xy[1]), 0.0, 0.0)
        with LOCK:
            brush = self._brush(fill)
            _gdip.GdipDrawString(self.graphics, ctypes.c_wchar_p(text), len(text), font.handle, ctypes.byref(layout),
                                 _string_format(), brush)
            _gdip.GdipDeleteBrush(brush)

    def textlength(self, text: str, font: Font) -> float:
        if not text:
            return 0.0
        layout, bounds = _RectF(0, 0, 0, 0), _RectF()
        with LOCK:
            _check(_gdip.GdipMeasureString(self.graphics, ctypes.c_wchar_p(text), len(text), font.handle,
                                           ctypes.byref(layout), _string_format(), ctypes.byref(bounds), None, None),
                   "measure")
        return bounds.Width

    # --- reading back ------------------------------------------------------------------------------------------

    def bgra(self, premultiplied: bool = True) -> bytes:
        """The pixels, top row first, 4 bytes each (blue, green, red, alpha)."""
        rect = _Rect(0, 0, self.width, self.height)
        data = _BitmapData()
        with LOCK:
            _check(_gdip.GdipBitmapLockBits(self.bitmap, ctypes.byref(rect), LOCK_READ,
                                            PIXEL_PARGB if premultiplied else PIXEL_ARGB, ctypes.byref(data)), "lock")
            try:
                row = self.width * 4
                if data.Stride == row:
                    return ctypes.string_at(data.Scan0, row * self.height)
                return b"".join(ctypes.string_at(data.Scan0 + y * data.Stride, row) for y in range(self.height))
            finally:
                _gdip.GdipBitmapUnlockBits(self.bitmap, ctypes.byref(data))

    def pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        """(r, g, b, a) straight alpha (for tests)."""
        b, g, r, a = self.bgra(premultiplied=False)[(y * self.width + x) * 4:(y * self.width + x) * 4 + 4]
        return r, g, b, a


# argument types (64-bit pointers must not be truncated to int)
_P = ctypes.c_void_p
for _name, _args in {
    "GdiplusStartup": [ctypes.POINTER(ctypes.c_size_t), _P, _P],
    "GdipNewPrivateFontCollection": [_P], "GdipPrivateAddMemoryFont": [_P, _P, ctypes.c_int],
    "GdipGetFontCollectionFamilyList": [_P, ctypes.c_int, _P, _P],
    "GdipCreateFont": [_P, ctypes.c_float, ctypes.c_int, ctypes.c_int, _P],
    "GdipCreateFontFamilyFromName": [ctypes.c_wchar_p, _P, _P],
    "GdipStringFormatGetGenericTypographic": [_P], "GdipCloneStringFormat": [_P, _P],
    "GdipSetStringFormatFlags": [_P, ctypes.c_int],
    "GdipCreateBitmapFromScan0": [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, _P, _P],
    "GdipGetImageGraphicsContext": [_P, _P], "GdipSetSmoothingMode": [_P, ctypes.c_int],
    "GdipSetTextRenderingHint": [_P, ctypes.c_int], "GdipSetPixelOffsetMode": [_P, ctypes.c_int],
    "GdipSetCompositingMode": [_P, ctypes.c_int], "GdipDeleteGraphics": [_P], "GdipDisposeImage": [_P],
    "GdipCreateSolidFill": [ctypes.c_uint32, _P], "GdipDeleteBrush": [_P],
    "GdipCreatePath": [ctypes.c_int, _P], "GdipDeletePath": [_P], "GdipClosePathFigure": [_P],
    "GdipAddPathArc": [_P] + [ctypes.c_float] * 6, "GdipFillPath": [_P, _P, _P], "GdipDrawPath": [_P, _P, _P],
    "GdipCreatePen1": [ctypes.c_uint32, ctypes.c_float, ctypes.c_int, _P], "GdipDeletePen": [_P],
    "GdipFillPolygon": [_P, _P, _P, ctypes.c_int, ctypes.c_int],
    "GdipFillEllipse": [_P, _P] + [ctypes.c_float] * 4, "GdipGraphicsClear": [_P, ctypes.c_uint32],
    "GdipDrawImageI": [_P, _P, ctypes.c_int, ctypes.c_int],
    "GdipDrawString": [_P, ctypes.c_wchar_p, ctypes.c_int, _P, _P, _P, _P],
    "GdipMeasureString": [_P, ctypes.c_wchar_p, ctypes.c_int, _P, _P, _P, _P, _P, _P],
    "GdipBitmapLockBits": [_P, _P, ctypes.c_uint, ctypes.c_int, _P], "GdipBitmapUnlockBits": [_P, _P],
}.items():
    _function = getattr(_gdip, _name)
    _function.argtypes = _args
    _function.restype = ctypes.c_int
