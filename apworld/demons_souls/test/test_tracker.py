"""The map tracker: its logic must agree with the generator's, and its data must cover the map."""

import json
import random
import struct
from collections import Counter

from BaseClasses import CollectionState

from ..client import tracker
from ..data import ITEMS, LOCATIONS
from . import DemonsSoulsTestBase


class TestTrackerLogic(DemonsSoulsTestBase):
    def _generator(self, names: list[str]) -> set[str]:
        state = CollectionState(self.multiworld)
        for name in names:
            state.collect(self.world.create_item(name), prevent_sweep=True)
        state.sweep_for_advancements()
        return {location.name for location in self.multiworld.get_locations(self.player)
                if location.address is not None and location.can_reach(state)}

    def _tracker(self, names: list[str]) -> set[str]:
        have = Counter(names)
        logic = tracker.evaluate(have)
        return {name for name, location in LOCATIONS.items()
                if location.code is not None and logic.in_logic(location, have)}

    def test_agrees_with_the_generator(self) -> None:
        """Random sets of the progression items (and none, and all): the same locations in logic."""
        progression = [item.name for item in tracker.PROGRESSION]
        rng = random.Random(7)
        cases = [[], progression] + [rng.sample(progression, rng.randint(1, len(progression))) for _ in range(40)]
        for names in cases:
            with self.subTest(items=sorted(names)):
                self.assertEqual(self._tracker(names), self._generator(names))

    def test_no_items(self) -> None:
        logic = tracker.evaluate(Counter())
        self.assertEqual(logic.open_parts, {"Tutorial", "Nexus", "1-1"})
        self.assertEqual(logic.bosses, {"1-1"})


class TestTrackerData(DemonsSoulsTestBase):
    def test_every_area_and_part_has_a_shape(self) -> None:
        import pkgutil
        index = tracker.MAPS
        self.assertEqual({a["id"] for a in index["areas"]}, {"nexus", "tutorial", "w1", "w2", "w3", "w4", "w5"})
        for area in index["areas"]:
            data = pkgutil.get_data(tracker.PACKAGE, "data/tracker/" + area["file"])
            triangles = sum(part["count"] for part in area["parts"])
            self.assertEqual(len(data), triangles * 9 * 2, area["id"])
            self.assertTrue(all(part["count"] > 0 for part in area["parts"]), area["id"])

    def test_every_location_is_in_an_area(self) -> None:
        areas = {a["id"] for a in tracker.MAPS["areas"]}
        static = tracker.static_data()
        self.assertEqual(len(static["locations"]), sum(1 for l in LOCATIONS.values() if l.code is not None))
        self.assertTrue(all(l["area"] in areas for l in static["locations"]))
        json.dumps(static)  # (served as JSON)

    def test_server_serves_the_page_and_data(self) -> None:
        from urllib.request import urlopen
        server = tracker.TrackerServer(lambda: {"ok": True})
        url = server.start()
        try:
            self.assertIn(b"three", urlopen(url).read())
            self.assertEqual(json.loads(urlopen(url + "api/state").read()), {"ok": True})
            self.assertIn("locations", json.loads(urlopen(url + "api/static").read()))
            self.assertGreater(len(urlopen(url + "maps/w1.bin").read()), 1000)
            self.assertGreater(len(urlopen(url + "fonts/Jost.ttf").read()), 1000)
        finally:
            server.stop()
