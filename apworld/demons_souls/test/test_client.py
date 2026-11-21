"""The client's logic against a fake game (no emulator): save claiming, placement, checks, item delivery and its
skip rule, world locks, DeathLink, plus the pure helpers (flags, lots, weapon upgrades, the call stub)."""

from __future__ import annotations

import struct
import unittest
from types import SimpleNamespace

from NetUtils import NetworkItem

from ..client import addresses as A
from ..client import params
from ..client.context import DemonsSoulsContext
from ..client.flags import (CURRENT_WORLD, DELIVERED_FLAG, FREE_END, IDENTITY_OFFSET, RECEIVED_OFFSET, SNAPSHOT_SIZE,
                            Flags, delivered_bit, flag_location)
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

    # what the context calls
    def attach(self): pass
    def detach(self): pass

    def state(self) -> GameState:
        return GameState(self.in_game, self.map_uid, Flags(bytes(self.flags)), self.deaths)

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
        for i in range(IDENTITY_OFFSET, FREE_END // 8):
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

    def find_tables(self):
        weapons = {base + level: 0 for base in (10000, 60000) for level in range(0, 11)}
        self.tables = {"ITEMLOT_PARAM_ST": [params.Table(0, {})], "SHOP_LINEUP_PARAM": [params.Table(0, {})],
                       "EQUIP_PARAM_WEAPON_ST": [params.Table(0, weapons)], "EQUIP_PARAM_GOODS_ST": []}
        return self.tables

    def patch_rows(self, table, writes):
        self.patched.setdefault(table, {}).update(writes)
        return len(writes)

    def rows_intact(self, table, writes):
        return True

    def find_text_entries(self, keys):
        return {key: [i] for i, key in enumerate(keys)}

    def set_text(self, fields, text):
        self.texts = getattr(self, "texts", []) + [(tuple(fields), text)]

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

    def test_items_from_others_one_per_tick_and_count_kept(self):
        self.placed_game()
        self.receive(GRASS, 1234, OTHER_PLAYER)
        self.receive(CLUB, 1235, OTHER_PLAYER)
        self.receive(LOCK_CODES["1-2 The Lord's Path"], 1236, OTHER_PLAYER)
        self.tick()
        self.assertEqual(self.game.given, [game_item(GRASS)])
        self.tick()
        self.tick()
        self.assertEqual(self.game.given, [game_item(GRASS), game_item(CLUB)])
        self.assertEqual(Flags(bytes(self.game.flags)).received, 3)
        self.tick()
        self.assertEqual(len(self.game.given), 2)

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
        self.assertLess(DELIVERED_FLAG + len(LOCATION_INDEX), FREE_END)

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
        from pathlib import Path
        elf = Path(r"C:\Dev\DeSArchi\work\eboot_01.007.000.elf")
        if not elf.exists():
            self.skipTest("the converted eboot is not here")
        data = elf.read_bytes()
        for address, expected in A.SIGNATURES.items():
            at = 0x4000 + address - 0x900000000
            self.assertEqual(data[at:at + len(expected) // 2].hex(), expected, hex(address))
