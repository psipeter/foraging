"""Load a logged session, replay its harvests from the raw trajectory, and resample it for agents.

A session folder (ForagingData/<sessionId>/, written by DataLogger) holds:
    trajectory.csv  per rendered frame: t, x, z, yaw, pitch, keys (1 = W, 2 = S, 4 = Space held)
    events.csv      t, real, type, tree_id, k, reward, running_total, note   (see docs/SCIENCE.md, "Data")
    harvests.csv    one row per harvest bout (a summary of the events)
    manifest.json   the full SessionConfig, the world file's sha256, build info, frame statistics
The world (bush positions and radii, per-fruit rewards, terrain) is found by the manifest's sha256 in
ForagingData/_worlds/ (archived by the logger) or, failing that, in Assets/StreamingAssets/Worlds/.

`replay_harvests` mirrors HarvestManager.Update frame for frame (range, bearing cone, press edge, fruit timer with
per-bush carry-over, exhaustion), so the logged fruit events can be *derived* from the trajectory alone. `verify`
checks that against the logged events: agreement means the trajectory + world fully determine the outcome, i.e. the
logs are a faithful, replayable record. `steps` resamples the trajectory onto a uniform grid for agents.

    ./venv/bin/python scripts/replay.py <session folder or id> [--steps 0.1]
"""

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from world import PROJECT_ROOT, read_unity_world

DATA_DIR = PROJECT_ROOT / "ForagingData"
WORLD_DIR = PROJECT_ROOT / "Assets" / "StreamingAssets" / "Worlds"

KEY_FORWARD, KEY_BACK, KEY_HARVEST = 1, 2, 4
TIME_TOL = 2e-3     # seconds; logged times are F6, so replayed event times agree far inside this


@dataclass
class Bushes:
    """The bush table a session was played on (positions are x, z)."""
    pos: np.ndarray             # (n, 2)
    canopy_radius: np.ndarray   # (n,)
    fruit_reward: np.ndarray    # (n, fruit_count) reward of the k-th fruit taken from each bush
    value: np.ndarray           # (n,) R_bush


@dataclass
class SessionLog:
    folder: Path
    manifest: dict
    traj: np.ndarray            # (frames, 6): t, x, z, yaw, pitch, keys
    events: list                # dicts: t, real, type, tree_id, k, reward, running_total, note
    bushes: Bushes
    grids: dict = field(default_factory=dict)   # terrain grids (empty for an Interlude loaded without its world)

    @property
    def config(self):
        return self.manifest["config"]


# --------------------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------------------

def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def find_world_file(name, sha):
    """Path of the file with this name and sha256: the logger's archive first, then StreamingAssets."""
    candidates = [DATA_DIR / "_worlds" / f"{sha[:8]}_{name}", WORLD_DIR / name]
    for path in candidates:
        if path.exists() and _sha256(path) == sha:
            return path
    raise FileNotFoundError(f"no file named {name} with sha256 {sha[:12]}... in {DATA_DIR / '_worlds'} or {WORLD_DIR}")


def _read_events(path):
    events = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            events.append({
                "t": float(row["t"]), "real": float(row["real"]), "type": row["type"],
                "tree_id": int(row["tree_id"]) if row["tree_id"] else -1,
                "k": int(row["k"]) if row["k"] else -1,
                "reward": float(row["reward"]) if row["reward"] else math.nan,
                "running_total": float(row["running_total"]) if row["running_total"] else math.nan,
                "note": row["note"],
            })
    return events


def parse_note(note):
    """'x=1;z=2' -> {'x': '1', 'z': '2'}"""
    return dict(part.split("=", 1) for part in note.split(";") if "=" in part)


def load_session_log(folder):
    """Load a session folder (a path, or a session id under ForagingData/) and its world."""
    folder = Path(folder)
    if not folder.exists():
        folder = DATA_DIR / str(folder)
    manifest = json.loads((folder / "manifest.json").read_text())
    traj = np.loadtxt(folder / "trajectory.csv", delimiter=",", skiprows=1, ndmin=2)
    events = _read_events(folder / "events.csv")

    world = manifest["world"]
    header, grids = read_unity_world(find_world_file(world["file"], world["sha256"]))
    table = header
    if world.get("interludeFile"):
        # An Interlude plays a small bush table on its session's terrain.
        table = json.loads(find_world_file(world["interludeFile"], world["interludeSha256"]).read_text())
    n, fruits = len(table["canopyRadius"]), int(table["fruitCount"])   # (an Interlude file's "n" counts trials)
    bushes = Bushes(
        pos=np.asarray(table["treePos"], dtype=float).reshape(n, 2),
        canopy_radius=np.asarray(table["canopyRadius"], dtype=float),
        fruit_reward=np.asarray(table["fruitRewards"], dtype=int).reshape(n, fruits),
        value=np.asarray(table["value"], dtype=float))
    return SessionLog(folder, manifest, traj, events, bushes, grids)


# --------------------------------------------------------------------------------------------------
# Harvest replay (mirrors HarvestManager)
# --------------------------------------------------------------------------------------------------

