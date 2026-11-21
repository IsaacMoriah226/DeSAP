"""Readers for the FromSoftware formats in the remake's cp11demonssouls\\dvdroot (little-endian, as Bluepoint
ships them): BND3 archives, PARAM tables (fields from Paramdex's DES definitions) and FMG text.

Layouts follow SoulsFormatsNEXT (BND3.cs, PARAM.cs, FMG.cs); only what the remake's files use is handled.
"""

from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from . import local

PARAMDEX_DES = local.path("paramdex") / "DES"  # (desap/local.py)


# --- BND3 -------------------------------------------------------------------------------------------------

@dataclass
class BinderFile:
    id: int
    name: str
    data: bytes

    @property
    def stem(self) -> str:
        return self.name.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]


def read_bnd3(data: bytes) -> list[BinderFile]:
    if data[:4] != b"BND3":
        raise ValueError(f"not a BND3 archive: {data[:12]!r}")
    fmt = data[0x0C]
    if data[0x0D] != 0:
        raise ValueError("big-endian BND3 (a PS3 file?)")
    if fmt != 0x74:
        raise ValueError(f"unhandled BND3 format {fmt:#x}")
    count = struct.unpack_from("<i", data, 0x10)[0]
    files = []
    for i in range(count):
        # format 0x74: flags, size, offset, id, name offset, uncompressed size
        _flags, size, offset, file_id, name_at, _usize = struct.unpack_from("<IiIiii", data, 0x20 + i * 24)
        name = data[name_at:data.index(b"\0", name_at)].decode("cp932")
        files.append(BinderFile(file_id, name, data[offset:offset + size]))
    return files


def read_bnd3_file(path: Path) -> dict[str, BinderFile]:
    return {f.stem: f for f in read_bnd3(path.read_bytes())}


# --- PARAMDEF (from Paramdex XML) ------------------------------------------------------------------------

_SCALAR = {"s8": "b", "u8": "B", "s16": "h", "u16": "H", "s32": "i", "u32": "I", "f32": "f"}


@dataclass
class Field:
    name: str
    type: str
    offset: int  # bytes
    bit: int = -1  # bitfield: first bit within the storage unit at offset
    bits: int = 0
    count: int = 1  # arrays (dummy8 Pad[2], fixstr)


@dataclass
class ParamDef:
    param_type: str
    fields: list[Field]
    size: int


def load_paramdef(name: str) -> ParamDef:
    root = ET.parse(PARAMDEX_DES / "Defs" / f"{name}.xml").getroot()
    param_type = root.findtext("ParamType")
    fields: list[Field] = []
    offset = 0
    bit_unit = None  # (type, offset, bits used)
    for node in root.iter("Field"):
        definition = node.get("Def")
        kind, rest = definition.split(" ", 1)
        rest = rest.split("=")[0].strip()  # default values ("s32 x = 0")
        count = 1
        bits = 0
        if ":" in rest:
            rest, bits_text = rest.split(":")
            rest, bits = rest.strip(), int(bits_text)
        if "[" in rest:
            rest, count_text = rest.split("[")
            count = int(count_text.rstrip("]"))
        size = 1 if kind in ("dummy8", "fixstr") else struct.calcsize(_SCALAR[kind])
        if bits:
            if bit_unit and bit_unit[0] == kind and bit_unit[2] + bits <= size * 8:
                fields.append(Field(rest, kind, bit_unit[1], bit_unit[2], bits))
                bit_unit = (kind, bit_unit[1], bit_unit[2] + bits)
                continue
            fields.append(Field(rest, kind, offset, 0, bits))
            bit_unit = (kind, offset, bits)
            offset += size
            continue
        bit_unit = None
        fields.append(Field(rest, kind, offset, count=count))
        offset += size * count
    return ParamDef(param_type, fields, offset)


# --- PARAM -----------------------------------------------------------------------------------------------

