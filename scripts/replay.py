"""Load a logged session, replay its harvests from the raw trajectory, and resample it for agents.

A session folder is the local layout of rundata.py (<run>/<session>/: session.json, events.csv, trajectory.csv; keys are
1 = W, 2 = S, 4 = Space held). The world (bush positions and radii, per-fruit rewards, terrain) is found by the session row's
sha256 in the `_worlds` folder next to the run's folder (where `server_admin.py pull` puts the files it takes from git at the run's
build commit), ForagingData/_worlds/ (archived by the Editor and standalone loggers) or, failing that, in Assets/StreamingAssets/Experiments/<code>/.

A session that was interrupted and continued (docs/ONLINE_DATA_PLAN.md, section 4) has a `session_resume` event: the game restarted
from the server's state, so the harvest state (open bout, per-bush progress on the fruit being picked) starts empty there, the
fruit counts come from the logged fruit events, and the events logged in the gap (after the last uploaded frame, up to the resume)
have no frames to be derived from: `verify` leaves them out.

A foraging session with ranking breaks (RankingBreak: `rank_break_start` / `rank_break_end` events) plays a ranking set in place: the real bushes are
still there but grey and not harvestable, the set's bushes (not in the world file; their table is the `rank_set` event) stand on an arc, the harvest is aimed (no range, the ranking's
tolerance) and quick (`rankingFruitSeconds` a fruit), and presses are discarded from the break's start and each set's end up to the next
`rank_go` (or the break's end). `with_ranking_bushes` appends those bushes to the table and `break_windows` gives the windows.

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
from perception import canopy_height_of, sample_grid
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
    n, fruits = len(table["canopyRadius"]), int(table["fruitCount"])
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


def _forward(yaw, pitch):
    """The view's forward vector (HarvestManager.UpdateAimRay): yaw about +Y from +Z toward +X, pitch positive = down."""
    y, p = math.radians(yaw), math.radians(pitch)
    return np.array([math.sin(y) * math.cos(p), -math.sin(p), math.cos(y) * math.cos(p)])


def _aimed(centres, rx, ry, eye, forward, radius_deg):
    """HarvestManager.Aimed for several bushes: does the view ray from `eye` along `forward` meet each canopy's ellipsoid (horizontal radius rx, vertical radius ry, centred on the
    ground), grown by distance x tan(radius)? A ray starting inside it counts."""
    grow = np.linalg.norm(centres - eye, axis=-1) * math.tan(math.radians(radius_deg))
    radii = np.stack([rx + grow, ry + grow, rx + grow], axis=-1)
    p, q = (eye - centres) / radii, forward / radii
    a, b, c = (q * q).sum(-1), (p * q).sum(-1), (p * p).sum(-1) - 1.0
    disc = b * b - a * c
    return (disc >= 0.0) & ((-b + np.sqrt(np.maximum(disc, 0.0))) / a > 0.0)


def _last_frames_start(traj):
    """Time from which the session's last two frames start. The sun's clock reaches the duration on the second-to-last frame, and
    whether it or the harvest update ran first decides there whether the bout ended on that frame or the next, so a release is
    honoured in these frames and events are not compared. (A median-frame-time window missed the release whenever the last
    frame was long.)"""
    return float(traj[-2, 0]) - 1e-6 if len(traj) > 1 else -np.inf


def _payload(e):
    return e.get("payload") or {}


def break_windows(events):
    """[(start, end)] session seconds of each ranking break (end is inf for one that never logged its end)."""
    starts = sorted(e["t"] for e in events if e["type"] == "rank_break_start")
    ends = sorted(e["t"] for e in events if e["type"] == "rank_break_end")
    return [(s, ends[i] if i < len(ends) else np.inf) for i, s in enumerate(starts)]


def with_ranking_bushes(log):
    """(bushes, sets, ids): the world's bush table with the bushes of every ranking set appended (the `rank_set` events carry them: tree id, x, z, canopy radius,
    shape; they pay nothing), `sets` one dict per `rank_set` (t, end = the time of its `rank_set_end`, slots = their indices in the table) and `ids`, the logged tree id
    of every row of the table (a pool wrap can give two sets the same ids, so a set's bushes are rows of their own)."""
    b = log.bushes
    n0, n_fruits = len(b.pos), b.fruit_reward.shape[1]
    pos, radius, shape, ids, sets = [b.pos], [b.canopy_radius], [b.shape if b.shape is not None else np.zeros(n0)], [np.arange(n0)], []
    ends = sorted(e["t"] for e in log.events if e["type"] == "rank_set_end")
    total = n0
    for e in (e for e in log.events if e["type"] == "rank_set"):
        rows = _payload(e)["bushes"]
        pos.append(np.array([[r["x"], r["z"]] for r in rows], dtype=float).reshape(-1, 2))
        radius.append(np.array([r["radius"] for r in rows], dtype=float))
        shape.append(np.array([r["shape"] for r in rows], dtype=float))
        ids.append(np.array([int(r["id"]) for r in rows]))
        sets.append({"t": e["t"], "end": next((x for x in ends if x > e["t"] - 1e-9), np.inf), "slots": np.arange(total, total + len(rows))})
        total += len(rows)
    if not sets:
        return b, sets, ids[0]
    extended = Bushes(pos=np.concatenate(pos), canopy_radius=np.concatenate(radius), fruit_reward=np.concatenate([b.fruit_reward, np.zeros((total - n0, n_fruits), dtype=int)]),
                      shape=np.concatenate(shape))
    return extended, sets, np.concatenate(ids)


