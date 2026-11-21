from __future__ import annotations

from dataclasses import dataclass

from Options import DeathLink, DefaultOnToggle, OptionGroup, PerGameCommonOptions, StartInventoryPool, Toggle


class RemoveStatRequirements(Toggle):
    """Remove the stat requirements of weapons, shields, catalysts and talismans, so anything you find can be
    used right away (no "too weak" penalty). Spells keep theirs for now."""
    display_name = "Remove Stat Requirements"


class AutoUpgradeWeapons(Toggle):
    """Upgrade every weapon you receive to match your most upgraded weapon, in proportion to each weapon's own
    maximum, rounding up. For example, with a +10 weapon (the most a normal weapon can reach) a boss soul weapon
    (most +5) arrives at +5; with a +8 weapon it arrives at +4."""
    display_name = "Auto-Upgrade Received Weapons"


class RandomizeStartingLoadout(DefaultOnToggle):
    """Give every class random starting weapons, shield and armor, as Dark Souls III's randomizer does. Each class
    keeps its stats, spells, ring and items; its new weapons are ones it can use (any weapon with Remove Stat
    Requirements), its catalyst or talisman stays, a bow stays a bow, and its armor weighs about what it did. The
    launcher's Classes page shows each class's new gear (the game's own class preview still shows the usual gear)."""
    display_name = "Randomize Starting Loadout"


@dataclass
class DemonsSoulsOptions(PerGameCommonOptions):
    remove_stat_requirements: RemoveStatRequirements
    auto_upgrade_weapons: AutoUpgradeWeapons
    randomize_starting_loadout: RandomizeStartingLoadout
    death_link: DeathLink
    start_inventory_from_pool: StartInventoryPool


option_groups = [
    OptionGroup("Equipment", [RandomizeStartingLoadout, RemoveStatRequirements, AutoUpgradeWeapons]),
]
