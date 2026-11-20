"""Item rewards handed out by the Lua event scripts (boss souls, event items), with the event flag that marks
each one, and how to read any event flag from the flag manager.

Flag ids are one bit array (flag n = bit n % 8 of byte n // 8 from the manager, set/get by id at 0x9002a7400 /
0x9002a7550). Two ranges belong to the world being played and are swapped on world change:
  0-3199      live at +0x0,   saved per world at +0x8d0  + (w - 1) * 0x190
  8192-12287  live at +0x400, saved per world at +0x2b1c + (w - 1) * 0x200
Everything else (3200-8191, 12288-18047) is global. The world being played is the byte at +0x3cd3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .gamedata import AREAS, GameData, LotItem

WORLD_RANGES = (  # (first flag, last flag + 1, live offset, saved base, saved size per world)
    (0, 3200, 0x0, 0x8D0, 0x190),
    (8192, 12288, 0x400, 0x2B1C, 0x200),
)
CURRENT_WORLD = 0x3CD3
FLAG_COUNT = 18048


def flag_location(flag: int, world: int, current_world: int) -> tuple[int, int]:
    """(byte offset from the flag manager, bit) holding `flag` of `world` while `current_world` is loaded."""
    for first, end, live, saved, size in WORLD_RANGES:
        if first <= flag < end:
            relative = flag - first
            if world == current_world:
                return live + relative // 8, relative % 8
            return saved + (world - 1) * size + relative // 8, relative % 8
    if not 0 <= flag < FLAG_COUNT:
        raise ValueError(f"flag {flag} out of range")
    return flag // 8, flag % 8


def is_world_flag(flag: int) -> bool:
    return any(first <= flag < end for first, end, *_ in WORLD_RANGES)


@dataclass
class EventReward:
    map: str
    area: str
    function: str
    lot: int
    items: list[LotItem]
    flag: int | None  # the event flag that marks the reward as given (None: not found in the script)
    flag_source: str = ""  # SetEventFlag | CompleteEvent | once event (the event's own id) | ""
    other_flags: list[int] = field(default_factory=list)

    @property
    def world(self) -> int:
        return int(self.map[1:3])


_FUNCTION = re.compile(r"^function\s+([\w.:]+)\s*\(", re.M)
_REWARD = re.compile(r"proxy:GetRateItem\(\s*(\d+)\s*\)")
_SET_FLAG = re.compile(r"proxy:SetEventFlag\(\s*(\d+)\s*,\s*(true|1)\s*\)")
_COMPLETE = re.compile(r"proxy:CompleteEvent\(\s*(\d+)\s*\)")


def _once_registrations(text: str) -> dict[str, int]:
    """Handler name -> event id, for events registered with `once` (a once event's id is its completion flag)."""
    out = {}
    for line in text.splitlines():
        m = re.search(r"proxy:On\w+\(\s*(\d+)\s*,.*\"(\w+)\".*\bonce\s*\)", line)
        if m:
            out.setdefault(m.group(2), int(m.group(1)))
    return out


@dataclass
class EnemyKill:
    """A one-time death the scripts record (proxy:OnCharacterDead(flag, entity, handler, once)): bosses, NPCs,
    Primeval Demons, Crystal Lizards. Verified: Tower Knight (entity 801) sets 4224 on death."""
    map: str
    area: str
    flag: int
    entity: int
    part: str
    npc_param: int
    npc_name: str
    drops: dict[int, list[LotItem]] = field(default_factory=dict)

    @property
    def world(self) -> int:
        return int(self.map[1:3])


_DEAD = re.compile(r"proxy:OnCharacterDead\(\s*(\d+)\s*,\s*(\d+)\s*,\s*\"(\w+)\"\s*,\s*once\s*\)")


def enemy_kills(game: GameData) -> list[EnemyKill]:
    import struct

    from . import msb, souls

    npc_rows = souls.read_param(game.params["NpcParam"].data)
    npc_data = game.params["NpcParam"].data
    lot_offsets = [f.offset for f in souls.load_paramdef("NpcParam").fields if f.name.startswith("itemLotId_")]
    npcs = {r.id: (r.name, [struct.unpack_from("<i", npc_data, r.data_offset + o)[0] for o in lot_offsets])
            for r in npc_rows.rows}
    out = []
    script = game.dvdroot / "script"
    for path in sorted(script.glob("m0?_??_00_00.lua")):
        text = path.read_bytes().decode("cp932", "replace")
        deaths = {}
        for m in _DEAD.finditer(text):
            deaths.setdefault((int(m.group(1)), int(m.group(2))), m.group(3))
        if not deaths:
            continue
        enemies = {e.entity_id: e for e in msb.read_enemies(game.dvdroot / "map" / "mapstudio" / f"{path.stem}.msb")}
        for (flag, entity), _handler in sorted(deaths.items()):
            enemy = enemies.get(entity)
            npc_name, lots = npcs.get(enemy.npc_param, ("", [])) if enemy else ("", [])
            kill = EnemyKill(path.stem, AREAS.get(path.stem, path.stem), flag, entity, enemy.name if enemy else "",
                             enemy.npc_param if enemy else -1, npc_name)
            for lot in lots:
                if lot > 0 and (items := game.lot_items(lot)):
                    kill.drops[lot] = items
            out.append(kill)
    return out


def event_rewards(game: GameData) -> list[EventReward]:
    out = []
    script = game.dvdroot / "script"
    for path in sorted(script.glob("m0?_??_00_00.lua")):
        text = path.read_bytes().decode("cp932", "replace")
        starts = [(m.start(), m.group(1)) for m in _FUNCTION.finditer(text)] + [(len(text), "")]
        once = _once_registrations(text)
        for (begin, name), (end, _) in zip(starts, starts[1:]):
            body = text[begin:end]
            lots = [int(x) for x in _REWARD.findall(body)]
            if not lots:
                continue
            flags = [int(x) for x, _ in _SET_FLAG.findall(body)]
            completes = [int(x) for x in _COMPLETE.findall(body)]
            own = re.match(r"OnEvent_(\d+)", name)
            own_id = int(own.group(1)) if own else None
            if flags:
                flag = own_id if own_id in flags else flags[0]
                source = "SetEventFlag"
            elif completes:
                flag = own_id if own_id in completes else completes[0]
                source = "CompleteEvent"
            elif name in once:
                flag, source = once[name], "once event"
            else:
                flag, source = None, ""
            for lot in lots:
                items = game.lot_items(lot)
                if items:
                    out.append(EventReward(path.stem, AREAS.get(path.stem, path.stem), name, lot, items, flag, source,
                                           [f for f in flags if f != flag]))
    return out
