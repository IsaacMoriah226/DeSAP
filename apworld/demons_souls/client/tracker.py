"""The 3D map tracker: a local web page (data/tracker/index.html, three.js) served by the client, fed with what
the client knows: checked locations, what is in logic, the progression items received, where the player is.

- Logic: the world's own requirement tokens (data.py `requires`, `part_requirements`), evaluated the way the
  generator's regions do: a part is open when its archstone's requirements hold, a boss counts as defeated when
  its part is open (its boss event is reachable), repeated until nothing changes.
- Map shapes: tools/build_tracker_maps.py (the game's navmeshes, one scene per world).
- Server: http://127.0.0.1:PORT/ (local only), JSON at /api/static (once) and /api/state (polled).
"""

from __future__ import annotations

import json
import logging
import pkgutil
import socket
import threading
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..data import ITEMS, LOCATIONS
from ..parts import ARCHDEMON_PARTS, PART_BY_CODE, PARTS

logger = logging.getLogger("Client")

PORT = 38390  # (another free port if taken)
PACKAGE = __name__.rsplit(".", 2)[0]  # the world package (data files load from a packed .apworld too)
ITEM_BY_CODE = {item.code: item for item in ITEMS.values()}
PROGRESSION = [item for item in ITEMS.values() if item.classification == "progression"]


def part_requirements(code: str) -> tuple[str, ...]:
    from .. import part_requirements as requirements  # (the world module imports Archipelago)
    return requirements(code)


# --- logic ---------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Logic:
    open_parts: frozenset[str]  # "Tutorial", "Nexus" and the parts whose archstones' requirements hold
    bosses: frozenset[str]  # parts whose boss is reachable

    def satisfied(self, needs: Iterable[str], have: Counter) -> bool:
        return all(self.token(need, have) for need in needs)

    def token(self, need: str, have: Counter) -> bool:
        if need.startswith("any:"):
            return any(self.token(option, have) for option in need[4:].split("|"))
        if need.startswith("boss:"):
            return need[5:] in self.bosses
        if need.startswith("region:"):
            return need[7:] in self.open_parts
        if need.startswith("archdemons:"):
            return len(self.bosses & set(ARCHDEMON_PARTS)) >= int(need[11:])
        return have[need] > 0

    def in_logic(self, location, have: Counter) -> bool:
        return location.part in self.open_parts and self.satisfied(location.requires, have)


BOSS_EVENTS = [location for location in LOCATIONS.values() if location.kind == "boss_event"]


def evaluate(have: Counter) -> Logic:
    """What is reachable with the items `have` (name -> count), to a fixed point."""
    logic = Logic(frozenset({"Tutorial", "Nexus"}), frozenset())
    while True:
        open_parts = {"Tutorial", "Nexus"} | {part.code for part in PARTS
                                               if logic.satisfied(part_requirements(part.code), have)}
        bosses = {event.part for event in BOSS_EVENTS
                  if event.part in open_parts and logic.satisfied(event.requires, have)}
        new = Logic(frozenset(open_parts), frozenset(bosses))
        if new == logic:
            return logic
        logic = new


# --- what the page shows -------------------------------------------------------------------------------------

def _index() -> dict:
    return json.loads(pkgutil.get_data(PACKAGE, "data/tracker/maps.json").decode("utf-8"))


MAPS = _index()
AREA_OF_MAP = {map_id: area["id"] for area in MAPS["areas"] for map_id in area["maps"]}
AREA_OF_PART = {part["code"]: area["id"] for area in MAPS["areas"] for part in area["parts"]}


def area_of(location) -> str:
    return AREA_OF_MAP.get(location.game.get("map", ""), AREA_OF_PART.get(location.part, "nexus"))


def static_data() -> dict:
    """Everything that does not change during a session: areas, locations, progression items."""
    locations = []
    for location in LOCATIONS.values():
        if location.code is None:
            continue
        locations.append({
            "code": location.code, "name": location.name, "part": location.part, "kind": location.kind,
            "area": area_of(location), "position": location.game.get("position"),
            "missable": bool(location.missable or location.tendency),
        })
    parts = {part.code: {"code": part.code, "name": part.area, "boss": part.boss, "lock": part.lock_item,
                         "world": part.world} for part in PARTS}
    progression = [{"name": item.name, "group": "Archstones" if item.kind == "archipelago" else "Keys"}
                   for item in PROGRESSION]
    return {"areas": MAPS["areas"], "quantum": MAPS["quantum"], "locations": locations, "parts": parts,
            "progression": progression}


