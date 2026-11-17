"""Sessions from a table of knob settings (docs/SESSION_FACTORS_PLAN.md, milestone 5).

    ./venv/bin/python scripts/cells.py realize scripts/design/tables/FORX.json [--workers 6]
    ./venv/bin/python scripts/cells.py reseed FORX            # choose the worlds again, the cells kept
    ./venv/bin/python scripts/cells.py show FORX

A table (`scripts/design/tables/<code>.json`) lists cells: {"id", "class" (additive, multiplicative or nonseparable), "gini", "travel_time", "diversity"} and optionally "interaction".
`realize` turns each cell into a session with `factors.realize` and writes `scripts/design/realized/<code>.json`, which the design module of that experiment reads (`design/tabled.py`), so that
`build_experiment.py <code>` is fast and deterministic: realising a cell takes minutes (simulation), building a session does not.

A table may give a "duration" in seconds (default 120): the sessions are realised at that length, with the anchor `factors.ANCHOR_RATE` times it.

A cell is realised with up to `draws` nuisance draws (which corner an additive map sits in, the start of the search that places the other maps' bumps), the first that holds the cap on the
best bush (`factors.MAX_PEAK`) and the anchor, and a cell for which none does is recorded as inaccessible with the reasons. The session's own world is then chosen among
`WORLD_CANDIDATES` world seeds on two criteria: the anchor agent's points near the anchor and the oracle's points near their average over the check worlds (the oracle's points are the steadiest
measure of how good a world is), the larger of the two relative gaps being the least (a session is one world, and the points of one world vary by 30 to 60 percent), and the best bush
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
WORLD_CANDIDATES = 100              # the points of one world vary a great deal (a standard deviation of 30 to 60 percent of the anchor under a high contrast), and two criteria must hold, so the world is searched for among many
DRAWS = 6


def corner_of(cell_id, draw):
    """The corner an additive map sits in for a cell and a draw (which feature pays more when higher: a nuisance)."""
    rng = np.random.default_rng([int(cell_id), int(draw), 77])
    return tuple(float(c) for c in rng.integers(0, 2, 2))


def choose_world(session, valuemap, settings, cell_id, anchor, oracle_expected, **overrides):
    """The world seed (among `WORLD_CANDIDATES` of the cell) where the anchor agent's points are nearest `anchor` and the oracle's nearest `oracle_expected` (the larger relative gap is minimised):
    {"seed", "points" (the anchor agent's on it), "oracle", "candidate_points", "candidate_oracle"}."""
    seeds = [FIRST_WORLD_SEED + 100 * int(cell_id) + k for k in range(WORLD_CANDIDATES)]
    both = [factors.points_on_world(session, valuemap, settings, s, agents=(factors.ANCHOR_AGENT, "oracle"), **overrides) for s in seeds]
    mine, oracle = np.array([b[factors.ANCHOR_AGENT] for b in both]), np.array([b["oracle"] for b in both])
    best = int(np.argmin(np.maximum(np.abs(mine - anchor) / anchor, np.abs(oracle - oracle_expected) / oracle_expected)))
    return {"seed": seeds[best], "points": float(mine[best]), "oracle": float(oracle[best]), "candidate_points": mine.tolist(), "candidate_oracle": oracle.tolist()}


def realize_cell(cell, session="FOR_S1", draws=DRAWS, duration=120.0, **overrides):
    """The realised session of one cell (at `duration` seconds), or an `inaccessible` record naming why each draw failed."""
    overrides = {**overrides, "session_duration": float(duration)}
    name, cid, gini = cell["class"], int(cell["id"]), float(cell["gini"])
    interaction = cell["interaction"] if "interaction" in cell else value_maps.default_interaction(name, gini)
    failed = []
    for draw in range(draws):
        try:
            r = factors.realize(session, gini, interaction, value_maps.CLASS_KLASS[name], float(cell["travel_time"]), float(cell["diversity"]), corner=corner_of(cid, draw), seed=draw, **overrides)
        except ValueError as e:
            failed.append({"draw": draw, "error": str(e)[:220]})
            continue
        valuemap, settings = r["map"], r["settings"]
        anchor = factors.anchor_points(duration)
        world = choose_world(session, valuemap, settings, cid, anchor, r["achieved"]["points"]["oracle"][0], **overrides)
        peak = valuemap.descriptors()["max"]
        return {"id": cid, "status": "ok", "knobs": {k: cell[k] for k in cell if k != "id"}, "interaction": interaction, "draw": draw, "failed_draws": failed, "map": valuemap.to_dict(), "settings": settings,
                "peak": peak, "feedback_max": min(factors.FRUIT_CAP, math.ceil(peak)), "duration": float(duration), "anchor_points": anchor, "world_seed": world["seed"], "own_world_points": world["points"],
                "own_world_oracle": world["oracle"], "candidate_points": world["candidate_points"], "candidate_oracle": world["candidate_oracle"], "achieved": r["achieved"], "within_tolerance": r["within_tolerance"], "calibrator": CALIBRATOR}
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
            print(f"cell {record['id']}: {record['status']}" + (f", draw {record['draw']}, gain {record['map']['equaliser']['value']:.2f}, peak {record['peak']:.1f}, own world {record['own_world_points']:.0f} points, world seed {record['world_seed']}"
                  if record["status"] == "ok" else "; " + "; ".join(f["error"][:80] for f in record["failed_draws"][:2])) + f" ({record['seconds']} s)", flush=True)
    return out


def _reseed(args):
    record, session = args
    m = record["map"]
    valuemap = value_maps.ValueMap(tuple(value_maps.Bump(**b) for b in m["bumps"]), m["noise"], m["equaliser"])
    duration = record.get("duration", 120.0)
    world = choose_world(session, valuemap, record["settings"], record["id"], factors.anchor_points(duration), record["achieved"]["points"]["oracle"][0], session_duration=duration)
    return {**record, "anchor_points": factors.anchor_points(duration), "world_seed": world["seed"], "own_world_points": world["points"], "own_world_oracle": world["oracle"],
            "candidate_points": world["candidate_points"], "candidate_oracle": world["candidate_oracle"]}


def reseed(code, workers=6):
    """Choose the world of every realised cell again (after WORLD_CANDIDATES or the anchor changed) without realising the cells again."""
    path = REALIZED / f"{code}.json"
    data = json.loads(path.read_text())
    ok = [c for c in data["cells"] if c["status"] == "ok"]
    with mp.Pool(workers) as pool:
        new = {c["id"]: c for c in pool.map(_reseed, [(c, data.get("session", "FOR_S1")) for c in ok])}
    data["cells"] = [new.get(c["id"], c) for c in data["cells"]]
    path.write_text(json.dumps(data, indent=1))
    return path


def show(code):
    data = json.loads((REALIZED / f"{code}.json").read_text())
    for c in data["cells"]:
        k = c["knobs"]
        if c["status"] == "ok":
            a = c["achieved"]["points"]
            print(f"{c['id']:3d} {k['class']:15s} gini {k['gini']:.2f} travel {k['travel_time']:4.1f} diversity {k['diversity']:.2f}: draw {c['draw']}, peak {c['peak']:.1f} (feedback maximum {c['feedback_max']}), "
                  f"learner {a[factors.ANCHOR_AGENT][0]:.0f} (anchor {c.get('anchor_points', factors.anchor_points(120.0)):.0f}) and oracle {a['oracle'][0]:.0f} on the check worlds, {c['own_world_points']:.0f} and {c.get('own_world_oracle', float('nan')):.0f} on world {c['world_seed']}")
        else:
            print(f"{c['id']:3d} {k['class']:15s} gini {k['gini']:.2f}: INACCESSIBLE after {len(c['failed_draws'])} draws")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["realize", "reseed", "show"])
    ap.add_argument("target")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if args.command == "realize":
        print("wrote", realize_table(args.target, args.workers))
    elif args.command == "reseed":
        print("wrote", reseed(args.target, args.workers))
    else:
        show(args.target)


if __name__ == "__main__":
    main()
