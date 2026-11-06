"""Load a logged session, replay its harvests from the raw trajectory, and resample it for agents.

A session folder is the local layout of rundata.py (<run>/<session>/: session.json, events.csv, trajectory.csv; keys are
1 = W, 2 = S, 4 = Space held). The world (bush positions and radii, per-fruit rewards, terrain) is found by the session row's
sha256 in the `_worlds` folder next to the run's folder (where `server_admin.py pull` puts the files it takes from git at the run's
build commit), ForagingData/_worlds/ (archived by the Editor and standalone loggers) or, failing that, in Assets/StreamingAssets/Experiments/<code>/.

A session that was interrupted and continued (docs/ONLINE_DATA_PLAN.md, section 4) has a `session_resume` event: the game restarted
from the server's state, so the harvest state (open bout, per-bush progress on the fruit being picked) starts empty there, the
fruit counts come from the logged fruit events, and the events logged in the gap (after the last uploaded frame, up to the resume)
have no frames to be derived from: `verify` leaves them out.

`replay_harvests` mirrors HarvestManager.Update frame for frame (range, bearing cone, press edge, fruit timer with
per-bush carry-over, exhaustion), so the logged fruit events can be *derived* from the trajectory alone. `verify`
checks that against the logged events: agreement means the trajectory + world fully determine the outcome, i.e. the
logs are a faithful, replayable record. `steps` resamples the trajectory onto a uniform grid for agents.

    ./venv/bin/python scripts/replay.py <session folder or id> [--steps 0.1]
"""

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

import rundata
from world import PROJECT_ROOT, read_unity_world

DATA_DIR = PROJECT_ROOT / "ForagingData"
WORLD_DIR = PROJECT_ROOT / "Assets" / "StreamingAssets" / "Experiments"      # <code>/<file>: searched one level down

KEY_FORWARD, KEY_BACK, KEY_HARVEST = 1, 2, 4
TIME_TOL = 2e-3     # seconds; logged times are F6, so replayed event times agree far inside this
TIE = 1e-5          # seconds; a replayed fruit timer this close to the fruit time is a tie (see replay_harvests)


@dataclass
class Bushes:
    """The bush table a session was played on (positions are x, z)."""
    pos: np.ndarray             # (n, 2)
    canopy_radius: np.ndarray   # (n,)
    fruit_reward: np.ndarray    # (n, fruit_count) reward of the k-th fruit taken from each bush
    shape: np.ndarray = None    # (n,) shape attribute (sets the canopy height; see visibility.py)


@dataclass
class SessionLog:
    folder: Path
    manifest: dict              # the `sessions` row (session.json)
    traj: np.ndarray            # (frames, 6): t, x, z, yaw, pitch, keys
    events: list                # dicts: t, real, type, tree_id, k, reward, running_total, payload
    bushes: Bushes
    grids: dict = field(default_factory=dict)   # terrain grids: moisture, elevation, rock, snow, ramp; (res, res) [x, z]
    half_extent: float = 0.0                    # the grids span [-half_extent, half_extent] in x and z
    truncated: list = field(default_factory=list)   # files whose last line was cut short (a crash) and dropped on load

    @property
    def config(self):
        return self.manifest["config"]

    @property
    def name(self):
        return self.manifest.get("name")

    @property
    def session_id(self):
        return f"{str(self.manifest.get('run_id'))[:8]}/{self.manifest.get('session_index')}"

    @property
    def final_score(self):
        return self.manifest.get("final_score")


# --------------------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------------------

def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def find_world_file(name, sha, archive=None):
    """Path of the file with this name and sha256: the archive `_worlds` folder given (a pulled run's), the logger's, then StreamingAssets."""
    candidates = [*([Path(archive) / f"{sha[:8]}_{name}"] if archive else []), DATA_DIR / "_worlds" / f"{sha[:8]}_{name}", *sorted(WORLD_DIR.glob(f"*/{name}"))]
    for path in candidates:
        if path.exists() and _sha256(path) == sha:
            return path
    raise FileNotFoundError(f"no file named {name} with sha256 {sha[:12]}... in {DATA_DIR / '_worlds'} or {WORLD_DIR}")


