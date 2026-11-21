from BaseClasses import CollectionState, LocationProgressType

from ..data import ITEMS, LOCATIONS
from ..parts import LOCK_ITEMS, PART_BY_CODE, PARTS
from . import DemonsSoulsTestBase


def _open_location(part: str) -> str:
    """A location of a part with no requirement beyond entering the part."""
    for name, data in LOCATIONS.items():
        if data.part == part and data.code is not None and not data.requires:
            return name
    raise AssertionError(f"no unconditional location in {part}")


class TestWorldLocks(DemonsSoulsTestBase):
    def _state(self, *item_names: str) -> CollectionState:
        state = CollectionState(self.multiworld)
        for name in item_names:
            state.collect(self.world.create_item(name), prevent_sweep=True)
        state.sweep_for_advancements()
        return state

    def _reachable(self, location: str, state: CollectionState) -> bool:
        return self.multiworld.get_location(location, self.player).can_reach(state)

    def _open(self, part: str, state: CollectionState) -> bool:
        """Whether a part (its region) can be entered."""
        return self.multiworld.get_region(PART_BY_CODE[part].lock_item, self.player).can_reach(state)

    def test_1_1_is_open(self) -> None:
        self.assertTrue(self._open("1-1", self._state()))

    def _everything(self) -> list[str]:
        return [item.name for item in self.multiworld.itempool if item.player == self.player]

    def test_every_locked_part_needs_its_lock(self) -> None:
        for part in PARTS[1:]:
            without = [name for name in self._everything() if name != part.lock_item]
            self.assertFalse(self._open(part.code, self._state(*without)),
                             f"{part.code} reachable without {part.lock_item}")

    def test_first_parts_of_worlds_need_only_their_lock(self) -> None:
        for world in range(2, 6):
            part = PART_BY_CODE[f"{world}-1"]
            self.assertTrue(self._open(part.code, self._state(part.lock_item)), part.code)

    def test_later_parts_need_the_previous_boss(self) -> None:
        for part in PARTS:
            if part.number == 1:
                continue
            previous = PART_BY_CODE[f"{part.world}-{part.number - 1}"]
            if previous.code == "1-1":
                continue  # 1-1 needs no lock, its boss is always reachable: test_other_worlds_need_phalanx
            # Everything but the previous part's lock: its boss cannot be killed, so this part stays closed.
            without = [name for name in self._everything() if name != previous.lock_item]
            self.assertFalse(self._open(part.code, self._state(*without)),
                             f"{part.code} reachable without {previous.boss} dead")
            self.assertTrue(self._open(part.code, self._state(*self._everything())), part.code)

    def test_inner_ward_needs_another_worlds_archdemon(self) -> None:
        boletaria = [PART_BY_CODE[code].lock_item for code in ("1-2", "1-3", "1-4")]
        self.assertFalse(self._open("1-3", self._state(*boletaria)))
        stonefang = [PART_BY_CODE[code].lock_item for code in ("2-1", "2-2", "2-3")]
        self.assertTrue(self._open("1-3", self._state(*boletaria, *stonefang)))

    def test_other_worlds_need_phalanx(self) -> None:
        # Phalanx needs nothing, so a fresh state already has him dead: check the rule itself.
        from .. import part_requirements
        for world in range(2, 6):
            self.assertIn("boss:1-1", part_requirements(f"{world}-1"))
        self.assertIn("boss:1-1", part_requirements("1-2"))  # as the previous part of its world

    def test_goal_needs_all_five_archdemons(self) -> None:
        everything = [item.name for item in self.multiworld.itempool if item.player == self.player]
        self.assertTrue(self.multiworld.can_beat_game(self._state(*everything)))
        for code in ("1-4", "2-3", "3-3", "4-3", "5-3"):
            without = [name for name in everything if name != PART_BY_CODE[code].lock_item]
            self.assertFalse(self.multiworld.can_beat_game(self._state(*without)), f"beatable without {code}")

    def test_everything_reachable_with_all_items(self) -> None:
        state = self._state(*[item.name for item in self.multiworld.itempool if item.player == self.player])
        for name, data in LOCATIONS.items():
            if data.code is not None:
                self.assertTrue(self._reachable(name, state), name)
        self.assertTrue(self.multiworld.can_beat_game(state))

    def test_goal_needs_every_world(self) -> None:
        for part in PARTS:
            if part.code == "1-1":
                continue
            others = [name for name in LOCK_ITEMS if name != part.lock_item]
            self.assertFalse(self.multiworld.can_beat_game(self._state(*others)), f"beatable without {part.code}")


class TestPool(DemonsSoulsTestBase):
    def test_pool_matches_locations(self) -> None:
        own = [item for item in self.multiworld.itempool if item.player == self.player]
        locations = [loc for loc in self.multiworld.get_locations(self.player) if loc.address is not None]
        self.assertEqual(len(own), len(locations))

    def test_every_lock_item_once(self) -> None:
        names = [item.name for item in self.multiworld.itempool if item.player == self.player]
        for lock in LOCK_ITEMS:
            self.assertEqual(names.count(lock), 1, lock)
            self.assertEqual(ITEMS[lock].classification, "progression")

    def test_missable_locations_only_get_filler(self) -> None:
        for location in self.multiworld.get_locations(self.player):
            data = LOCATIONS.get(location.name)
            if data is not None and (data.missable or data.tendency):
                self.assertEqual(location.progress_type, LocationProgressType.EXCLUDED, location.name)


class TestNames(DemonsSoulsTestBase):
    run_default_tests = False

    def test_location_names_have_area_codes_and_world_numbers(self) -> None:
        prefixes = {f"{part.abbreviation} {part.code}" for part in PARTS} | {"NX", "TUT"}
        for name, data in LOCATIONS.items():
            if data.code is not None:
                self.assertIn(name.split(":", 1)[0], prefixes, name)

    def test_item_classifications(self) -> None:
        for name, item in ITEMS.items():
            self.assertIn(item.classification, ("progression", "useful", "filler"), name)
        self.assertTrue(any(item.classification == "filler" for item in ITEMS.values()))
