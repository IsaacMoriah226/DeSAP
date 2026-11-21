# Design

Decisions by the designer (the project owner). The implementation follows this file; open points are marked.

## Goal

Reach the ending credits (beat the final boss). The only goal for now.

## Progression: world locks

- One AP item per world part, named by its number: **1-2, 1-3, 1-4, 2-1, 2-2, 2-3, 3-1, 3-2, 3-3, 4-1, 4-2, 4-3,
  5-1, 5-2, 5-3** (15 items). 1-1 is open from the start.
- Parts of a world are sequential: x-n needs both its lock item and x-(n-1) finished (its boss beaten), even when
  the x-n lock is held. Logic makes every x-n reachable before x-(n+1).
- The game has to keep players out of a part whose lock they lack (enforced by the client; see Implementation):
  a locked part cannot be warped to, and walking into it sends the player back to the Nexus.
- The vanilla archstone conditions stay on top of the locks (decided 2026-11-20):
  - 2-1, 3-1, 4-1, 5-1 also need Phalanx dead (the Monumental unseals those archstones after the first boss).
  - 1-3 (and so 1-4) also needs an archdemon of another world dead (the gate past the Tower Knight, flag 8035).
- The goal (credits) is False King Allant below the Nexus, reached once all five archdemons are dead (Old King
  Allant, Dragon God, Old Monk, Storm King, Maiden Astraea).

## Locations

| Kind | Location? |
| --- | --- |
| Map pickups (corpses, chests): 484 | yes, AP items can be there |
| Boss drops and boss rewards (demon souls, items given after the fight) | yes |
| Shops | the 13 limited-stock entries (one-time stock); buying one sends its check, their vanilla items go into the pool. Unlimited items stay vanilla. All are **missable** (the merchants can die or turn hostile). The 14th limited row (Filthy Woman's Stone of Ephemeral Eyes) restocks after every death, so it is not a location |
| Tutorial pickups | yes, **missable** (the tutorial cannot be revisited; decided 2026-11-20). The Vanguard fight and its rewards too |
| NPC-dependent pickups (Rydell's 2F East cells, Yurt's corpses in the Nexus, Demonbrandt behind the vanilla Mausoleum Key) | yes, **missable** |
| The Nexial Binding (first Nexus arrival) | no, vanilla (the return-to-Nexus item and the icon of other players' items) |
| The Pantheon's Stone of Ephemeral Eyes | no (the Pantheon only opens online) |
| Items only at pure white or pure black world tendency | **missable** (filler only) |
| Crystal Lizards | no, vanilla drops |
| Respawning enemies | no, vanilla drops |
| NPC quest items and NPC gifts/trades | no, vanilla |
| Remake-only additions (Penetrator armor, coins, ...) | no, vanilla (they are not in the original-format data) |

Missable locations only get filler items.

## Items

- Classification after the Dark Souls III world: **progression** (world locks, keys and other items logic needs),
  **useful** (equipment, spells, upgrade materials, demon souls), **filler** (consumables, souls items, grass).
- Boss demon souls: **useful** (progression only if one is needed to finish the game).
- Keys and every other progression item are clearly marked as progression: the 15 world locks and every key a
  logic rule uses (the Copper Key and the Prison of Hope keys). Keys nothing checks are useful.

## Options (YAML)

- **Remove stat requirements** for weapons and spells.
- **Auto-upgrade received weapons:** every weapon received (from this world or others) is upgraded to match the
  highest-upgraded weapon held, **proportionally** to each weapon's maximum, rounding up. Highest normal +10 means
  a boss weapon (max +5) arrives at +5; +8 means +4.
- **DeathLink** (included).

## Presentation

- Items for other worlds placed in Demon's Souls show as **"[Player]'s [Item]"** with the **Nexial Binding**
  icon, so it is clear an item went to someone else. In shops: **"[AP] [Player]'s [Item]"**.
- Received items show the game's own pickup popup, as when picking something up.

## Open

- Weapon upgrade paths (Sharp, Quality, Crescent, ...): proportional to the path's own maximum.
- Unique non-respawning enemies' drops (Fat Officials' keys, Miralda, NPC black phantoms, Garl Vinland): not
  locations yet (the Iron Key Ring and Bloody Iron Key stay vanilla; the logic uses where they drop).

## Implementation notes (not design decisions)

- Locations and their flags: `docs/FINDINGS.md`, `tools/build_locations.py`.
- World locks: the client watches the loaded map (the flag manager's world byte, `+0x3cd3`) and sends the player
  back to the Nexus when a locked part loads; archstones of locked parts stay locked.
- Placeholders: a location's item lot is rewritten in the loaded ItemLotParam when the client connects; the files
  on disk are not changed.
