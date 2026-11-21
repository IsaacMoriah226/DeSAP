"""The Archipelago client for Demon's Souls (PS5 remake on KytyPS5).

    ArchipelagoLauncher -> "Demon's Souls Client", or
    python Launcher.py "Demon's Souls Client" -- --connect host:port --name slot

Each tick (GAME_TICK seconds) the game loop, off the event loop:
- attaches to kyty_emulator.exe (checks the game version, installs the call stub);
- reads the game state: character loaded, map, event flags, death count;
- claims or recognises the save (its Archipelago identity, in unused event flags), and stops on a save that belongs
  to another seed or slot;
- once the server's scouts are in: finds the param tables and rewrites lots and shop rows (placement.py);
- sends newly checked locations; gives received items (popup), keeping the count in the save;
- removes placeholder items, enforces the world locks (sends the player to the Nexus), DeathLink, the goal.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import Utils
from CommonClient import ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled, logger, server_loop
from NetUtils import ClientStatus, NetworkItem

from ..parts import PARTS
from . import addresses as A
from . import params
from .game import DemonsSoulsGame, GameState, GameVersionError
from .placement import (CHECKS, GOAL_FLAG, GOAL_WORLD, LOCATION_BY_CODE, LOCATION_INDEX, LOCK_CODES, PLACEHOLDER,
                        PLACEHOLDER_TEXTS, game_item, has_lot, shared, upgraded_weapon)

GAME = "Demon's Souls Remake"
GAME_TICK = 0.25
ATTACH_RETRY = 5.0
KICK_RETRY = 15.0
GIVE_PER_TICK = 1  # items per game call (one popup each; raise once batching is checked in game)
PART_OF_MAP = {part.map: part for part in PARTS}


@dataclass(frozen=True)
class View:
    """What a tick needs from the server state, copied on the event loop (the tick runs in a worker thread)."""
    locations: frozenset[int]  # this slot's locations
    checked: frozenset[int]
    items: tuple[NetworkItem, ...]  # received, in order
    scouted: dict[int, NetworkItem]


def default_live_file() -> Path:
    if os.environ.get("DESAP_LIVE_FILE"):
        return Path(os.environ["DESAP_LIVE_FILE"])
    return Path(os.environ.get("LOCALAPPDATA", ".")) / "DemonsSoulsAP" / "live.txt"


class DemonsSoulsCommandProcessor(ClientCommandProcessor):
    ctx: "DemonsSoulsContext"

    def _cmd_claim(self) -> bool:
        """Use the loaded save for this slot even though it already has progress (it was not made with this
        client)."""
        self.ctx.claim_requested = True
        self.output("The loaded save will be claimed for this slot on the next game tick.")
        return True

    def _cmd_game(self) -> bool:
        """Show what the client sees in the game."""
        self.output(self.ctx.game_summary())
        return True

    def _cmd_livefile(self, path: str = "") -> bool:
        """Show or set the emulator's live-control file (the emulator's KYTY_LIVE_FILE)."""
        if path:
            self.ctx.bridge.live.path = Path(path)
        self.output(f"Live-control file: {self.ctx.bridge.live.path}")
        return True

    def _cmd_deathlink(self) -> bool:
        """Turn DeathLink on or off for this session."""
        self.ctx.death_link_enabled = not self.ctx.death_link_enabled
        Utils.async_start(self.ctx.update_death_link(self.ctx.death_link_enabled))
        self.output(f"DeathLink {'on' if self.ctx.death_link_enabled else 'off'}.")
        return True


class DemonsSoulsContext(CommonContext):
    game = GAME
    command_processor = DemonsSoulsCommandProcessor
    items_handling = 0b111  # every item, own ones included (placement.py: what the game gives by itself)
    want_slot_data = True

    def __init__(self, server_address: str | None, password: str | None):
        super().__init__(server_address, password)
        self.bridge = DemonsSoulsGame(default_live_file())
        self.slot_data: dict[str, Any] = {}
        self.scouted: dict[int, NetworkItem] = {}
        self.claim_requested = False
        self.death_link_enabled = False
        self.pending_death = False
        self.expect_own_death_until = 0.0
        self.reset_game_session()

    def reset_game_session(self) -> None:
        """State tied to one attached game and one loaded save."""
        self.save_ok = False  # the loaded save is this slot's
        self.save_problem = ""
        self.placed = False  # lots and shop rows rewritten for this slot
        self.area_safe = False  # the area being played loaded after the rewrite (treasures are fixed at load)
        self.texts_set = False
        self.lot_writes: dict[int, dict[int, bytes]] = {}
        self.shop_writes: dict[int, dict[int, bytes]] = {}
        self.physical: set[int] = set()  # locations whose lot or shop row gives this world's item by itself
        self.game_checked: set[int] | None = None  # locations whose flags are set (None: not read yet)
        self.last_deaths = -1
        self.last_kick = 0.0
        self.last_attach_try = 0.0
        self.last_message = ""

    # --- server ---------------------------------------------------------------------------------------------------

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        if cmd == "Connected":
            self.slot_data = args.get("slot_data", {}) or {}
            from .. import DemonsSoulsWorld
            ours, seeds = DemonsSoulsWorld.world_version.as_simple_string(), self.slot_data.get("world_version")
            if seeds != ours:
                logger.warning(f"This seed was made with version {seeds} of the Demon's Souls world, this client is "
                               f"{ours}: use the matching .apworld, or locations may be checked wrongly.")
            self.scouted = {}
            self.placed = False
            self.death_link_enabled = bool(self.slot_data.get("death_link"))
            Utils.async_start(self.update_death_link(self.death_link_enabled))
            ours = sorted(self.missing_locations | self.checked_locations)
            Utils.async_start(self.send_msgs([{"cmd": "LocationScouts", "locations": ours, "create_as_hint": 0}]))
        elif cmd == "LocationInfo":
            for item in args["locations"]:
                self.scouted[item.location] = item

    def on_deathlink(self, data: dict) -> None:
        super().on_deathlink(data)
        if self.death_link_enabled:
            self.pending_death = True

    async def disconnect(self, allow_autoreconnect: bool = False):
        self.slot_data = {}
        self.scouted = {}
        await super().disconnect(allow_autoreconnect)

    @property
    def identity(self) -> int:
        """The save's Archipelago identity for this seed, team and slot (never 0)."""
        text = f"{self.server_seed_name}:{self.team}:{self.slot}".encode()
        return int.from_bytes(hashlib.sha256(text).digest()[:8], "little") | 1

    def run_gui(self):
        from kvui import GameManager

        class DemonsSoulsManager(GameManager):
            logging_pairs = [("Client", "Archipelago")]
            base_title = "Archipelago Demon's Souls Client"

        self.ui = DemonsSoulsManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")

    def game_summary(self) -> str:
        if not self.bridge.attached:
            return "Not attached to the emulator."
        state = self.bridge.state()
        save = "this slot's" if self.save_ok else self.save_problem or "not checked yet"
        return (f"In game: {state.in_game}, map {state.map_id or '?'}, deaths {state.death_count}; save: {save}; "
                f"items placed: {self.placed}; current area randomized: {self.area_safe}.")

    def say(self, message: str) -> None:
        if message != self.last_message:
            logger.info(message)
            self.last_message = message

    # --- the game loop (runs in a worker thread) ------------------------------------------------------------------

    def view(self) -> View:
        return View(frozenset(self.missing_locations | self.checked_locations), frozenset(self.checked_locations),
                    tuple(self.items_received), dict(self.scouted))

    def tick(self, view: View) -> dict:
        """One game tick; returns what to send to the server: {"checks": set, "death": bool, "goal": bool}."""
        out = {"checks": set(), "death": False, "goal": False}
        if not self.bridge.attached:
            if self.bridge.memory is not None:
                self.say("The emulator closed.")
                self.bridge.detach()
                self.reset_game_session()
            if time.monotonic() - self.last_attach_try < ATTACH_RETRY:
                return out
            self.last_attach_try = time.monotonic()
            try:
                self.bridge.attach()
                self.say("Attached to the emulator.")
            except LookupError:
                self.say("Waiting for kyty_emulator.exe ...")
                return out
            except GameVersionError as error:
                self.say(str(error))
                return out
        if not self.slot or self.server_seed_name is None:
            return out
        state = self.bridge.state()
        if not state.in_game:
            # a loading screen or the title: the next area loads with the current lots (another save may be loaded
            # next; check_save tells)
            if self.placed:
                self.area_safe = True
            return out
        if not self.check_save(state):
            return out
        self.place(view)
        out["checks"] = self.find_checks(state, view)
        self.deliver(state, view)
        self.clean_placeholders()
        self.enforce_locks(state, view)
        out["death"] = self.death_link(state)
        out["goal"] = not self.finished_game and state.flags.get(GOAL_FLAG, GOAL_WORLD)
        return out

    def check_save(self, state: GameState) -> bool:
        """Claim a fresh save, accept this slot's own, refuse any other."""
        identity = state.flags.identity
        if identity == self.identity:
            if not self.save_ok:
                self.say("This save belongs to this slot: the randomizer is active.")
            self.save_ok = True
            return True
        self.save_ok = False
        self.game_checked = None  # another save: what its flags say is not this slot's
        self.last_deaths = -1
        if identity == 0 and (state.area == A.TUTORIAL_AREA or self.claim_requested):
            self.bridge.clear_client_flags()
            self.bridge.write_identity(self.identity)
            self.claim_requested = False
            self.say("Claimed this save for this slot.")
            self.save_ok = True
            return True
        if identity == 0:
            self.save_problem = "a save with progress that was not made with this client"
            self.say("The loaded save was not started with Archipelago. Start a new character (the client claims it "
                     "in the tutorial), or type /claim to use this save anyway.")
        else:
            self.save_problem = "another slot's save"
            self.say("The loaded save belongs to another Archipelago seed or slot. Load the save you made for this "
                     "slot (or start a new character).")
        return False

    def place(self, view: View) -> None:
        """Rewrite lots and shop rows once the scouts are in; repair them if the game reloaded its params."""
        if not view.scouted:
            return
        if self.placed:
            if self.bridge.rows_intact("ITEMLOT_PARAM_ST", self.lot_writes):
                return
            self.say("The game reloaded its item tables: placing the items again.")
            self.placed = False
        if not self.bridge.tables:
            self.say("Looking for the game's item tables (about 30 seconds) ...")
            try:
                self.bridge.find_tables()
            except LookupError:
                return
        self.build_writes(view)
        self.bridge.patch_rows("ITEMLOT_PARAM_ST", self.lot_writes)
        if self.bridge.tables.get("SHOP_LINEUP_PARAM"):
            self.bridge.patch_rows("SHOP_LINEUP_PARAM", self.shop_writes)
        else:
            logger.warning("The shop table was not found: shops sell their usual items this session.")
        if self.slot_data.get("remove_stat_requirements"):
            rows = {row: {params.WEAPON_REQUIREMENTS: bytes(4)}
                    for copy in self.bridge.tables.get("EQUIP_PARAM_WEAPON_ST", []) for row in copy.rows}
            self.bridge.patch_rows("EQUIP_PARAM_WEAPON_ST", rows)
        if not self.texts_set:
            self.say("Setting the text of items for other worlds (about a minute) ...")
            fields = self.bridge.find_text_entries(list(PLACEHOLDER_TEXTS))
            for key, text in PLACEHOLDER_TEXTS.items():
                self.bridge.set_text(fields[key], text)
            self.texts_set = True
        self.placed = True
        self.area_safe = False
        self.say("Items placed. Pickups lying in the area you are in change after its next loading screen (die, "
                 "warp, or quit and continue); bosses, scripted rewards and enemy drops already give their new items.")

    def weapon_rows(self) -> set[int]:
        copies = self.bridge.tables.get("EQUIP_PARAM_WEAPON_ST")
        return set(copies[0].rows) if copies else set()

    def build_writes(self, view: View) -> None:
        rows = self.weapon_rows()
        upgrade = bool(self.slot_data.get("auto_upgrade_weapons")) and bool(rows)
        held = [e.item_id for e in self.bridge.inventory() if e.category == 0] if upgrade else []
        self.lot_writes, self.shop_writes, self.physical = {}, {}, set()
        for code, item in view.scouted.items():
            location = LOCATION_BY_CODE.get(code)
            if location is None:
                continue
            own = game_item(item.item) if item.player == self.slot else None
            if own and own[0] == 0 and upgrade:
                own = (own[0], upgraded_weapon(own[1], held, rows), own[2])
            if has_lot(location):
                lot = location.game["lot"]
                host_only = bool(location.game.get("host_only"))
                if shared(location):  # the client gives these when their flags turn on
                    self.lot_writes[lot] = params.lot_bytes(-1, 0, 0, host_only)
                    continue
                self.lot_writes[lot] = params.lot_bytes(*(own or PLACEHOLDER), host_only)
                if own:
                    self.physical.add(code)
            elif location.kind == "shop" and self.bridge.tables.get("SHOP_LINEUP_PARAM"):
                self.shop_writes[location.game["shop_row"]] = params.shop_bytes(*(own or PLACEHOLDER)[:2])
                if own:
                    self.physical.add(code)

    def find_checks(self, state: GameState, view: View) -> set[int]:
        """Newly checked locations; marks the ones the game just delivered by itself (placement.py)."""
        found = {code for code in view.locations if code in CHECKS and CHECKS[code].done(state.flags)}
        if self.game_checked is None:
            self.game_checked = found  # what the save already had: who delivered it is unknown
        else:
            for code in found - self.game_checked:
                location = LOCATION_BY_CODE[code]
                if self.placed and code in self.physical and (location.kind != "treasure" or self.area_safe):
                    self.bridge.set_delivered(LOCATION_INDEX[code])
            self.game_checked |= found
        return found - view.checked

    def deliver(self, state: GameState, view: View) -> None:
        """Give received items from the save's count on, skipping what the game gave by itself."""
        given = state.flags.received
        if given >= len(view.items):
            return
        rows = self.weapon_rows() if self.slot_data.get("auto_upgrade_weapons") else set()
        held = [e.item_id for e in self.bridge.inventory() if e.category == 0] if rows else []
        batch: list[tuple[int, int, int]] = []
        index = given
        while index < len(view.items) and len(batch) < GIVE_PER_TICK:
            item = view.items[index]
            index += 1
            if item.player == self.slot and item.location in LOCATION_INDEX \
                    and state.flags.delivered(LOCATION_INDEX[item.location]):
                continue  # the game already handed this one out
            thing = game_item(item.item)
            if thing is None:
                continue  # a world lock: nothing to give in the game
            if thing[0] == 0 and rows:
                thing = (thing[0], upgraded_weapon(thing[1], held, rows), thing[2])
            batch.append(thing)
        if batch:
            self.bridge.give_items(batch)
        self.bridge.write_received(index)

    def clean_placeholders(self) -> None:
        count = sum(e.count for e in self.bridge.inventory() if (e.category, e.item_id) == PLACEHOLDER[:2])
        if count:
            self.bridge.remove_item(PLACEHOLDER[0], PLACEHOLDER[1], min(count, 16))

    def enforce_locks(self, state: GameState, view: View) -> None:
        part = PART_OF_MAP.get(state.map_id)
        if part is None or part.code == "1-1":
            return
        if any(item.item == LOCK_CODES[part.lock_item] for item in view.items):
            return
        if time.monotonic() - self.last_kick < KICK_RETRY:
            return
        self.last_kick = time.monotonic()
        self.say(f"{part.code} {part.area} is locked (you need \"{part.lock_item}\"): back to the Nexus.")
        self.bridge.warp_to_nexus(state.area)

    def death_link(self, state: GameState) -> bool:
        died = self.last_deaths != -1 and state.death_count > self.last_deaths
        self.last_deaths = state.death_count
        if self.pending_death and state.area != A.TUTORIAL_AREA:  # (the tutorial blocks death)
            self.pending_death = False
            self.expect_own_death_until = time.monotonic() + 30
            self.bridge.kill_player()
        if died and time.monotonic() < self.expect_own_death_until:
            self.expect_own_death_until = 0.0
            return False  # the death DeathLink caused
        return died and self.death_link_enabled


