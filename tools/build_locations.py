"""Write every treasure location (map, index, event flag, items) as JSON, from the game dump.

Usage: python -I build_locations.py [<out.json>] [<game folder>]   (default C:\\Dev\\DeSArchi\\work\\locations.json)
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from desap.gamedata import DEFAULT_GAME, GameData  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:\Dev\DeSArchi\work\locations.json")
    game = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_GAME
    rows = []
    for t in GameData(game).treasures():
        row = asdict(t)
        row["lots"] = {str(lot): items for lot, items in row["lots"].items()}
        row["stored_offset"], row["stored_bit"] = t.stored_offset
        rows.append(row)
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} treasures -> {out}")


if __name__ == "__main__":
    main()
