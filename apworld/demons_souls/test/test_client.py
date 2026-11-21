"""The client's logic against a fake game (no emulator): save claiming, placement, checks, item delivery and its
skip rule, world locks, DeathLink, plus the pure helpers (flags, lots, weapon upgrades, the call stub)."""

from __future__ import annotations

import struct
from pathlib import Path
import unittest
from types import SimpleNamespace

from NetUtils import NetworkItem

from ..client import addresses as A
from ..client import params
from ..client.context import DemonsSoulsContext
from ..client.flags import (CLIENT_BLOCK, CLIENT_BLOCK_SIZE, CURRENT_WORLD, DELIVERED_BITS, IDENTITY_OFFSET,
                            RECEIVED_OFFSET, SNAPSHOT_SIZE, Flags, delivered_bit, flag_location)
from ..client.game import GameState, InventoryEntry
from ..client.gamecall import DATA, build_stub
from ..client.placement import (CHECKS, LOCATION_BY_CODE, LOCATION_INDEX, LOCK_CODES, PLACEHOLDER, game_item,
                                upgraded_weapon)
from ..data import ITEMS, LOCATIONS

TUTORIAL_UID, NEXUS_UID, GATES_UID, LORDS_PATH_UID = 0x08000000, 0x01000000, 0x02000000, 0x02010000


def location_code(name: str) -> int:
    return LOCATIONS[name].code


TREASURE = location_code("NX: New Moon Grass - ledge above Boldwin")
TREASURE_2 = next(code for code, location in LOCATION_BY_CODE.items()
                  if location.kind == "treasure" and location.game["map"] == "m02_00_00_00")
TREASURE_3 = next(code for code, location in LOCATION_BY_CODE.items()
                  if location.kind == "treasure" and location.game["map"] == "m02_01_00_00")
EVENT = location_code("GB 1-1: Lead Demon Soul - boss drop")
SHARED = location_code("IE 4-1: Gray Demon Soul - pit courtyard, miniboss drop")
CLUB, DAGGER, GRASS = ITEMS["Club"].code, ITEMS["Dagger"].code, ITEMS["Crescent Moon Grass"].code
OTHER_PLAYER = 2


