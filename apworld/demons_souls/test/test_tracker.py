"""The map tracker: its logic must agree with the generator's; its map shapes are built from the game on the
player's PC (nothing from the game ships)."""

import json
import random
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path

from BaseClasses import CollectionState

from ..client import tracker
from ..data import LOCATIONS
from . import DemonsSoulsTestBase, local_path

GAME_DUMP = local_path("game")  # (tests that need the game skip without it)


def needs_game(test):
    return unittest.skipUnless(GAME_DUMP and (GAME_DUMP / "cp11demonssouls").is_dir(), "no game dump on this PC")(test)


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
    @needs_game
    def test_shapes_built_from_the_game(self) -> None:
        from ..client import mapshapes
        with tempfile.TemporaryDirectory() as folder:
            index = mapshapes.build(GAME_DUMP, Path(folder))
            self.assertEqual([a["id"] for a in index["areas"]], [a[0] for a in mapshapes.AREAS])
            for area in index["areas"]:
                triangles = sum(part["count"] for part in area["parts"])
                self.assertEqual((Path(folder) / area["file"]).stat().st_size, triangles * 9 * 2, area["id"])
                self.assertTrue(all(part["count"] > 0 for part in area["parts"]), area["id"])
            self.assertIsNotNone(mapshapes.load(Path(folder)))

    def test_nothing_from_the_game_ships(self) -> None:
        world = Path(tracker.__file__).resolve().parent.parent
        self.assertEqual([p.name for p in (world / "data").rglob("*.bin")], [])

    def test_every_location_is_in_an_area(self) -> None:
        from ..client.mapshapes import AREAS
        areas = {a[0] for a in AREAS}
        static = tracker.static_data({"areas": [], "quantum": 32})
        self.assertEqual(len(static["locations"]), sum(1 for l in LOCATIONS.values() if l.code is not None))
        self.assertTrue(all(l["area"] in areas for l in static["locations"]))
        json.dumps(static)  # (served as JSON)

    def test_without_the_game_the_page_says_why(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = tracker.MapStore(Path(folder), lambda: None)
            store.ensure()
            self.assertEqual(store.status()["state"], "missing")
            self.assertIn("KytyLauncher", store.status()["message"])

    @needs_game
    def test_server_builds_and_serves_the_maps(self) -> None:
        from urllib.request import urlopen
        with tempfile.TemporaryDirectory() as folder:
            server = tracker.TrackerServer(lambda: {"ok": True}, tracker.MapStore(Path(folder), lambda: GAME_DUMP))
            url = server.start()
            try:
                self.assertIn(b"three", urlopen(url).read())
                self.assertEqual(json.loads(urlopen(url + "api/state").read()), {"ok": True})
                for _ in range(100):  # (built in the background on the first request)
                    static = json.loads(urlopen(url + "api/static").read())
                    if static["maps"]["state"] != "building":
                        break
                    time.sleep(0.1)
                self.assertEqual(static["maps"]["state"], "ready")
                self.assertIn("locations", static)
                self.assertGreater(len(urlopen(url + "maps/w1.bin").read()), 1000)
                self.assertGreater(len(urlopen(url + "fonts/Jost.ttf").read()), 1000)
            finally:
                server.stop()
