from __future__ import annotations

from dataclasses import dataclass

from Options import DeathLink, OptionGroup, PerGameCommonOptions, StartInventoryPool, Toggle


class RemoveStatRequirements(Toggle):
    """Remove the stat requirements of weapons, shields, catalysts, talismans and spells, so anything you find
    can be used right away (no "too weak" penalty)."""
    display_name = "Remove Stat Requirements"


class AutoUpgradeWeapons(Toggle):
    """Upgrade every weapon you receive to match your most upgraded weapon, in proportion to each weapon's own
    maximum, rounding up. For example, with a +10 weapon (the most a normal weapon can reach) a boss soul weapon
    (most +5) arrives at +5; with a +8 weapon it arrives at +4."""
    display_name = "Auto-Upgrade Received Weapons"


@dataclass
class DemonsSoulsOptions(PerGameCommonOptions):
    remove_stat_requirements: RemoveStatRequirements
    auto_upgrade_weapons: AutoUpgradeWeapons
    death_link: DeathLink
    start_inventory_from_pool: StartInventoryPool


option_groups = [
    OptionGroup("Equipment", [RemoveStatRequirements, AutoUpgradeWeapons]),
]
