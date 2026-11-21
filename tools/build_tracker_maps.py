"""Build the map tracker's shapes from the game dump into work/tracker_maps, to look at them. Players' clients
build their own on first use (apworld/demons_souls/client/mapshapes.py); nothing from the game ships.

    python tools/build_tracker_maps.py [game folder]
"""

import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from desap import local  # noqa: E402

OUT = local.path("work") / "tracker_maps"

spec = importlib.util.spec_from_file_location("mapshapes", ROOT / "apworld" / "demons_souls" / "client" / "mapshapes.py")
mapshapes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mapshapes)

if __name__ == "__main__":
    start = time.monotonic()
    index = mapshapes.build(Path(sys.argv[1]) if len(sys.argv) > 1 else local.require("game"), OUT)
    for area in index["areas"]:
        print(f"{area['id']}: {sum(p['count'] for p in area['parts'])} triangles")
    print(f"{OUT} in {time.monotonic() - start:.1f} s")
