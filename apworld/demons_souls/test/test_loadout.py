"""Starting loadouts: usable, within weight, deterministic, and in the slot data."""

import unittest
from random import Random

from ..loadout import ARMOR_ALLOWANCE, ARMOR_FIELDS, BOW, CATALYST, EQUIPMENT, MELEE, SHIELD, starting_loadouts
from . import DemonsSoulsTestBase


class LoadoutTest(unittest.TestCase):
    def test_usable_and_light_enough(self):
        for seed in range(30):
            for row_id, fields in starting_loadouts(Random(seed), False).items():
                row = EQUIPMENT["classes"][row_id]
                for field, item in fields.items():
                    if field in ARMOR_FIELDS:
                        continue
                    weapon = EQUIPMENT["weapons"][str(item)]
                    for stat, key in (("str", "baseStr"), ("dex", "baseDex"), ("mag", "baseMag"), ("fai", "baseFai")):
                        self.assertLessEqual(weapon[stat], row[key], f"{row['name']}: {weapon['name']}")
                    old = row[field + "_info"]["category"]
                    new = weapon["category"]
                    self.assertTrue((old in MELEE and new in MELEE) or old == new == SHIELD or old == new == BOW,
                                    f"{row['name']} {field}: category {old} became {new}")
                    self.assertNotEqual(old, CATALYST)
                armor = sum(EQUIPMENT["armor"][str(fields.get(f, row[f]))]["weight"]
                            if str(fields.get(f, row[f])) in EQUIPMENT["armor"] else row[f + "_weight"]
                            for f in ARMOR_FIELDS)
                limit = sum(row[f + "_weight"] for f in ARMOR_FIELDS) + ARMOR_ALLOWANCE
                self.assertLessEqual(armor, limit + 1e-6, row["name"])

    def test_armor_fits_both_body_types(self):
        for seed in range(30):
            for row_id, fields in starting_loadouts(Random(seed), False).items():
                for field in ARMOR_FIELDS:
                    if field in fields:
                        self.assertIn(EQUIPMENT["armor"][str(fields[field])]["gender"], (0, 3))

    def test_casters_keep_their_tools(self):
        for row_id, fields in starting_loadouts(Random(1), True).items():
            row = EQUIPMENT["classes"][row_id]
            for field in ("equip_Wep_Right", "equip_Subwep_Right", "equip_Wep_Left", "equip_Subwep_Left"):
                info = row.get(field + "_info")
                if info and info["category"] == CATALYST:
                    self.assertNotIn(field, fields)

    def test_deterministic(self):
        self.assertEqual(starting_loadouts(Random(9), False), starting_loadouts(Random(9), False))


class LoadoutSlotData(DemonsSoulsTestBase):
    def test_in_slot_data(self):
        loadouts = self.world.fill_slot_data()["starting_loadouts"]
        self.assertEqual(sorted(loadouts), sorted(EQUIPMENT["classes"]))
