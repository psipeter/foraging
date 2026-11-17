"""Instances for a design module whose sessions come from a table of knob settings (`cells.py`): one session of the foraging task per realised cell, in the table's order.

The session's reward is the realised value map (its gain included), its layout the realised tile settings, its world the world seed `cells.py` chose, its feedback maximum the best bush's
value rounded up; everything else is FOR's (`design/FOR.py`). The logged design (`designJson`) carries the knobs asked, the nuisance draw, the map and its descriptors, the anchor and what the
session earned for it, and the version of the recipe. A cell that was inaccessible has no session."""

import json

import cells
import factors
import value_maps
from design import Instance
from design import FOR


def realized(code):
    path = cells.REALIZED / f"{code}.json"
    return json.loads(path.read_text()) if path.exists() else {"cells": []}


def instances_of(code, data=None):
    out = []
    for c in (realized(code) if data is None else data)["cells"]:
        if c["status"] != "ok":
            continue
        n = len(out) + 1
        m, s = c["map"], c["settings"]
        valuemap = value_maps.ValueMap(tuple(value_maps.Bump(**b) for b in m["bumps"]), m["noise"], m["equaliser"])
        layout = {"tileRadius": s["tile_radius"], "tileSpread": s["tile_spread"]}
        fields = FOR._fields(s["tile_value_mode"], s["tile_within_mode"], layout, c["world_seed"], valuemap)
        session_fields = {"sessionDuration": float(c.get("duration", FOR.SECONDS)), "instructionsFile": f"Experiments/{code}/instructions_S{n}.txt", "isPractice": False, "crosshairRadius": FOR.CROSSHAIR_RADIUS,
                          "crosshairRingSizeDeg": FOR.CROSSHAIR_RING_DEG, **FOR.FEEDBACK_FIELDS, "rewardFeedbackMax": float(c["feedback_max"]), **FOR.RANKING_FIELDS}
        design = {"experiment": code, "index": n, "cell": c["id"], "knobs": c["knobs"], "nuisance_draw": c["draw"], "world_seed": c["world_seed"], "calibrator": c["calibrator"],
                  "anchor": {"agent": factors.ANCHOR_AGENT, "rate": factors.ANCHOR_RATE, "points": c.get("anchor_points", factors.anchor_points(120.0)), "duration": c.get("duration", FOR.SECONDS), "own_world_points": round(c["own_world_points"]), "own_world_oracle": round(c.get("own_world_oracle", 0)), "check_points": {a: round(v[0]) for a, v in c["achieved"]["points"].items()}},
                  **valuemap.describe()}
        out.append(Instance(f"{code}_S{n}", fields, session_fields, design))
    return out