def load_session_log(folder):
    """Load a session folder (a path, or a session id under ForagingData/) and its world."""
    folder = Path(folder)
    if not folder.exists() and not folder.is_absolute() and (PROJECT_ROOT / folder).exists():
        folder = PROJECT_ROOT / folder        # a path relative to the project root, from any working directory
    elif not folder.exists():
        folder = DATA_DIR / str(folder)
    data = rundata.read_session(folder)
    row = data["session"]
    archive = folder.resolve().parent.parent / "_worlds"          # <out>/<run>/<session>
    header, grids = read_unity_world(find_world_file(row["world_file"], row["world_sha256"], archive))
    table = header
    if row.get("interlude_file"):
        # An Interlude plays a small bush table on its session's terrain.
        table = json.loads(find_world_file(row["interlude_file"], row["interlude_sha256"], archive).read_text())
    n, fruits = len(table["canopyRadius"]), int(table["fruitCount"])   # (an Interlude file's "n" counts trials)
    bushes = Bushes(
        pos=np.asarray(table["treePos"], dtype=float).reshape(n, 2),
        canopy_radius=np.asarray(table["canopyRadius"], dtype=float),
        fruit_reward=np.asarray(table["fruitRewards"], dtype=int).reshape(n, fruits), shape=np.asarray(table["shape"], dtype=float))
    return SessionLog(folder, row, data["traj"], data["events"], bushes, grids, float(header["halfExtent"]), data["truncated"])


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


def _last_frames_start(traj):
    """Time from which the session's last two frames start. The sun's clock reaches the duration on the second-to-last frame, and
    whether it or the harvest update ran first decides there whether the bout ended on that frame or the next, so a release is
    honoured in these frames and events are not compared. (A median-frame-time window missed the release whenever the last
    frame was long.)"""
    return float(traj[-2, 0]) - 1e-6 if len(traj) > 1 else -np.inf


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
    # Releases the keys cannot explain are honoured only where the game itself ends a bout: the Interlude's trial end
    # and the session's last frames. Any other logged release must come from the replayed key rules, or verify flags it.
    tail = _last_frames_start(log.traj)
    cut_times = [e["t"] for e in ev if e["type"] == "trial_end"]
    forced_times = [e for e in ev if e["type"] == "harvest_release"
                    and (e["t"] >= tail or any(abs(e["t"] - c) < TIE for c in cut_times))]   # a trial_end is logged on the frame it ends the bout
    trials = [e for e in ev if e["type"] == "trial_start"]
    # The fruit a logged tie resolves to, by (bush, k): see the fruit timer below.
    fruit_t = {(e["tree_id"], e["k"]): e["t"] for e in ev if e["type"] == "fruit"}
    # An Interlude commitment: from the frame after the press that started the chosen bush, the other bush can no longer be
    # harvested (hidden, spent or locked; the policy only changes how it looks).
    locks = [e for e in ev if e["type"] == "choice_lock"]
    next_lock = 0
    # HarvestManager discards presses between an Interlude trial's end and the following trial_go (rows after the
    # trial_end up to and including the trial_go frame); after the last trial's end there is no trial_go.
    go_times = [e["t"] for e in ev if e["type"] == "trial_go"]
    blocks = [(e["t"], min((g for g in go_times if g > e["t"] - 1e-9), default=np.inf)) for e in ev if e["type"] == "trial_end"]
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
    resumes = sorted((e for e in ev if e["type"] == "session_resume"), key=lambda e: e["t"])
    next_resume = 0

    def release(t, forced):
        nonlocal target, timer
        if not exhausted[target]:
            partial[target] = timer
        out.append({"type": "harvest_release", "t": t, "tree_id": target, "forced": forced})
        target, timer = -1, 0.0

    for i in range(len(log.traj)):
        t, x, z, yaw, _, keys = log.traj[i]
        # The first frame after a resume: the game restarted from the server's state. Nothing is held or in progress; the fruits
        # taken so far are the logged ones (the replay cannot derive those of the gap); the clock continues from the resume.
        while next_resume < len(resumes) and resumes[next_resume]["t"] < t - 1e-9:
            at = resumes[next_resume]["t"]
            next_resume += 1
            target, timer, in_cone, held_prev, t_prev = -1, 0.0, True, False, at
            partial[:] = 0.0
            taken[:] = 0
            total = 0.0
            for e in ev:
                # (An Interlude restarts the unfinished trial in a fresh scene with every bush full: nothing carries over.)
                if e["type"] == "fruit" and e["t"] <= at + 1e-9 and not trials:
                    taken[e["tree_id"]] += 1
                    total = e["running_total"] if not math.isnan(e["running_total"]) else total + e["reward"]
            exhausted = taken >= n_fruits
        dt = t - t_prev
        t_prev = t
        held = bool(int(keys) & KEY_HARVEST)
        pressed = held and not held_prev
        held_prev = held
        if any(a + 1e-9 < t <= b + 1e-9 for a, b in blocks):
            pressed = False

        while next_trial < len(trials) and trials[next_trial]["t"] <= t + 1e-4:     # (a trial_start takes effect on the frame at or just after its logged time)
            pair = trials[next_trial]["payload"]
            active[:] = False
            active[[int(pair["left"]), int(pair["right"])]] = True
            next_trial += 1

        while next_lock < len(locks) and locks[next_lock]["t"] < t - 1e-9:
            active[int(locks[next_lock]["payload"]["locked"])] = False
            next_lock += 1

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
                # Browsers hand Unity whole-millisecond frame times, so the frames' sum often equals the fruit time exactly, and
                # which side the game's float32 sum fell on is not in the log: within TIE the logged fruit decides (about 98 of
                # 1000 fruits are one frame off otherwise). Without a logged fruit (an agent) the plain comparison holds.
                while target >= 0 and (timer >= per_fruit if abs(timer - per_fruit) >= TIE or (target, int(taken[target])) not in fruit_t
                                       else abs(fruit_t[target, int(taken[target])] - t) < 1e-4):
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
        if target >= 0 and any(abs(e["t"] - t) < TIE and e["tree_id"] == target for e in forced_times):
            release(t, True)

    return out