def _delta_angle(a, b):
    """Signed shortest angle from a to b in degrees (Mathf.DeltaAngle)."""
    return (b - a + 180.0) % 360.0 - 180.0


def _measure(bushes, idx, x, z, yaw):
    """HarvestManager.Measure for the bushes `idx`: (edge distance, bearing beyond the canopy's angular radius)."""
    dx = bushes.pos[idx, 0] - x
    dz = bushes.pos[idx, 1] - z
    dist = np.hypot(dx, dz)
    radius = bushes.canopy_radius[idx]
    delta = _delta_angle(yaw, np.degrees(np.arctan2(dx, dz)))
    with np.errstate(divide="ignore", invalid="ignore"):
        ang = np.where(dist > 1e-4, np.degrees(np.arcsin(np.clip(radius / dist, 0.0, 1.0))), 90.0)
    return dist - radius, np.maximum(0.0, np.abs(delta) - ang)


def replay_harvests(log):
    """Re-derive the harvest events from the trajectory. Returns a list of event dicts in the logged vocabulary
    (harvest_press, harvest_pause/resume, fruit, harvest_release); a release the trajectory alone does not explain
    (the Interlude cancelling a bout at a trial's end, or the session ending) is taken from the log and marked
    `forced`."""
    cfg = log.config
    gap_base, gap_per = cfg["harvestRangeGapBase"], cfg["harvestRangeGapPerRadius"]
    max_angle, per_fruit = cfg["harvestMaxAngle"], cfg["fruitHarvestDuration"]
    b = log.bushes
    n, n_fruits = len(b.pos), b.fruit_reward.shape[1]
    gaps = gap_base + gap_per * b.canopy_radius

    ev = log.events
    forced_times = [e for e in ev if e["type"] == "harvest_release"]
    trials = [e for e in ev if e["type"] == "trial_start"]
    active = np.ones(n, dtype=bool)
    if trials:
        active[:] = False
    next_trial = 0

    partial = np.zeros(n)
    taken = np.zeros(n, dtype=int)
    exhausted = np.zeros(n, dtype=bool)
    out = []
    target, timer, in_cone, total = -1, 0.0, True, 0.0
    t_prev = 0.0
    held_prev = False

    def release(t, forced):
        nonlocal target, timer
        if not exhausted[target]:
            partial[target] = timer
        out.append({"type": "harvest_release", "t": t, "tree_id": target, "forced": forced})
        target, timer = -1, 0.0

    for i in range(len(log.traj)):
        t, x, z, yaw, _, keys = log.traj[i]
        dt = t - t_prev
        t_prev = t
        held = bool(int(keys) & KEY_HARVEST)
        pressed = held and not held_prev
        held_prev = held

        while next_trial < len(trials) and trials[next_trial]["t"] <= t + 1e-4:
            note = parse_note(trials[next_trial]["note"])
            active[:] = False
            active[[int(note["left"]), int(note["right"])]] = True
            next_trial += 1

        if target < 0:
            idx = np.flatnonzero(active & ~exhausted)
            focus = -1
            if len(idx):
                edge, bearing = _measure(b, idx, x, z, yaw)
                ok = (edge <= gaps[idx]) & (bearing <= max_angle)
                if ok.any():
                    cand = np.flatnonzero(ok)
                    best = cand[np.lexsort((edge[cand], bearing[cand]))[0]]
                    focus = int(idx[best])
            if pressed and focus >= 0:
                target, timer, in_cone = focus, partial[focus], True
                out.append({"type": "harvest_press", "t": t, "tree_id": target})
        elif not held:
            release(t, False)

        if target >= 0:
            edge, bearing = _measure(b, np.array([target]), x, z, yaw)
            now_in = bool(edge[0] <= gaps[target] and bearing[0] <= max_angle)
            if now_in != in_cone:
                out.append({"type": "harvest_resume" if now_in else "harvest_pause", "t": t, "tree_id": target})
            in_cone = now_in
            if in_cone:
                timer += dt
                while timer >= per_fruit and target >= 0:
                    timer -= per_fruit
                    k = int(taken[target])
                    reward = float(b.fruit_reward[target, k])
                    taken[target] += 1
                    total += reward
                    out.append({"type": "fruit", "t": t, "tree_id": target, "k": k, "reward": reward, "running_total": total})
                    if taken[target] >= n_fruits:
                        exhausted[target] = True
                        release(t, False)

        # A bout the trajectory does not end by itself, but the log says ended on this frame.
        if target >= 0 and any(abs(e["t"] - t) < 1e-5 and e["tree_id"] == target for e in forced_times):
            release(t, True)

    return out