async def game_loop(ctx: DemonsSoulsContext) -> None:
    while not ctx.exit_event.is_set():
        try:
            out = await asyncio.to_thread(ctx.tick, ctx.view())
        except Exception as error:  # one bad tick must not end the loop
            logger.exception(f"Game tick failed: {error}")
            out = {"checks": set(), "death": False, "goal": False}
            await asyncio.sleep(2)
        if out["checks"] and ctx.server and ctx.slot:
            await ctx.check_locations(out["checks"])
        if out["death"] and ctx.server:
            await ctx.send_death(f"{ctx.player_names.get(ctx.slot, 'Someone')} died in Boletaria.")
        if out["goal"] and ctx.server and not ctx.finished_game:
            await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
            ctx.finished_game = True
            logger.info("Goal: False King Allant defeated.")
        await asyncio.sleep(GAME_TICK)
    await asyncio.to_thread(ctx.bridge.detach)


def launch(*args: str) -> None:
    async def main(parsed) -> None:
        ctx = DemonsSoulsContext(parsed.connect, parsed.password)
        if parsed.name:
            ctx.auth = parsed.name
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        loop_task = asyncio.create_task(game_loop(ctx), name="game loop")
        await ctx.exit_event.wait()
        ctx.server_address = None
        await loop_task
        await ctx.shutdown()

    import colorama

    parser = get_base_parser(description="Demon's Souls Remake client (KytyPS5).")
    parser.add_argument("--name", default=None, help="Slot name to connect as.")
    parsed, _rest = parser.parse_known_args(args)
    colorama.just_fix_windows_console()
    asyncio.run(main(parsed))
    colorama.deinit()
