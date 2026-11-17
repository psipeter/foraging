"""Sessions from a table of knob settings (docs/SESSION_FACTORS_PLAN.md, milestone 5).

    ./venv/bin/python scripts/cells.py realize scripts/design/tables/FORX.json [--workers 6]
    ./venv/bin/python scripts/cells.py show FORX

A table (`scripts/design/tables/<code>.json`) lists cells: {"id", "class" (additive, multiplicative or nonseparable), "gini", "travel_time"} and optionally "interaction".
`realize` turns each cell into a session with `factors.realize` and writes `scripts/design/realized/<code>.json`, which the design module of that experiment reads (`design/tabled.py`), so that
`build_experiment.py <code>` is fast and deterministic: realising a cell takes minutes (simulation), building a session does not.

A table may give a "duration" in seconds (default 120): the sessions are realised at that length, with the anchor `factors.ANCHOR_RATE` times it.

A cell is realised with up to `draws` nuisance draws (which corner an additive map sits in, the start of the search that places the other maps' bumps), the first that holds the cap on the
best bush (`factors.MAX_PEAK`) and the anchor, and a cell for which none does is recorded as inaccessible with the reasons. The session's world is the cell's `world_seed` if it gives one, else `FIRST_WORLD_SEED + 100 * id` (no search among worlds since 2026-11-18: with the pool placed at random the learner's points vary 9 to 11 percent of the anchor across worlds; a placement that needs a redraw or a search will bring its own). The best bush
sets the session's `rewardFeedbackMax`. A rerun skips the cells already done.
"""

import argparse
import json
import math
import multiprocessing as mp
import time
from pathlib import Path

import numpy as np

import factors
import value_maps

ROOT = Path(__file__).resolve().parent.parent
TABLES = ROOT / "scripts" / "design" / "tables"
REALIZED = ROOT / "scripts" / "design" / "realized"
CALIBRATOR = 1                   # the version of the recipe (the anchor, the cap, the classes): raise it when a change would realise a cell differently
FIRST_WORLD_SEED = 9001
DRAWS = 6


def corner_of(cell_id, draw):
    """The corner an additive map sits in for a cell and a draw (which feature pays more when higher: a nuisance)."""
    rng = np.random.default_rng([int(cell_id), int(draw), 77])
    return tuple(float(c) for c in rng.integers(0, 2, 2))


def aspect_of(cell_id, draw):
    """The stretch of an additive map for a cell and a draw (round, 2:1 or 3:1, along shape or along colour: a nuisance), as `value_maps.corner_aspect`."""
    rng = np.random.default_rng([int(cell_id), int(draw), 78])
    return value_maps.corner_aspect(rng.choice(value_maps.CORNER_STRETCHES), bool(rng.integers(2)))


def realize_cell(cell, session="FOR_S1", draws=DRAWS, duration=120.0, **overrides):
    """The realised session of one cell (at `duration` seconds), or an `inaccessible` record naming why each draw failed. A cell may fix the nuisance of an additive map: `corner` ([shape, colour], each 0 or 1) and `aspect` (shape width over colour width), else they are drawn; `world_candidates` sets how many worlds are searched."""
    overrides = {**overrides, "session_duration": float(duration)}
    name, cid, gini = cell["class"], int(cell["id"]), float(cell["gini"])
    interaction = cell["interaction"] if "interaction" in cell else value_maps.default_interaction(name, gini)
    failed = []
    for draw in range(draws):
        try:
            r = factors.realize(session, gini, interaction, value_maps.CLASS_KLASS[name], float(cell["travel_time"]), corner=tuple(float(x) for x in cell["corner"]) if "corner" in cell else corner_of(cid, draw), aspect=float(cell["aspect"]) if "aspect" in cell else aspect_of(cid, draw), seed=draw, **overrides)
        except ValueError as e:
            failed.append({"draw": draw, "error": str(e)[:220]})
            continue
        valuemap, settings = r["map"], r["settings"]
        anchor = factors.anchor_points(duration)
        peak = valuemap.descriptors()["max"]
        return {"id": cid, "status": "ok", "knobs": {k: cell[k] for k in cell if k != "id"}, "interaction": interaction, "draw": draw, "failed_draws": failed, "map": valuemap.to_dict(), "settings": settings,
                "peak": peak, "feedback_max": min(factors.FRUIT_CAP, math.ceil(peak)), "duration": float(duration), "anchor_points": anchor, "world_seed": int(cell.get("world_seed", FIRST_WORLD_SEED + 100 * cid)), "achieved": r["achieved"], "within_tolerance": r["within_tolerance"], "calibrator": CALIBRATOR}
    return {"id": cid, "status": "inaccessible", "knobs": {k: cell[k] for k in cell if k != "id"}, "failed_draws": failed, "duration": float(duration), "calibrator": CALIBRATOR}


def _work(args):
    cell, session, duration = args
    t = time.time()
    record = realize_cell(cell, session, duration=duration)
    record["seconds"] = round(time.time() - t)
    return record


def realize_table(table_path, workers=6):
    table = json.loads(Path(table_path).read_text())
    code, session, duration = table["code"], table.get("session", "FOR_S1"), float(table.get("duration", 120.0))
    out = REALIZED / f"{code}.json"
    data = json.loads(out.read_text()) if out.exists() else {"code": code, "session": session, "duration": duration, "cells": []}
    done = {c["id"] for c in data["cells"]}
    todo = [c for c in table["cells"] if c["id"] not in done]
    print(f"{len(todo)} of {len(table['cells'])} cells to realise for {code}, {workers} at a time", flush=True)
    REALIZED.mkdir(exist_ok=True)
    with mp.Pool(workers) as pool:
        for record in pool.imap_unordered(_work, [(c, session, duration) for c in todo]):
            data["cells"].append(record)
            data["cells"].sort(key=lambda c: c["id"])
            out.write_text(json.dumps(data, indent=1))
            print(f"cell {record['id']}: {record['status']}" + (f", draw {record['draw']}, gain {record['map']['equaliser']['value']:.2f}, peak {record['peak']:.1f}, world seed {record['world_seed']}"
                  if record["status"] == "ok" else "; " + "; ".join(f["error"][:80] for f in record["failed_draws"][:2])) + f" ({record['seconds']} s)", flush=True)
    return out


def show(code):
    data = json.loads((REALIZED / f"{code}.json").read_text())
    for c in data["cells"]:
        k = c["knobs"]
        if c["status"] == "ok":
            a = c["achieved"]["points"]
            print(f"{c['id']:3d} {k['class']:15s} gini {k['gini']:.2f} travel {k['travel_time']:4.1f}: draw {c['draw']}, peak {c['peak']:.1f} (feedback maximum {c['feedback_max']}), "
                  f"learner {a[factors.ANCHOR_AGENT][0]:.0f} (anchor {c.get('anchor_points', factors.anchor_points(120.0)):.0f}) and oracle {a['oracle'][0]:.0f} on the check worlds, world {c['world_seed']}")
        else:
            print(f"{c['id']:3d} {k['class']:15s} gini {k['gini']:.2f}: INACCESSIBLE after {len(c['failed_draws'])} draws")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["realize", "show"])
    ap.add_argument("target")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if args.command == "realize":
        print("wrote", realize_table(args.target, args.workers))
    else:
        show(args.target)


if __name__ == "__main__":
    main()