def verify(log):
    """Compare the replayed harvest events with the logged ones. Returns a list of mismatch descriptions (empty = the
    log is reproduced exactly) and the replayed events."""
    replayed = replay_harvests(log)
    problems = []
    t_end = float(log.traj[-1, 0]) if len(log.traj) else 0.0
    frame_dt = float(np.median(np.diff(log.traj[:, 0]))) if len(log.traj) > 2 else 0.0
    for kind in ("harvest_press", "harvest_pause", "harvest_resume", "fruit", "harvest_release"):
        a = [e for e in log.events if e["type"] == kind]
        b = [e for e in replayed if e["type"] == kind]
        # Events on the session's last frame depend on whether the sun clock ended before or after the harvest update.
        a_core = [e for e in a if e["t"] < t_end - 1.5 * frame_dt]
        b_core = [e for e in b if e["t"] < t_end - 1.5 * frame_dt]
        if len(a_core) != len(b_core):
            problems.append(f"{kind}: logged {len(a_core)} vs replayed {len(b_core)}")
        for j, (ea, eb) in enumerate(zip(a_core, b_core)):
            bad = ea["tree_id"] != eb["tree_id"] or abs(ea["t"] - eb["t"]) > TIME_TOL
            if kind == "fruit":
                bad = bad or ea["k"] != eb["k"] or ea["reward"] != eb["reward"]
            if bad:
                problems.append(f"{kind} #{j}: logged {_brief(ea)} vs replayed {_brief(eb)}")
                break
    fruit_sum = sum(e["reward"] for e in log.events if e["type"] == "fruit")
    final = log.manifest.get("finalScore")
    if final is not None and abs(fruit_sum - final) > 1e-6:
        problems.append(f"finalScore {final} != sum of logged fruit rewards {fruit_sum}")
    return problems, replayed


def _brief(e):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in e.items() if k in ("t", "tree_id", "k", "reward")}


# --------------------------------------------------------------------------------------------------
# Agent-facing view
# --------------------------------------------------------------------------------------------------

def steps(log, dt=0.1):
    """Resample onto a uniform grid of `dt` seconds (the participant's state at the start of each step).

    Returns arrays over the grid: t, x, z, yaw (unwrapped degrees), pitch, forward/back/harvest key states (0/1),
    `reward` (sum of the fruit rewards that arrive in the step, from the logged events), `harvesting` (1 inside a
    bout) and `tree` (the bush being harvested, else -1). Pose is linearly interpolated, except across a teleport
    (an Interlude trial change), where the earlier pose is held until the jump; discrete states take the latest
    frame at or before the step start.
    """
    tr = log.traj
    t = np.arange(0.0, tr[-1, 0], dt)
    frame = np.clip(np.searchsorted(tr[:, 0], t, side="right") - 1, 0, len(tr) - 1)
    pose = {name: np.interp(t, tr[:, 0], tr[:, col]) for name, col in (("x", 1), ("z", 2), ("yaw", 3), ("pitch", 4))}
    for e in log.events:
        if e["type"] == "teleport":
            hold = (t >= tr[max(np.searchsorted(tr[:, 0], e["t"]) - 1, 0), 0]) & (t < e["t"] + 1e-9)
            for name in ("x", "z", "yaw", "pitch"):
                pose[name] = np.where(hold, tr[frame, {"x": 1, "z": 2, "yaw": 3, "pitch": 4}[name]], pose[name])
    keys = tr[frame, 5].astype(int)

    reward = np.zeros(len(t))
    harvesting = np.zeros(len(t), dtype=int)
    tree = -np.ones(len(t), dtype=int)
    bout_start = None
    for e in log.events:
        if e["type"] == "fruit":
            reward[min(int(e["t"] // dt), len(t) - 1)] += e["reward"]
        elif e["type"] == "harvest_press":
            bout_start = e
        elif e["type"] == "harvest_release" and bout_start is not None:
            inside = (t >= bout_start["t"] - dt) & (t < e["t"])
            harvesting[inside] = 1
            tree[inside] = bout_start["tree_id"]
            bout_start = None
    if bout_start is not None:      # a bout still open when the trajectory ends
        inside = t >= bout_start["t"] - dt
        harvesting[inside] = 1
        tree[inside] = bout_start["tree_id"]
    return {"t": t, **pose, "forward": (keys & KEY_FORWARD > 0).astype(int), "back": (keys & KEY_BACK > 0).astype(int),
            "harvest": (keys & KEY_HARVEST > 0).astype(int), "reward": reward, "harvesting": harvesting, "tree": tree}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("session", help="session folder or session id under ForagingData/")
    parser.add_argument("--steps", type=float, default=None, help="also print the uniform-grid resample with this dt")
    args = parser.parse_args()

    log = load_session_log(args.session)
    m = log.manifest
    print(f"{m['sessionName']} ({m['sessionId']}): {len(log.traj)} frames, {log.traj[-1, 0]:.1f} s, "
          f"{sum(e['type'] == 'fruit' for e in log.events)} fruits, finalScore {m.get('finalScore')}")
    problems, replayed = verify(log)
    if problems:
        print("MISMATCH:")
        for p in problems:
            print("  " + p)
    else:
        forced = sum(1 for e in replayed if e.get("forced"))
        print(f"replay reproduces every logged harvest event ({forced} bouts ended by the game, not the keys)")
    if args.steps:
        s = steps(log, args.steps)
        print(f"{len(s['t'])} steps of {args.steps} s; total reward {s['reward'].sum():.0f}")
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