def replay_harvests(log):
    """Re-derive the harvest events from the trajectory. Returns a list of event dicts in the logged vocabulary
    (harvest_press, harvest_pause/resume, fruit, harvest_release); a release the trajectory alone does not explain
    (a ranking set's end cancelling a bout, or the session ending) is taken from the log and marked
    `forced`."""
    cfg = log.config
    gap_base, gap_per = cfg["harvestRangeGapBase"], cfg["harvestRangeGapPerRadius"]
    max_angle, per_fruit = cfg["harvestMaxAngle"], cfg["fruitHarvestDuration"]
    n0 = len(log.bushes.pos)
    b, rank_sets, ids = with_ranking_bushes(log)
    n, n_fruits = len(b.pos), b.fruit_reward.shape[1]
    gaps = gap_base + gap_per * b.canopy_radius
    # The crosshair rule (SessionConfig.crosshairRadius > 0; a log without it, or with 0, is the old cone): the view ray must touch the canopy's ellipsoid grown by the
    # circle, instead of the bearing being within a cone.
    crosshair = float(cfg.get("crosshairRadius") or 0.0)
    if crosshair > 0.0:
        elevation, half, eye_height = log.grids["elevation"], log.half_extent, float(cfg["eyeHeight"])
        ground = sample_grid(elevation, half, b.pos[:, 0], b.pos[:, 1])
        half_height = 0.5 * canopy_height_of(b.shape, (cfg["shapeRange"]["x"], cfg["shapeRange"]["y"]), (cfg["canopyHeightRange"]["x"], cfg["canopyHeightRange"]["y"]))
        centres = np.stack([b.pos[:, 0], ground, b.pos[:, 1]], axis=-1)
        release_radius = crosshair * max(float(cfg.get("crosshairReleaseScale") or 1.0), 1.0)
    # A ranking break (HarvestManager.SetAimMode): aimed (no harvest range; with the old cone, the ranking's tolerance) and quick (rankingFruitSeconds a fruit) from its start to its end.
    windows = break_windows(log.events)
    break_per_fruit, break_angle = cfg.get("rankingFruitSeconds", per_fruit), cfg.get("rankingAimTolerance", max_angle)
    next_set, was_in_break = 0, False

    ev = log.events
    # Releases the keys cannot explain are honoured only where the game itself ends a bout: a ranking set's end
    # and the session's last frames. Any other logged release must come from the replayed key rules, or verify flags it.
    tail = _last_frames_start(log.traj)
    cut_times = [e["t"] for e in ev if e["type"] == "rank_set_end"]
    forced_times = [e for e in ev if e["type"] == "harvest_release"
                    and (e["t"] >= tail or any(abs(e["t"] - c) < TIE for c in cut_times))]   # a rank_set_end is logged on the frame it ends the bout
    # The fruit a logged tie resolves to, by (bush, k): see the fruit timer below.
    fruit_t = {(e["tree_id"], e["k"]): e["t"] for e in ev if e["type"] == "fruit"}
    # A ranking break discards presses from its start and from each set's end up to the next rank_go (a set going live) or the break's end.
    unblocks = sorted(e["t"] for e in ev if e["type"] in ("rank_go", "rank_break_end"))
    blocks = [(e["t"], min((g for g in unblocks if g > e["t"] + 1e-9), default=np.inf)) for e in ev
              if e["type"] in ("rank_break_start", "rank_set_end")]
    active = np.ones(n, dtype=bool)
    active[n0:] = False

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
        out.append({"type": "harvest_release", "t": t, "tree_id": int(ids[target]), "forced": forced})
        target, timer = -1, 0.0

    for i in range(len(log.traj)):
        t, x, z, yaw, pitch, keys = log.traj[i]
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
                if e["type"] == "fruit" and e["t"] <= at + 1e-9:
                    taken[e["tree_id"]] += 1
                    total = e["running_total"] if not math.isnan(e["running_total"]) else total + e["reward"]
            exhausted = taken >= n_fruits
        dt = t - t_prev
        t_prev = t
        in_break = any(lo + 1e-9 < t <= hi + 1e-9 for lo, hi in windows)
        if was_in_break and not in_break:
            active[:] = False                   # the break is over: the real bushes are back
            active[:n0] = True
        was_in_break = in_break
        aim_now, angle_now, fruit_now = in_break, (break_angle if in_break else max_angle), (break_per_fruit if in_break else per_fruit)
        while next_set < len(rank_sets) and rank_sets[next_set]["t"] <= t + 1e-4:        # a set's bushes stand from the frame at or just after its rank_set
            active[:] = False
            active[rank_sets[next_set]["slots"]] = True
            next_set += 1
        held = bool(int(keys) & KEY_HARVEST)
        pressed = held and not held_prev
        held_prev = held
        if any(a + 1e-9 < t <= b + 1e-9 for a, b in blocks):
            pressed = False

        if target < 0:
            idx = np.flatnonzero(active & ~exhausted)
            focus = -1
            if len(idx):
                edge, bearing = _measure(b, idx, x, z, yaw)
                if crosshair > 0.0:
                    eye = np.array([x, float(sample_grid(elevation, half, x, z)) + eye_height, z])
                    cand = np.flatnonzero((edge <= gaps[idx]) | aim_now)
                    if len(cand):
                        cand = cand[_aimed(centres[idx[cand]], b.canopy_radius[idx[cand]], half_height[idx[cand]], eye, _forward(yaw, pitch), crosshair)]
                    if len(cand):
                        focus = int(idx[cand[np.argmin(edge[cand])]])
                else:
                    ok = ((edge <= gaps[idx]) | aim_now) & (bearing <= angle_now)
                    if ok.any():
                        cand = np.flatnonzero(ok)
                        best = cand[np.lexsort((edge[cand], bearing[cand]))[0]]
                        focus = int(idx[best])
            if pressed and focus >= 0:
                target, timer, in_cone = focus, partial[focus], True
                out.append({"type": "harvest_press", "t": t, "tree_id": int(ids[target])})
        elif not held and not aim_now:     # aiming: a bout runs to the bush's last fruit (HarvestManager)
            release(t, False)

        if target >= 0:
            edge, bearing = _measure(b, np.array([target]), x, z, yaw)
            if crosshair > 0.0:
                eye = np.array([x, float(sample_grid(elevation, half, x, z)) + eye_height, z])
                inside = edge[0] <= gaps[target] and bool(_aimed(centres[[target]], b.canopy_radius[[target]], half_height[[target]], eye, _forward(yaw, pitch), release_radius)[0])
            else:
                inside = edge[0] <= gaps[target] and bearing[0] <= angle_now
            now_in = bool(aim_now or inside)
            if now_in != in_cone:
                out.append({"type": "harvest_resume" if now_in else "harvest_pause", "t": t, "tree_id": int(ids[target])})
            in_cone = now_in
            if in_cone:
                timer += dt
                # Browsers hand Unity whole-millisecond frame times, so the frames' sum often equals the fruit time exactly, and
                # which side the game's float32 sum fell on is not in the log: within TIE the logged fruit decides (about 98 of
                # 1000 fruits are one frame off otherwise). Without a logged fruit (an agent) the plain comparison holds.
                while target >= 0 and (timer >= fruit_now if abs(timer - fruit_now) >= TIE or (int(ids[target]), int(taken[target])) not in fruit_t
                                       else abs(fruit_t[int(ids[target]), int(taken[target])] - t) < 1e-4):
                    timer -= fruit_now
                    k = int(taken[target])
                    reward = float(b.fruit_reward[target, k])
                    taken[target] += 1
                    total += reward
                    out.append({"type": "fruit", "t": t, "tree_id": int(ids[target]), "k": k, "reward": reward, "running_total": total})
                    if taken[target] >= n_fruits:
                        exhausted[target] = True
                        release(t, False)

        # A bout the trajectory does not end by itself, but the log says ended on this frame.
        if target >= 0 and any(abs(e["t"] - t) < TIE and e["tree_id"] == int(ids[target]) for e in forced_times):
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
    bout), `tree` (the bush being harvested, else -1) and `ranking` (1 inside a ranking break: the player stands still ranking
    a set, the real bushes are grey and not harvestable, and the tree ids of the bouts are those of the set's bushes). Pose is linearly interpolated, except across a teleport
    (a ranking break's teleport or a resume), where the earlier pose is held until the jump; discrete states take the latest
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
    ranking = np.zeros(len(t), dtype=int)
    for lo, hi in break_windows(log.events):
        ranking[(t > lo) & (t <= hi)] = 1
    return {"t": t, **pose, "forward": (keys & KEY_FORWARD > 0).astype(int), "back": (keys & KEY_BACK > 0).astype(int),
            "harvest": (keys & KEY_HARVEST > 0).astype(int), "reward": reward, "harvesting": harvesting, "tree": tree, "ranking": ranking}


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
