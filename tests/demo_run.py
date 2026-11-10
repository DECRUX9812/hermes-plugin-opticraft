"""The 90-second demo path, runnable from the repo root.

Design an achromat, trace the user's own prescription, ask whether it is good,
ask whether it can be built, and look at the glass pair. Exactly what the video
shows.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opticraft.tools import make_handlers

h = make_handlers()


def show(title, payload, keys=None):
    print(f"\n## {title}")
    if keys:
        payload = {k: payload[k] for k in keys if k in payload}
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:1400])


design = json.loads(h["opticraft_design"]({"efl_mm": 100, "aperture_mm": 25}))
show("1. DESIGN IT", design, keys=("ok", "design", "colour"))
print("\n   report:", json.dumps(design["report"]["summary"], indent=None))
print("   vs the same lens in one element:", design["comparison"]["improvement"])

spec = [
    {"radius_mm": r, "thickness_mm": t, "glass": g, "semi_aperture_mm": 12.5}
    for r, t, g in zip(
        (design["design"]["radii_mm"]["r1"], design["design"]["radii_mm"]["r2"], design["design"]["radii_mm"]["r3"]),
        (design["design"]["element_thickness_mm"], design["design"]["element_thickness_mm"], 0.0),
        (design["design"]["crown"], design["design"]["flint"], ""),
    )
]

trace = json.loads(h["opticraft_trace"]({"surface_spec": spec}))
show("2. TRACE IT", trace, keys=("ok", "paraxial", "spot", "verdict"))

spot = json.loads(h["opticraft_spot"]({"surface_spec": spec}))
show("3. HOW SHARP", spot, keys=("ok", "verdict", "spot"))

tol = json.loads(h["opticraft_tolerance"]({"surface_spec": spec}))
show("4. CAN YOU BUILD IT", tol, keys=("ok", "focus_depth_mm", "worst_case_mm", "verdict"))

glass = json.loads(h["opticraft_glass"]({}))
show("5. THE GLASS PAIR", glass, keys=("ok", "count", "glasses"))