class FakeGame:
    def __init__(self):
        self.flags = bytearray(SNAPSHOT_SIZE)
        self.flags[CURRENT_WORLD] = 8
        self.map_uid = TUTORIAL_UID
        self.in_game = True
        self.deaths = 0
        self.given: list[tuple[int, int, int]] = []
        self.removed: list[tuple[int, int, int]] = []
        self.kicks: list[int] = []
        self.kills = 0
        self.entries: list[InventoryEntry] = []
        self.tables: dict = {}
        self.patched: dict[str, dict] = {}
        self.live = SimpleNamespace(path=None)
        self.memory = object()
        self.attached = True
        self.exe_path = ""
        self.restored = 0

    # what the context calls
    def attach(self): pass
    def detach(self): pass

    def state(self) -> GameState:
        return GameState(self.in_game, self.map_uid, Flags(bytes(self.flags)), self.deaths,
                         getattr(self, "position", None))

    def inventory(self):
        return list(self.entries)

    def write_identity(self, identity: int) -> None:
        struct.pack_into("<Q", self.flags, IDENTITY_OFFSET, identity)

    def write_received(self, count: int) -> None:
        struct.pack_into("<I", self.flags, RECEIVED_OFFSET, count)

    def set_delivered(self, index: int) -> None:
        offset, bit = delivered_bit(index)
        self.flags[offset] |= 1 << bit

    def clear_client_flags(self) -> None:
        for i in range(CLIENT_BLOCK, CLIENT_BLOCK + CLIENT_BLOCK_SIZE):
            self.flags[i] = 0

    def give_items(self, items):
        self.given += items

    def remove_item(self, category, item_id, count=1):
        self.removed.append((category, item_id, count))
        self.entries = [e for e in self.entries if (e.category, e.item_id) != (category, item_id)]

    def warp_to_nexus(self, area):
        self.kicks.append(area)

    def kill_player(self):
        self.kills += 1

    def paused(self, record=None):
        import contextlib
        self.pauses = getattr(self, "pauses", 0) + 1
        return contextlib.nullcontext()

    def prepare(self, keys, everywhere=True):
        self.find_tables()
        return self.find_text_entries(keys)

    def find_tables(self):
        weapons = {base + level: 0 for base in (10000, 60000) for level in range(0, 11)}
        self.tables = {"ITEMLOT_PARAM_ST": [params.Table(0, {})], "SHOP_LINEUP_PARAM": [params.Table(0, {})],
                       "EQUIP_PARAM_WEAPON_ST": [params.Table(0, weapons)], "EQUIP_PARAM_GOODS_ST": [],
                       "MAGIC_PARAM_ST": [params.Table(0, {1000: 0, 2000: 0})]}
        return self.tables

    def patch_rows(self, table, writes):
        self.patched.setdefault(table, {}).update(writes)
        return len(writes)

    def rows_intact(self, table, writes):
        return True

    def restore_rows(self):
        self.restored += 1
        return 1

    def find_text_entries(self, keys):
        return {key: [i] for i, key in enumerate(keys)}

    def set_text(self, fields, text, key=""):
        self.texts = getattr(self, "texts", []) + [(tuple(fields), text)]

    def set_text_buffer(self, fields, text, key):
        self.set_text(fields, text)

    def tables_live(self):
        return bool(self.tables)

    # test helpers
    def set_flag(self, location_code: int) -> None:
        check = CHECKS[location_code]
        if check.counter:
            self.flags[check.flag // 8] = 1
            return
        offset, bit = flag_location(check.flag, check.world, self.flags[CURRENT_WORLD])
        self.flags[offset] |= 1 << bit

    def enter(self, map_uid: int) -> None:
        self.map_uid = map_uid
        self.flags[CURRENT_WORLD] = map_uid >> 24


class ClientTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ctx = DemonsSoulsContext(None, None)  # (starts a keep-alive task: needs a running loop)
        self.game = FakeGame()
        self.ctx.bridge = self.game
        self.ctx.slot, self.ctx.team, self.ctx.server_seed_name = 1, 0, "seed"
        self.ctx.missing_locations = set(LOCATION_BY_CODE)
        self.ctx.checked_locations = set()
        self.ctx.items_received = []
        self.ctx.slot_data = {"auto_upgrade_weapons": False, "remove_stat_requirements": True, "death_link": True}
        self.ctx.death_link_enabled = True

    async def asyncTearDown(self):
        self.ctx.keep_alive_task.cancel()

    def tick(self) -> dict:
        out = self.ctx.tick(self.ctx.view())
        self.ctx.checked_locations |= out["checks"]  # (the server's answer)
        self.ctx.missing_locations -= out["checks"]
        return out

    def scout(self, placements: dict[int, tuple[int, int]]) -> None:
        """location -> (item, player) for the given ones, a foreign filler for the rest."""
        self.ctx.scouted = {}
        for code in LOCATION_BY_CODE:
            item, player = placements.get(code, (GRASS, OTHER_PLAYER))
            self.ctx.scouted[code] = NetworkItem(item, code, player, 0)

    def receive(self, item: int, location: int, player: int) -> None:
        self.ctx.items_received.append(NetworkItem(item, location, player, 0))

    def loading_screen(self) -> None:
        self.game.in_game = False
        self.tick()
        self.game.in_game = True

    def placed_game(self) -> None:
        self.scout({TREASURE: (CLUB, 1), TREASURE_2: (CLUB, 1), EVENT: (DAGGER, 1)})
        self.tick()  # claims (tutorial), places
        self.assertTrue(self.ctx.placed)

    # --- saves --------------------------------------------------------------------------------------------------

    def test_claims_a_fresh_save_in_the_tutorial(self):
        self.tick()
        self.assertEqual(Flags(bytes(self.game.flags)).identity, self.ctx.identity)
        self.assertTrue(self.ctx.save_ok)

    def test_refuses_an_unclaimed_save_with_progress(self):
        self.game.enter(GATES_UID)
        self.tick()
        self.assertEqual(Flags(bytes(self.game.flags)).identity, 0)
        self.assertFalse(self.ctx.save_ok)
        self.ctx.claim_requested = True
        self.tick()
        self.assertTrue(self.ctx.save_ok)

    def test_refuses_another_slots_save(self):
        self.game.write_identity(12345)
        self.receive(GRASS, -1, 0)
        self.tick()
        self.assertFalse(self.ctx.save_ok)
        self.assertEqual(self.game.given, [])
        self.assertEqual(Flags(bytes(self.game.flags)).identity, 12345)

    def test_launcher_places_at_the_title_and_undoes_it_for_another_save(self):
        self.ctx.launcher_mode = True
        self.scout({TREASURE: (CLUB, 1)})
        self.game.in_game = False  # the title screen
        self.tick()
        self.assertTrue(self.ctx.placed)
        self.assertTrue(self.ctx.area_safe)
        self.game.in_game = True
        self.game.enter(GATES_UID)
        self.game.write_identity(12345)  # another seed's save
        self.tick()
        self.assertFalse(self.ctx.placed)
        self.assertEqual(self.game.restored, 1)

    def test_the_game_is_paused_until_ready(self):
        banners = []
        self.ctx.overlay = SimpleNamespace(set_banner=lambda parts, seconds=None: banners.append(parts),
                                           push=lambda parts: None)
        self.ctx.launcher_mode = True
        self.scout({TREASURE: (CLUB, 1)})
        self.game.in_game = False  # the title screen
        self.tick()
        self.assertEqual(self.game.pauses, 1)  # one pause around the whole placement
        self.assertTrue(self.ctx.placed)
        self.assertEqual(self.ctx.phase, "ready")
        self.assertIn("Preparing", banners[0][0][0])
        self.assertIn("New Game", "".join(text for text, _ in banners[-1]))
        self.tick()
        self.assertEqual(self.game.pauses, 1)  # placed: no more pauses

    def test_waits_for_the_item_tables(self):
        def not_loaded(keys, everywhere=True):
            raise LookupError("not yet")
        self.game.prepare = not_loaded
        self.ctx.launcher_mode = True
        self.scout({TREASURE: (CLUB, 1)})
        self.game.in_game = False
        self.tick()
        self.assertFalse(self.ctx.placed)
        self.assertEqual(self.ctx.phase, "preparing")  # (at the title: still says to wait)
        self.tick()
        self.assertEqual(self.game.pauses, 1)  # (not again before PLACE_RETRY)
        del self.game.prepare
        self.ctx.next_place_try = 0.0
        self.tick()
        self.assertTrue(self.ctx.placed)

    def test_overlay_banner_shows_with_messages_off(self):
        from ..client.overlay import Overlay
        from ..client.settings import OverlaySettings
        overlay = Overlay(OverlaySettings(enabled=False), lambda: None)
        plain = overlay.render().size[1]
        overlay.set_banner([("Preparing Archipelago", "gold"), (": the game is paused ...", "text")])
        self.assertGreater(overlay.render().size[1], plain)
        overlay.set_banner(None)
        self.assertEqual(overlay.render().size[1], plain)

    # --- placement ----------------------------------------------------------------------------------------------

    def test_placement(self):
        self.placed_game()
        lots = self.game.patched["ITEMLOT_PARAM_ST"]
        club = game_item(CLUB)
        self.assertEqual(lots[LOCATION_BY_CODE[TREASURE].game["lot"]], params.lot_bytes(*club, False))
        foreign = next(code for code in LOCATION_BY_CODE if LOCATION_BY_CODE[code].kind == "treasure"
                       and code not in (TREASURE, TREASURE_2))
        self.assertEqual(lots[LOCATION_BY_CODE[foreign].game["lot"]], params.lot_bytes(*PLACEHOLDER, False))
        self.assertEqual(lots[LOCATION_BY_CODE[SHARED].game["lot"]], params.lot_bytes(-1, 0, 0, False))
        self.assertIn(TREASURE, self.ctx.physical)
        self.assertNotIn(SHARED, self.ctx.physical)
        self.assertIn("EQUIP_PARAM_WEAPON_ST", self.game.patched)  # stat requirements removed
        self.assertEqual(self.game.patched["MAGIC_PARAM_ST"][2000],  # (and Urbain's faith to learn a miracle)
                         {params.MAGIC_FAITH_TO_LEARN: struct.pack("<h", -1)})

    # --- checks and delivery ------------------------------------------------------------------------------------

    def test_physical_pickup_is_not_given_twice(self):
        self.placed_game()
        self.loading_screen()  # the area reloads with the new lots
        self.game.set_flag(TREASURE)
        out = self.tick()
        self.assertIn(TREASURE, self.ctx.checked_locations)
        self.assertTrue(Flags(bytes(self.game.flags)).delivered(LOCATION_INDEX[TREASURE]))
        self.receive(CLUB, TREASURE, 1)  # the server's copy
        self.tick()
        self.assertEqual(self.game.given, [])
        self.assertEqual(Flags(bytes(self.game.flags)).received, 1)

    def test_treasure_picked_before_its_area_reloaded_is_given(self):
        self.placed_game()
        self.game.set_flag(TREASURE)  # no loading screen since the placement: the vanilla item was there
        self.tick()
        self.assertFalse(Flags(bytes(self.game.flags)).delivered(LOCATION_INDEX[TREASURE]))
        self.receive(CLUB, TREASURE, 1)
        self.tick()
        self.assertEqual(self.game.given, [game_item(CLUB)])

    def test_scripted_reward_is_physical_without_a_reload(self):
        self.placed_game()
        self.game.set_flag(EVENT)  # lots read when the reward is given: no reload needed
        self.tick()
        self.receive(DAGGER, EVENT, 1)
        self.tick()
        self.assertEqual(self.game.given, [])

    def test_collected_location_is_given(self):
        self.placed_game()
        self.receive(CLUB, TREASURE_2, 1)  # e.g. !collect: never picked up
        self.tick()
        self.assertEqual(self.game.given, [game_item(CLUB)])

    def test_flags_set_before_the_client_ran_are_not_marked(self):
        self.game.set_flag(TREASURE)
        self.placed_game()
        self.loading_screen()
        self.tick()
        self.assertIn(TREASURE, self.ctx.checked_locations)
        self.assertFalse(Flags(bytes(self.game.flags)).delivered(LOCATION_INDEX[TREASURE]))

    def test_items_from_others_batched_and_count_kept(self):
        self.placed_game()
        self.receive(GRASS, 1234, OTHER_PLAYER)
        self.receive(CLUB, 1235, OTHER_PLAYER)
        self.receive(LOCK_CODES["1-2 The Lord's Path"], 1236, OTHER_PLAYER)
        for _ in range(5):
            self.receive(GRASS, 2000, OTHER_PLAYER)
        self.tick()
        self.assertEqual(self.game.given, [game_item(GRASS), game_item(CLUB)] + [game_item(GRASS)] * 2)
        self.assertEqual(Flags(bytes(self.game.flags)).received, 5)  # (the lock took a place, nothing to give)
        self.tick()
        self.assertEqual(len(self.game.given), 7)
        self.assertEqual(Flags(bytes(self.game.flags)).received, 8)
        self.tick()
        self.assertEqual(len(self.game.given), 7)

    def test_placeholder_named_after_the_nearest_foreign_location(self):
        self.placed_game()
        nexus = LOCATION_BY_CODE[TREASURE]  # (in the Nexus, holding Club for this slot: not a placeholder)
        foreign = next(code for code, location in LOCATION_BY_CODE.items() if location.kind == "treasure"
                       and location.game["map"] == "m01_00_00_00" and code != TREASURE)
        self.game.enter(NEXUS_UID)
        self.game.position = tuple(LOCATION_BY_CODE[foreign].game["position"])
        self.ctx.player_names = {1: "Me", OTHER_PLAYER: "Friend"}
        self.ctx.slot_info = {1: SimpleNamespace(game="Demon's Souls Remake", name="Me"),
                              OTHER_PLAYER: SimpleNamespace(game="Demon's Souls Remake", name="Friend")}
        self.tick()
        self.assertTrue(any(text.startswith("Friend's ") for _fields, text in self.game.texts), self.game.texts)
        self.game.position = (9999.0, 0.0, 0.0)
        self.game.texts = []
        self.tick()
        self.assertTrue(self.game.texts and all(text == "Archipelago Item" for _f, text in self.game.texts))

    def test_each_item_of_a_corpse_gets_its_own_placeholder(self):
        from ..client.placement import NAME_KEYS, RANK, placeholder_for, placeholder_names
        corpse = [code for code, location in LOCATION_BY_CODE.items()
                  if location.name.startswith("GB 1-1:") and "hanging corpse, courtyard" in location.name
                  and location.game["index"] == 1]
        self.assertEqual(sorted(RANK[c] for c in corpse), [0, 1, 2, 3])
        self.assertEqual(len({placeholder_for(c) for c in corpse}), 3)
        items = [(RANK[c], SimpleNamespace(name=f"item{RANK[c]}")) for c in corpse]
        names = placeholder_names(items, lambda item: "Friend's " + item.name)
        self.assertEqual(names[NAME_KEYS[1]], "Friend's item1")
        self.assertEqual(names[NAME_KEYS[0]], "Friend's item0 and 1 more")

    def test_placeholders_are_removed(self):
        self.placed_game()
        self.game.entries = [InventoryEntry(PLACEHOLDER[0], PLACEHOLDER[1], 2)]
        self.tick()
        self.assertEqual(self.game.removed, [(PLACEHOLDER[0], PLACEHOLDER[1], 2)])

    def test_auto_upgrade(self):
        self.ctx.slot_data["auto_upgrade_weapons"] = True
        self.placed_game()
        self.game.entries = [InventoryEntry(0, 10008, 1)]  # Dagger+8
        self.receive(CLUB, 999, OTHER_PLAYER)
        self.tick()
        self.assertEqual(self.game.given, [(0, 60008, 1)])

    # --- world locks, DeathLink, goal ------------------------------------------------------------------------------

    def test_locked_part_kicks_to_the_nexus(self):
        self.placed_game()
        self.game.enter(GATES_UID)
        self.tick()
        self.assertEqual(self.game.kicks, [])
        self.game.enter(LORDS_PATH_UID)
        self.tick()
        self.assertEqual(self.game.kicks, [2])

    def test_unlocked_part_does_not_kick(self):
        self.placed_game()
        self.receive(LOCK_CODES["1-2 The Lord's Path"], 1, OTHER_PLAYER)
        self.game.enter(LORDS_PATH_UID)
        self.tick()
        self.assertEqual(self.game.kicks, [])

    def test_death_link(self):
        self.placed_game()
        self.game.enter(NEXUS_UID)
        self.tick()
        self.game.deaths += 1
        self.assertTrue(self.tick()["death"])
        self.ctx.pending_death = True
        self.tick()
        self.assertEqual(self.game.kills, 1)
        self.game.deaths += 1
        self.assertFalse(self.tick()["death"])  # the death DeathLink caused is not sent back

    def test_no_kill_in_the_tutorial(self):
        self.placed_game()
        self.ctx.pending_death = True
        self.tick()
        self.assertEqual(self.game.kills, 0)

    def test_goal(self):
        self.placed_game()
        self.game.enter(NEXUS_UID)
        offset, bit = flag_location(70, 1, 1)
        self.game.flags[offset] |= 1 << bit
        self.assertTrue(self.tick()["goal"])


class HelperTest(unittest.TestCase):
    def test_every_location_has_a_check(self):
        for code, location in LOCATION_BY_CODE.items():
            if location.game.get("flag_unverified"):
                self.assertNotIn(code, CHECKS)
                self.assertEqual(location.part, "Tutorial", "only the tutorial's treasure flags are unmeasured")
                continue
            check = CHECKS[code]
            self.assertTrue(0 <= check.flag < 18048, location.name)

    def test_treasure_flags_are_distinct(self):
        seen = {}
        for code, location in LOCATION_BY_CODE.items():
            if location.kind != "treasure":
                continue
            key = (location.game["map"][:3], location.game["flag"])
            spot = (location.game["map"], location.game["index"])
            self.assertEqual(seen.setdefault(key, spot), spot, f"{location.name}: flag shared with another treasure")

    def test_delivered_bits_fit(self):
        self.assertLessEqual(len(LOCATION_INDEX), DELIVERED_BITS)
        # the block is world 7's saved block of the world flag range, inside the snapshot
        self.assertEqual(flag_location(8192, 7, 1)[0], CLIENT_BLOCK)
        self.assertLessEqual(CLIENT_BLOCK + CLIENT_BLOCK_SIZE, SNAPSHOT_SIZE)

    def test_flag_location(self):
        self.assertEqual(flag_location(10242, 2, 2), (0x500, 2))  # verified pickups (docs/FINDINGS.md)
        self.assertEqual(flag_location(10242, 2, 1), (0x2E1C, 2))
        self.assertEqual(flag_location(4224, 2, 1), (528, 0))  # global

    def test_lot_bytes(self):
        writes = params.lot_bytes(0x40000000, 1000, 3, False)
        self.assertEqual(writes[4], struct.pack("<iiHHhhH", 0x40000000, 1000, 3, 1000, 0, 0, 0))
        self.assertEqual(writes[164], struct.pack("<iiH", 0, 0, 0))
        host = params.lot_bytes(0x40000000, 1000, 3, True)
        self.assertEqual(host[164], struct.pack("<iiH", 0x40000000, 1000, 3))
        self.assertEqual(host[4][4:8], b"\0\0\0\0")

    def test_upgrades(self):
        rows = {base + level for base in (10000, 21400) for level in range(0, 11)}
        rows |= {10011 + i for i in range(5)} | {30000 + level for level in range(0, 6)}  # Quality +1..5; a +5 path
        self.assertEqual(upgraded_weapon(30000, [10008], rows), 30004)  # 8/10 of +5, rounded up
        self.assertEqual(upgraded_weapon(30000, [10014], rows), 30004)  # Quality Dagger+4: 4/5 = 0.8
        self.assertEqual(upgraded_weapon(10000, [], rows), 10000)
        self.assertEqual(upgraded_weapon(10002, [10001], rows), 10002)  # never below its own level
        self.assertEqual(upgraded_weapon(160000, [10010], rows), 160000)  # ammunition

    def test_stub(self):
        try:
            import capstone
        except ImportError:
            self.skipTest("capstone is not installed")
        base = 0x7FF600000000
        code = build_stub(base)
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        listing = list(md.disasm(code, base))
        self.assertEqual(sum(i.size for i in listing), len(code))
        self.assertEqual(listing[-1].mnemonic, "ret")
        targets = {i.address + i.size + int(i.op_str.split("rip + ")[1].split("]")[0], 16)
                   for i in listing if "rip + " in i.op_str}
        self.assertEqual(targets, {base + DATA + 0x08, base + DATA + 0x0C, base + DATA + 0x10})

    def test_signatures_match_the_eboot(self):
        from . import local_path
        elf = (local_path("work") or Path(".")) / "eboot_01.007.000.elf"
        if not elf.exists():
            self.skipTest("the converted eboot is not here")
        data = elf.read_bytes()
        for address, expected in A.SIGNATURES.items():
            at = 0x4000 + address - 0x900000000
            self.assertEqual(data[at:at + len(expected) // 2].hex(), expected, hex(address))