class TrackerFeed:
    """The page's /api/state, built from the client (cheap: the logic is recomputed only when items arrive)."""

    def __init__(self, ctx):
        self.ctx = ctx
        self._logic_key = None
        self._logic: tuple[Logic, Counter, list[int]] | None = None

    def logic(self) -> tuple[Logic, Counter, list[int]]:
        items = list(self.ctx.items_received)
        key = len(items)
        if self._logic is None or key != self._logic_key:
            have = Counter(ITEM_BY_CODE[i.item].name for i in items if i.item in ITEM_BY_CODE)
            logic = evaluate(have)
            ours = set(self.ctx.missing_locations) | set(self.ctx.checked_locations)
            in_logic = [location.code for location in LOCATIONS.values()
                        if location.code is not None and location.code in ours and logic.in_logic(location, have)]
            self._logic, self._logic_key = (logic, have, in_logic), key
        return self._logic

    def state(self) -> dict:
        ctx = self.ctx
        logic, have, in_logic = self.logic()
        player = None
        position, map_id = getattr(ctx, "last_position", None), getattr(ctx, "last_map", "")
        if position is not None and map_id in AREA_OF_MAP:
            player = {"area": AREA_OF_MAP[map_id], "map": map_id, "position": [round(c, 2) for c in position]}
        scouted = {}
        for code, item in list(ctx.scouted.items()):
            name = ctx.item_names.lookup_in_slot(item.item, item.player)
            scouted[code] = {"item": name, "player": ctx.player_names.get(item.player, "?"),
                             "own": item.player == ctx.slot, "flags": item.flags}
        return {
            "connected": bool(ctx.server and ctx.slot), "slot": ctx.player_names.get(ctx.slot, "") if ctx.slot else "",
            "game_running": bool(ctx.bridge.attached), "ready": bool(ctx.placed), "goal": bool(ctx.finished_game),
            "player": player,
            "checked": sorted(ctx.checked_locations),
            "locations": sorted(set(ctx.missing_locations) | set(ctx.checked_locations)),
            "in_logic": in_logic,
            "open_parts": sorted(logic.open_parts), "bosses": sorted(logic.bosses),
            "have": dict(have), "scouted": scouted,
        }


# --- the server ----------------------------------------------------------------------------------------------

CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".json": "application/json", ".bin": "application/octet-stream",
                 ".ttf": "font/ttf", ".js": "text/javascript"}


class _Server(ThreadingHTTPServer):
    """No port sharing: on Windows SO_REUSEADDR (http.server's default) lets a second server take a port in use."""
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class TrackerServer:
    def __init__(self, state: Callable[[], dict]):
        self.state = state
        self.httpd: ThreadingHTTPServer | None = None
        self.url = ""
        self._static: bytes | None = None

    def start(self) -> str:
        if self.httpd is not None:
            return self.url
        handler = self._handler()
        for port in (PORT, PORT + 1, PORT + 2, 0):
            try:
                self.httpd = _Server(("127.0.0.1", port), handler)
                break
            except OSError:
                continue
        if self.httpd is None:
            raise OSError("no free port for the tracker")
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/"
        threading.Thread(target=self.httpd.serve_forever, name="tracker", daemon=True).start()
        logger.info(f"Map tracker: {self.url}")
        return self.url

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd = None

    def file(self, path: str) -> tuple[bytes, str] | None:
        if path in ("/", "/index.html"):
            name = "data/tracker/index.html"
        elif path == "/fonts/Jost.ttf":
            name = "data/fonts/Jost.ttf"
        elif path.startswith("/maps/") and path.count("/") == 2 and path.endswith((".bin", ".json")):
            name = "data/tracker/" + path[6:]
        else:
            return None
        data = pkgutil.get_data(PACKAGE, name)
        if data is None:
            return None
        return data, CONTENT_TYPES.get(name[name.rfind("."):], "application/octet-stream")

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?", 1)[0]
                try:
                    if path == "/api/state":
                        body, kind = json.dumps(server.state()).encode("utf-8"), CONTENT_TYPES[".json"]
                    elif path == "/api/static":
                        if server._static is None:
                            server._static = json.dumps(static_data()).encode("utf-8")
                        body, kind = server._static, CONTENT_TYPES[".json"]
                    else:
                        found = server.file(path)
                        if found is None:
                            self.send_error(404)
                            return
                        body, kind = found
                except Exception as error:  # (a page request must never take the client down)
                    logger.debug(f"Tracker request {path} failed: {error!r}")
                    self.send_error(500)
                    return
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        return Handler
