"""The Archipelago client for Demon's Souls (PS5 remake on KytyPS5).

    ArchipelagoLauncher -> "Demon's Souls Client", or
    python Launcher.py "Demon's Souls Client" -- --connect host:port --name slot

Each tick (GAME_TICK seconds) the game loop, off the event loop:
- attaches to kyty_emulator.exe (checks the game version, installs the call stub);
- reads the game state: character loaded, map, event flags, death count;
- claims or recognises the save (its Archipelago identity, in unused event flags), and stops on a save that belongs
  to another seed or slot;
- once the server's scouts are in: pauses the game for a few seconds, finds the param tables and rewrites lots and
  shop rows (placement.py), so nobody plays a world that is not ready (the overlay and the launcher say so);
- sends newly checked locations; gives received items (popup), keeping the count in the save;
- removes placeholder items, enforces the world locks (sends the player to the Nexus), DeathLink, the goal.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import struct
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
from .memory import thaw_recorded
from .profile import Emulator, Profile, ProfileError, data_dir
from .settings import LauncherSettings
from .placement import (CHECKS, GOAL_FLAG, GOAL_WORLD, LOCATION_BY_CODE, LOCATION_INDEX, LOCK_CODES, NAME_KEYS,
                        NAMING_RANGE, PLACEHOLDERS, PLACEHOLDER_TEXTS, SHOP_PLACEHOLDER, SHOP_PLACEHOLDER_TEXTS,
                        game_item, has_lot, nearest_foreign, placeholder_for, placeholder_names, shared,
                        upgraded_weapon)

GAME = "Demon's Souls Remake"
GAME_TICK = 0.25
ATTACH_RETRY = 2.0
KICK_RETRY = 15.0
SETTLE_SECONDS = 3.0  # after attaching, before the client writes anything (only live tables are written)
PLACE_RETRY = 3.0  # the item tables were not loaded yet: try again after this long
NARROW_TRIES = 4  # tries in the usual memory only (the game may still be booting) before searching everywhere
READY_BANNER_SECONDS = 20.0
PAUSE_RECORD = data_dir() / "paused.json"  # the threads a pause holds (resumed by the next client if this one dies)
GIVE_PER_TICK = 4  # items per game call (one popup each; batches of 2 and 8 verified in game)
PART_OF_MAP = {part.map: part for part in PARTS}
NEXIAL_BINDING = 1033


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

    def _cmd_tracker(self) -> bool:
        """Open the 3D map tracker in your browser."""
        url = self.ctx.open_tracker()
        if url:
            self.output(f"Map tracker: {url}")
        return bool(url)

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
        self.settings = LauncherSettings.load()
        self.profile = Profile()
        self.emulator_process = None
        self.launch_status = ""
        self.last_backup = 0.0
        self.overlay = None  # the in-game message window (GUI only; overlay.py)
        self.tracker = None  # the 3D map tracker's local web server (tracker.py)
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
        self.text_fields: dict[str, list[int]] = {}
        self.placeholder_names: dict[str, str] = {}
        self.lot_writes: dict[int, dict[int, bytes]] = {}
        self.shop_writes: dict[int, dict[int, bytes]] = {}
        self.physical: set[int] = set()  # locations whose lot or shop row gives this world's item by itself
        self.game_checked: set[int] | None = None  # locations whose flags are set (None: not read yet)
        self.last_deaths = -1
        self.last_kick = 0.0
        self.last_attach_try = 0.0
        self.attached_at = 0.0
        self.next_place_try = 0.0
        self.place_tries = 0
        self.phase = ""  # "preparing" (the game is paused while the items are placed), "ready", "" (neither yet)
        self.last_message = ""
        self.launcher_mode = False  # the emulator runs from the Archipelago profile: every save there is ours
        self.last_position = None  # the player's, for the map tracker (None: no character loaded)
        self.last_map = ""

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
            self.overlay_message([("DeathLink: ", "trap"), (data.get("cause") or f"{data.get('source', '?')} died",
                                                             "text")])

    def overlay_message(self, parts: list[tuple[str, str]]) -> None:
        if self.overlay is not None:
            self.overlay.push(parts)

    def overlay_banner(self, parts: list[tuple[str, str]] | None, seconds: float | None = None) -> None:
        """A notice pinned above the messages (shown even with the messages turned off); None removes it."""
        if self.overlay is not None:
            self.overlay.set_banner(parts, seconds)

    def on_print_json(self, args: dict) -> None:
        super().on_print_json(args)
        if self.overlay is None or args.get("type") not in ("ItemSend", "ItemCheat") or not self.slot:
            return
        from .overlay import item_color
        item, receiver = args["item"], args["receiving"]
        finder = item.player
        if self.slot not in (finder, receiver):
            return  # other players' items: the launcher's log only
        name = self.item_names.lookup_in_slot(item.item, receiver)
        color = item_color(item.flags)
        where = self.location_names.lookup_in_slot(item.location, finder) if item.location > 0 else ""
        if finder == receiver == self.slot:
            parts = [("You found your ", "text"), (name, color)] + ([(f" ({where})", "location")] if where else [])
        elif finder == self.slot:
            parts = [("You sent ", "text"), (name, color), (" to ", "text"),
                     (self.player_names.get(receiver, "?"), "player")] + ([(f" ({where})", "location")] if where else [])
        else:
            parts = [("You received ", "text"), (name, color), (" from ", "text"),
                     (self.player_names.get(finder, "Archipelago"), "player")]
        self.overlay.push(parts)

    async def disconnect(self, allow_autoreconnect: bool = False):
        self.slot_data = {}
        self.scouted = {}
        await super().disconnect(allow_autoreconnect)

    @property
    def identity(self) -> int:
        """The save's Archipelago identity for this seed, team and slot (never 0)."""
        text = f"{self.server_seed_name}:{self.team}:{self.slot}".encode()
        return int.from_bytes(hashlib.sha256(text).digest()[:8], "little") | 1

    def start_tracker(self) -> str:
        """Serve the map tracker (once); returns its address ("" if it could not start)."""
        if self.tracker is None:
            from .tracker import MapStore, TrackerFeed, TrackerServer
            self.tracker = TrackerServer(TrackerFeed(self).state, MapStore(data_dir() / "maps", self.game_folder))
        try:
            return self.tracker.start()
        except OSError as error:
            logger.warning(f"The map tracker could not start: {error}")
            return ""

    def game_folder(self) -> Path | None:
        """The Demon's Souls folder, from the KytyLauncher the launcher is set to (None if unknown)."""
        if not self.settings.kyty_launcher:
            return None
        return Emulator(Path(self.settings.kyty_launcher)).game_folder()

    def open_tracker(self) -> str:
        url = self.start_tracker()
        if url:
            import webbrowser
            webbrowser.open(url)
        return url

    def run_gui(self):
        from .gui import make_manager
        self.ui = make_manager(self)
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
                thawed = thaw_recorded(PAUSE_RECORD)  # (a client that died while the game was paused)
                if thawed:
                    logger.warning(f"Resumed the game ({thawed} threads a previous client left paused).")
            except (OSError, ValueError):
                pass
            try:
                self.bridge.attach()
                self.attached_at = time.monotonic()
                self.launcher_mode = self.in_profile(self.bridge.exe_path)
                if self.launcher_mode:
                    self.bridge.live.path = self.profile.live_file
                self.say("Attached to the emulator" + (" (Archipelago profile)." if self.launcher_mode else "."))
                if self.launcher_mode and self.slot and not self.placed:
                    self.wait_banner()
            except LookupError as error:
                self.say("Waiting for the game ..." if "starting" in str(error) else "Waiting for kyty_emulator.exe ...")
                return out
            except GameVersionError as error:
                self.say(str(error))
                return out
        self.periodic_backup()
        if not self.slot or self.server_seed_name is None:
            return out
        if time.monotonic() - self.attached_at < SETTLE_SECONDS:
            return out  # (let the game finish starting before anything is written)
        state = self.bridge.state()
        self.last_position, self.last_map = (state.position, state.map_id) if state.in_game else (None, "")
        if not state.in_game:
            # a loading screen or the title: the next area loads with the current lots (another save may be loaded
            # next; check_save tells)
            if self.launcher_mode:
                self.place(view, in_game=False)  # ready before a save is even loaded (Archipelago saves only)
            if self.placed:
                self.area_safe = True
            return out
        if not self.check_save(state):
            return out
        self.place(view, in_game=True)
        out["checks"] = self.find_checks(state, view)
        self.deliver(state, view)
        self.name_placeholder(state, view)
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
        if self.placed and not (identity == 0 and (state.area == A.TUTORIAL_AREA or self.claim_requested)):
            self.bridge.restore_rows()  # not this slot's save: the vanilla items again
            self.placed = False
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

    def place(self, view: View, in_game: bool = True) -> None:
        """Rewrite lots and shop rows once the scouts are in; repair them if the game reloaded its params. The game
        is paused meanwhile (a few seconds), so nothing is picked up, bought or created from the vanilla tables."""
        if not view.scouted or os.environ.get("DESAP_NO_WRITES"):
            return
        if self.placed:
            if not self.bridge.tables_live():
                self.say("The game moved its item tables: placing the items again.")
                self.placed = False
            elif self.bridge.rows_intact("ITEMLOT_PARAM_ST", self.lot_writes):
                return
            else:
                self.say("The game reloaded its item tables: placing the items again.")
                self.placed = False
        if time.monotonic() < self.next_place_try:
            return
        self.phase = "preparing"
        self.say("Preparing Archipelago: the game is paused for a few seconds ...")
        self.overlay_banner([("Preparing Archipelago", "gold"), (": the game is paused for a few seconds ...", "text")])
        started = time.monotonic()
        try:
            with self.bridge.paused(PAUSE_RECORD):
                done = self.write_placement(view)
        except BaseException:
            self.phase = ""
            self.overlay_banner(None)
            raise
        if not done:
            if in_game:
                self.phase = ""
                self.overlay_banner(None)
            else:
                self.wait_banner()  # (at the title: still not ready to start)
            self.next_place_try = time.monotonic() + PLACE_RETRY
            self.say("Waiting for the game to load its item tables ...")
            return
        self.phase = "ready"
        self.place_tries = 0
        logger.info(f"Items placed in {time.monotonic() - started:.1f} s.")
        if in_game:
            logger.info("Pickups lying in the area you are in change after its next loading screen (die, warp, or "
                        "quit and continue); bosses, scripted rewards and enemy drops already give their new items.")
            self.say("Ready: the Archipelago items are placed.")
            self.overlay_banner([("Ready: ", "location"), ("the Archipelago items are placed.", "text")],
                                READY_BANNER_SECONDS / 2)
        else:
            self.say("Ready! Start a New Game in Demon's Souls (or Continue this slot's save).")
            self.overlay_banner([("Ready! ", "location"), ("Start a New Game (or Continue this slot's save).", "text")],
                                READY_BANNER_SECONDS)

    def wait_banner(self) -> None:
        """The game is up but not ready: say so until it is (nobody should start a character before "Ready!")."""
        self.phase = "preparing"
        self.overlay_banner([("Preparing Archipelago", "gold"), (": wait for ", "text"), ("Ready!", "location"),
                             (" before you start.", "text")])

    def write_placement(self, view: View) -> bool:
        """The placement itself (with the game paused). False when the item tables are not loaded yet."""
        if self.bridge.tables and not self.bridge.tables_live():
            self.bridge.tables = {}
            self.texts_set = False
        texts = {**PLACEHOLDER_TEXTS, **SHOP_PLACEHOLDER_TEXTS}
        if not self.bridge.tables:
            self.place_tries += 1
            try:
                self.text_fields = self.bridge.prepare(list(texts), everywhere=self.place_tries > NARROW_TRIES)
            except LookupError:
                return False
            self.texts_set = False
        self.build_writes(view)
        self.bridge.patch_rows("ITEMLOT_PARAM_ST", self.lot_writes)
        if self.bridge.tables.get("SHOP_LINEUP_PARAM"):
            self.bridge.patch_rows("SHOP_LINEUP_PARAM", self.shop_writes)
        else:
            logger.warning("The shop table was not found: shops sell their usual items this session.")
        loadouts = self.slot_data.get("starting_loadouts") or {}
        if loadouts:  # the classes' gear: before a character is made, so the class selection shows it
            from ..loadout import EQUIPMENT
            offsets = EQUIPMENT["class_offsets"]
            self.bridge.patch_rows("CHARACTER_INIT_PARAM", {
                int(row): {offsets[field]: struct.pack("<i", item) for field, item in fields.items()}
                for row, fields in loadouts.items()})
        self.dress_placeholders()
        if self.slot_data.get("remove_stat_requirements"):
            rows = {row: {params.WEAPON_REQUIREMENTS: bytes(4)}
                    for copy in self.bridge.tables.get("EQUIP_PARAM_WEAPON_ST", []) for row in copy.rows}
            self.bridge.patch_rows("EQUIP_PARAM_WEAPON_ST", rows)
            rows = {row: {params.MAGIC_FAITH_TO_LEARN: struct.pack("<h", -1)}
                    for copy in self.bridge.tables.get("MAGIC_PARAM_ST", []) for row in copy.rows}
            self.bridge.patch_rows("MAGIC_PARAM_ST", rows)
        if not self.texts_set:
            missing = [key for key in texts if not self.text_fields.get(key)]
            if missing:
                logger.warning(f"Texts not found ({', '.join(missing)}): those items keep their own names.")
            for key, text in texts.items():
                if key in NAME_KEYS:
                    self.bridge.set_text_buffer(self.text_fields.get(key, []), text, key)
                else:
                    self.bridge.set_text(self.text_fields.get(key, []), text, key)
            self.placeholder_names = {key: PLACEHOLDER_TEXTS[key] for key in NAME_KEYS}
            self.texts_set = True
        self.placed = True
        self.area_safe = False
        return True

    def dress_placeholders(self) -> None:
        """The placeholders take the Nexial Binding's look (its icon id and the remake's item link)."""
        copies = self.bridge.tables.get("EQUIP_PARAM_GOODS_ST")
        if not copies or copies[0].row(NEXIAL_BINDING) is None:
            return
        source = copies[0].row(NEXIAL_BINDING)
        icon = self.bridge.memory.read(source + params.GOODS_ICON, 2)
        link = self.bridge.memory.read(source + params.GOODS_REMAKE_UI, 4)
        self.bridge.patch_rows("EQUIP_PARAM_GOODS_ST", {
            item: {params.GOODS_ICON: icon, params.GOODS_REMAKE_UI: link}
            for item in [p[1] for p in PLACEHOLDERS] + [SHOP_PLACEHOLDER[1]]})

    def in_profile(self, exe_path: str) -> bool:
        try:
            return Path(exe_path).resolve().parent == self.profile.root.resolve()
        except OSError:
            return False

    def periodic_backup(self) -> None:
        minutes = self.settings.backup_minutes
        if self.launcher_mode and minutes > 0 and time.monotonic() - self.last_backup > minutes * 60:
            self.last_backup = time.monotonic()
            try:
                if self.profile.backup():
                    logger.debug("Saves backed up.")
            except OSError as error:
                logger.warning(f"Save backup failed: {error}")

    async def launch(self) -> None:
        """The launcher's Play button: connect, prepare the profile, back up its saves, start the game."""
        s = self.settings
        s.save()
        emulator = Emulator(Path(s.kyty_launcher))
        problems = emulator.check() if s.kyty_launcher else ["choose KytyLauncher.exe first"]
        if problems:
            self.launch_status = "Cannot start: " + "; ".join(problems)
            logger.error(self.launch_status)
            return
        running_ours = False
        try:
            from .memory import GameMemory, find_pid
            with GameMemory(find_pid()) as running:
                running_ours = self.in_profile(running.image_path())
            if not running_ours:
                self.launch_status = "Another KytyPS5 (not the Archipelago profile) is running: close it first."
                logger.error(self.launch_status)
                return
        except LookupError:
            pass
        if not (self.server and self.slot and self.auth == s.slot):
            self.launch_status = f"Connecting to {s.server} as {s.slot} ..."
            self.username, self.auth = s.slot, None
            self.password = s.password or None
            await self.connect(s.server)
            for _ in range(300):
                if self.slot and self.scouted:
                    break
                await asyncio.sleep(0.1)
            else:
                self.launch_status = "Could not connect (check the server, the slot name and the password)."
                logger.error(self.launch_status)
                return
        if running_ours:
            self.launch_status = "Connected to the running game."
            return
        self.launch_status = "Preparing the Archipelago profile ..."
        try:
            await asyncio.to_thread(self.profile.sync, emulator)
            await asyncio.to_thread(self.profile.backup, "launch")
            self.bridge.live.path = self.profile.live_file
            self.emulator_process = await asyncio.to_thread(self.profile.start, emulator)
        except (ProfileError, OSError) as error:
            self.launch_status = f"Cannot start: {error}"
            logger.error(self.launch_status)
            return
        self.launch_status = "Starting Demon's Souls ..."
        logger.info("Starting Demon's Souls in the Archipelago profile; the items are placed at the title screen.")

    def status(self) -> dict:
        """What the launcher's Play page shows."""
        state = None
        if self.bridge.attached:
            try:
                state = self.bridge.state()
            except OSError:
                state = None
        return {
            "connected": bool(self.server and self.slot), "slot": self.player_names.get(self.slot, "") if self.slot else "",
            "scouted": len(self.scouted), "attached": self.bridge.attached, "launcher_mode": self.launcher_mode,
            "placed": self.placed, "save_ok": self.save_ok, "save_problem": self.save_problem,
            "in_game": bool(state and state.in_game), "map": state.map_id if state else "",
            "checked": len(self.checked_locations), "locations": len(self.checked_locations | self.missing_locations),
            "received": len(self.items_received), "goal": self.finished_game, "launch": self.launch_status,
            "progress": self.last_message if self.bridge.attached and not self.placed else "",
            "phase": self.phase if self.bridge.attached else "",
        }

    def weapon_rows(self) -> set[int]:
        copies = self.bridge.tables.get("EQUIP_PARAM_WEAPON_ST")
        return set(copies[0].rows) if copies else set()

    def build_writes(self, view: View) -> None:
        rows = self.weapon_rows()
        upgrade = bool(self.slot_data.get("auto_upgrade_weapons")) and bool(rows)
        held = self.held_weapons() if upgrade else []
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
                self.lot_writes[lot] = params.lot_bytes(*(own or placeholder_for(code)), host_only)
                if own:
                    self.physical.add(code)
            elif location.kind == "shop" and self.bridge.tables.get("SHOP_LINEUP_PARAM"):
                self.shop_writes[location.game["shop_row"]] = params.shop_bytes(*(own or SHOP_PLACEHOLDER)[:2])
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
        held = self.held_weapons() if rows else []
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

    def held_weapons(self) -> list[int]:
        try:
            return [e.item_id for e in self.bridge.inventory() if e.category == 0]
        except (OSError, LookupError):
            return []  # (no character loaded: the title screen)

    def name_placeholder(self, state: GameState, view: View) -> None:
        """The placeholders take the names of the nearest corpse's items for other worlds (one placeholder each)."""
        if not self.texts_set:
            return
        found, distance = nearest_foreign(state.position, state.area, view.scouted, view.checked, self.slot)
        if distance > NAMING_RANGE:
            found = []

        def describe(item) -> str:
            return (f"{self.player_names.get(item.player, 'Someone')}'s "
                    f"{self.item_names.lookup_in_slot(item.item, item.player)}")

        for key, name in placeholder_names(found, describe).items():
            if key in self.text_fields and self.placeholder_names.get(key) != name:
                self.bridge.set_text_buffer(self.text_fields[key], name, key)
                self.placeholder_names[key] = name

    def clean_placeholders(self) -> None:
        for placeholder in PLACEHOLDERS + (SHOP_PLACEHOLDER,):
            count = sum(e.count for e in self.bridge.inventory() if (e.category, e.item_id) == placeholder[:2])
            if count:
                self.bridge.remove_item(placeholder[0], placeholder[1], min(count, 16))

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
            ctx.overlay_message([("Goal complete: ", "progression"), ("False King Allant defeated.", "text")])
        await asyncio.sleep(GAME_TICK)
    await asyncio.to_thread(ctx.bridge.detach)
    if ctx.overlay is not None:
        ctx.overlay.stop()


def launch(*args: str) -> None:
    async def main(parsed) -> None:
        ctx = DemonsSoulsContext(parsed.connect, parsed.password)
        if parsed.name:
            ctx.auth = parsed.name
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        ctx.start_tracker()
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        loop_task = asyncio.create_task(game_loop(ctx), name="game loop")
        await ctx.exit_event.wait()
        ctx.server_address = None
        await loop_task
        await ctx.shutdown()

    import colorama

    Utils.init_logging("DemonsSoulsLauncher", exception_logger="Client")  # (Archipelago's logs folder)
    parser = get_base_parser(description="Demon's Souls Remake client (KytyPS5).")
    parser.add_argument("--name", default=None, help="Slot name to connect as.")
    parsed, _rest = parser.parse_known_args(args)
    colorama.just_fix_windows_console()
    asyncio.run(main(parsed))
    colorama.deinit()
