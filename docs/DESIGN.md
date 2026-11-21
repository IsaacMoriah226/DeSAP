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
| Map pickups (corpses, chests): 521 | yes, AP items can be there |
| Boss drops and boss rewards (demon souls, items given after the fight) | yes |
| Shops | the 13 limited-stock entries (one-time stock); buying one sends its check, their vanilla items go into the pool. Unlimited items stay vanilla. All are **missable** (the merchants can die or turn hostile). The 14th limited row (Filthy Woman's Stone of Ephemeral Eyes) restocks after every death, so it is not a location |
| Tutorial pickups | yes, **missable** (the tutorial cannot be revisited; decided 2026-11-20). The Vanguard fight and its rewards too |
| NPC-dependent pickups (Rydell's 2F East cells, Yurt's corpses in the Nexus, Demonbrandt behind the vanilla Mausoleum Key) | yes, **missable** |
| The Nexial Binding (first Nexus arrival) | no, vanilla (the return-to-Nexus item and the icon of other players' items) |
| The Pantheon's Stone of Ephemeral Eyes | no (the Pantheon only opens online) |
| Items only at pure white or pure black world tendency | **missable** (filler only) |
| One-time enemies with a fixed drop (decided 2026-11-20): Primeval Demons, the 4-1 Vanguard, the dragons, Fat Officials (Iron Key Ring, Bloody Iron Key), Miralda, Old King Doran, black phantoms (King's Tower, Satsuki, Rydell, Selen, Garl, Scirvir, invaders), Garl Vinland, the 5-2 slug and Shaman, the 2-1 sack miners | yes; tendency-only ones and drops that vanish on reload (bodies not saved) are **missable**. Random drops and friendly NPCs' kill drops are not locations |
| Crystal Lizards | no, vanilla drops |
| Respawning enemies | no, vanilla drops |
| NPC quest items and NPC gifts/trades | no, vanilla |
| Remake-only additions (Penetrator armor, coins, ...) | no, vanilla (they are not in the original-format data) |

Missable locations only get filler items.

### By the numbers (version 0.4.0)

| | |
| --- | --- |
| Locations | 656: 521 treasures, 37 boss and scripted rewards, 85 one-time enemy drops, 13 shop entries |
| Missable (filler only) | 118 |
| Items | 331 kinds: 27 progression (15 world locks, 12 keys), 226 useful, 78 filler |

## Items

- Classification after the Dark Souls III world: **progression** (world locks, keys and other items logic needs),
  **useful** (equipment, spells, upgrade materials, demon souls), **filler** (consumables, souls items, grass).
- Boss demon souls: **useful** (progression only if one is needed to finish the game).
- Keys and every other progression item are clearly marked as progression: the 15 world locks and every key a
  logic rule uses (the Iron Key Ring, the Bloody Iron Key, the Copper Key and the Prison of Hope keys: 27
  progression items in all). Keys nothing checks are useful.

## Options (YAML)

- **Remove stat requirements** for weapons, shields, catalysts and talismans. Spells have no requirement to cast;
  the only requirement the spell data has is the faith Saint Urbain asks before teaching God's Wrath, Anti-Magic
  Field and Recovery, which goes too.
- **Randomize starting loadout** (on by default; decided 2026-11-21): every class's weapons, shield and armor,
  DS3-style; weapons the class can use (any, with stat requirements removed), a catalyst or talisman stays, a bow
  stays a bow, armor of about the same weight that both body types can wear. The launcher shows the gear (the
  game's class preview cannot).
- **Auto-upgrade received weapons:** every weapon received (from this world or others) is upgraded to match the
  highest-upgraded weapon held, **proportionally** to each weapon's maximum, rounding up. Highest normal +10 means
  a boss weapon (max +5) arrives at +5; +8 means +4.
- **DeathLink** (included).

## Presentation

- Items for other worlds placed in Demon's Souls show as **"[Player]'s [Item]"** with the **Nexial Binding**
  icon, so it is clear an item went to someone else (done: named after the nearest corpse's items). In shops:
  **"[AP] [Player]'s [Item]"** (for now one generic "[AP] Item for another world").
- An in-game overlay (Futura-like font, colour-coded, adjustable, draggable) shows only what this player finds,
  sends and receives; a 3D map tracker and Universal Tracker show the logic.
- Nobody plays before the items are placed: the client pauses the game at the title until it is ready, and says
  so.
- Received items show the game's own pickup popup, as when picking something up.

## Open

- Weapon upgrade paths (Sharp, Quality, Crescent, ...): proportional to the path's own maximum.
- The Black Eye Stone (five invader phantoms share its one-time flag, so only the first gives it): not a location.
  The minibosses' New Moon Grass (LP 1-2 prison, IW 1-3 twice) are locations; two of them share one lot, so the
  client gives those by flag.

## Implementation notes (not design decisions)

- Locations and their flags: `docs/FINDINGS.md`, `tools/build_locations.py`.
- The client: `docs/CLIENT.md` (how placement, checks, delivery, world locks and DeathLink work, and what is still
  to test in game).