@dataclass
class Row:
    id: int
    name: str
    values: dict[str, object] = field(default_factory=dict)
    data_offset: int = 0

    def __getitem__(self, key: str):
        return self.values[key]


@dataclass
class Param:
    param_type: str
    row_size: int
    rows: list[Row]

    def by_id(self) -> dict[int, Row]:
        return {row.id: row for row in self.rows}


def _row_name(data: bytes, at: int) -> str:
    if at <= 0 or at >= len(data):
        return ""
    end = data.find(b"\0", at)
    return data[at:end].decode("cp932", "replace")


def read_param(data: bytes, paramdef: ParamDef | None = None, extended: bool = False) -> Param:
    """`extended`: the remake made some rows longer than the PS3 paramdef (EquipParamGoods 64 -> 72 bytes,
    EquipParamProtector 144 -> 256); read the paramdef's fields from the start of each row and ignore the rest."""
    if data[0x2C] != 0:
        raise ValueError("big-endian PARAM")
    flags = data[0x2D]
    if flags & 0x84:  # LongDataOffset / OffsetParamType: not in the remake's files so far
        raise ValueError(f"unhandled PARAM format flags {flags:#x}")
    row_count = struct.unpack_from("<H", data, 0x0A)[0]
    param_type = data[0x0C:0x2C].split(b"\0")[0].decode("ascii")
    rows = []
    for i in range(row_count):
        row_id, data_at, name_at = struct.unpack_from("<iII", data, 0x30 + i * 12)
        # The remake's name offsets point 4 bytes before the text (the names are Bluepoint's English ones).
        rows.append(Row(row_id, _row_name(data, name_at + 4 if name_at else 0), data_offset=data_at))
    row_size = rows[1].data_offset - rows[0].data_offset if len(rows) > 1 else 0
    if paramdef is not None:
        if paramdef.size != row_size and not (extended and paramdef.size < row_size):
            raise ValueError(f"{param_type}: paramdef size {paramdef.size} != row size {row_size}")
        for row in rows:
            row.values = _unpack(paramdef, data, row.data_offset)
    return Param(param_type, row_size, rows)


def _unpack(paramdef: ParamDef, data: bytes, base: int) -> dict[str, object]:
    out: dict[str, object] = {}
    for f in paramdef.fields:
        if f.type == "dummy8":
            continue
        if f.type == "fixstr":
            out[f.name] = data[base + f.offset:base + f.offset + f.count].split(b"\0")[0].decode("cp932", "replace")
            continue
        value = struct.unpack_from("<" + _SCALAR[f.type], data, base + f.offset)[0]
        if f.bits:
            value = (value >> f.bit) & ((1 << f.bits) - 1)
        out[f.name] = value
    return out


# --- FMG -------------------------------------------------------------------------------------------------

def read_fmg(data: bytes) -> dict[int, str]:
    """The remake's FMG (not the PS3 layout): a 0x20-byte header of int32s (1, file size, unicode, group count,
    string count, 0, string offsets offset, 0), groups of (offset index, first id, last id), int32 string offsets."""
    one, file_size, unicode, group_count, string_count, _zero, offsets_at = struct.unpack_from("<7i", data, 0)
    if one != 1 or file_size != len(data):
        raise ValueError(f"unexpected FMG header {data[:32].hex(' ')}")
    strings_start = offsets_at + string_count * 4  # an empty entry points into the header (offset 4)
    out: dict[int, str] = {}
    for g in range(group_count):
        index, first, last = struct.unpack_from("<iii", data, 0x20 + g * 12)
        for j in range(last - first + 1):
            string_at = struct.unpack_from("<i", data, offsets_at + (index + j) * 4)[0]
            if string_at < strings_start:
                continue
            if unicode:
                end = string_at
                while data[end:end + 2] != b"\0\0":
                    end += 2
                out[first + j] = data[string_at:end].decode("utf-16-le")
            else:
                out[first + j] = data[string_at:data.index(b"\0", string_at)].decode("cp932", "replace")
    return out