def verify(log):
    """Compare the replayed harvest events with the logged ones. Returns a list of mismatch descriptions (empty = the
    log is reproduced exactly) and the replayed events."""
    replayed = replay_harvests(log)
    problems = [f"{name} ended mid-line (the session did not finish writing): its last line was dropped"
                for name in log.truncated]
    tail = _last_frames_start(log.traj)
    # Events logged in a resume's gap (after the last uploaded frame, up to the resume) have no frames to derive them from.
    gaps = []
    for r in (e for e in log.events if e["type"] == "session_resume"):
        before = log.traj[log.traj[:, 0] <= r["t"] + 1e-9, 0]
        gaps.append((float(before[-1]) if len(before) else 0.0, r["t"]))
    for kind in ("harvest_press", "harvest_pause", "harvest_resume", "fruit", "harvest_release"):
        a = [e for e in log.events if e["type"] == kind and not any(lo + 1e-9 < e["t"] <= hi + 1e-9 for lo, hi in gaps)]
        b = [e for e in replayed if e["type"] == kind]
        a_core = [e for e in a if e["t"] < tail]
        b_core = [e for e in b if e["t"] < tail]
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
    final = log.final_score
    if final is not None and abs(fruit_sum - final) > 1e-6:
        problems.append(f"final_score {final} != sum of logged fruit rewards {fruit_sum}")
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
    names = ("x", "z", "yaw", "pitch")             # trajectory columns 1 to 4
    pose = {name: np.interp(t, tr[:, 0], tr[:, col]) for col, name in enumerate(names, 1)}
    for e in log.events:
        if e["type"] == "teleport":
            # The jump happens after the logger wrote the row at e["t"], so that row still has the old pose: hold it
            # until the next row, which is the first with the new one.
            nxt = np.searchsorted(tr[:, 0], e["t"], side="right")
            hold = (t >= e["t"] - 1e-9) & (t < (tr[nxt, 0] if nxt < len(tr) else np.inf))
            for col, name in enumerate(names, 1):
                pose[name] = np.where(hold, tr[frame, col], pose[name])
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
    parser.add_argument("session", help="session folder, or <run id>/<session> under ForagingData/")
    parser.add_argument("--steps", type=float, default=None, help="also print the uniform-grid resample with this dt")
    args = parser.parse_args()

    log = load_session_log(args.session)
    print(f"{log.name} ({log.session_id}): {len(log.traj)} frames, {log.traj[-1, 0]:.1f} s, "
          f"{sum(e['type'] == 'fruit' for e in log.events)} fruits, final_score {log.final_score}")
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
