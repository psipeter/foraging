"""Validate logged runs: is the data self-consistent, is the scoring right, and did the game follow the ranking-break rules of the design?

    ./venv/bin/python scripts/validate_run.py <session folder | run folder | run id> [--json]
    ./venv/bin/python scripts/validate_run.py --all [--json]       # every run under ForagingData/ (not _worlds, _db_backup*, other non-run folders)

Read-only. One table per session folder (ForagingData/<run>/<NN>/) of checks, each PASS / WARN / FAIL / SKIP with the numbers that disagree, a summary
line, and exit code 1 if any check FAILs. FAIL means the data or the scoring is wrong; WARN is a case the logs cannot decide (an old format, a world file
that cannot be found, a reduced run). Three groups (docs/VALIDATION_PLAN.md, Layer 1):

  scoring    foraging_points = the last running_total = the sum of the fruit rewards, each fruit pays the world's pre-drawn reward; each ranking set's
             correct_pairs / total_pairs recomputed with `ranking.pair_scores`, its points, the `rank_set_end` event, ranking_points and `session_end`.
  integrity  event seq and clock, session_start / session_end, trajectory frame count, ranking break and set events, the world file's hash.
  breaks     the design's rules: a patch switch before each break, the cooldown, the minimum of harvested bushes, the last seconds, rankingEvery, the player
             still and no foraging fruit during a break, the foraging clock lasting sessionDuration, the pool played in order.

Each check is a small function from a `Ctx` (one session's loaded data) to a list of `Result`, so tests call them directly.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

import ranking
import replay
import rundata
from world import read_unity_world

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
TOL = 1e-6              # points are whole numbers; a sum differing by more than this is wrong
CLOCK_TOL = 1.5         # seconds a session's foraging time may differ from sessionDuration
COOLDOWN_TOL = 0.05     # seconds
STILL_TOL = 1e-3        # world units the player may move in a break
SETTLE_SECONDS = 0.25   # seconds after a break's start in which the last momentum may still move the player
SETTLE_MOVE = 0.5       # world units it may move in them
TIME_EPS = 1e-4         # seconds: an event and the frame it was logged on may differ in the last digit


@dataclass
class Result:
    name: str
    status: str
    detail: str = ""


@dataclass
class Ctx:
    """One session's data. `fruit_reward` ((bushes, fruits) array) and `tile_centres` ((tiles, 2)) are None when the world file could not be found."""
    row: dict
    traj: np.ndarray                    # (frames, 6): t, x, z, yaw, pitch, keys
    events: list
    sets: list = None                   # the ranking_sets rows, None when there is no ranking_sets.csv
    fruit_reward: np.ndarray = None
    tile_centres: np.ndarray = None
    world_note: str = ""                # why the world is missing (a WARN detail), or where it was found
    world_found: bool = False
    pool_tolerance: float = ranking.TIE_TOLERANCE
    pool_size: int = None
    truncated: list = field(default_factory=list)

    @property
    def config(self):
        return self.row.get("config") or {}

    @property
    def foraging_points(self):
        return self.row.get("foraging_points", self.row.get("final_score"))        # the old spelling of a log from before 2026-11-14

    @property
    def ranking_every(self):
        return self.config.get("rankingEvery") or 0

    @property
    def has_ranking(self):
        return self.ranking_every > 0 or any(e["type"] in ("rank_break_start", "rank_set") for e in self.events)

    @property
    def ranking_played(self):
        return bool(self.sets) or any(e["type"] in ("rank_set", "rank_set_start", "rank_set_end") for e in self.events)

    @property
    def old_interlude(self):
        """A session of the old format: an Interlude (its ranking_sets rows are an Interlude's trials, not a break's)."""
        return bool(self.config.get("isInterlude")) or (bool(self.sets) and not self.has_ranking)

    @property
    def completed(self):
        return bool(self.row["completed"]) if "completed" in self.row else any(e["type"] == "session_end" for e in self.events)

    @property
    def old_breaks(self):
        """Ranking breaks logged by a build from before the sets had their own events and rows (no rank_set_start, no ranking_sets.csv)."""
        return any(e["type"] == "rank_break_start" for e in self.events) and not self.sets and not _of(self, "rank_set_start")

    @property
    def set_ids(self):
        """Tree ids of the bushes of the ranking sets: those the `rank_set` events carry, and (world known) every id past the world's table."""
        ids = {int(b["id"]) for e in self.events if e["type"] == "rank_set" for b in (e.get("payload") or {}).get("bushes", [])}
        if self.fruit_reward is not None:
            ids |= {e["tree_id"] for e in self.events if e["tree_id"] >= len(self.fruit_reward)}
        return ids

    @property
    def reduced(self):
        return any(e["type"] == "run_modes" for e in self.events) or (self.config.get("short") or 1) < 1


def _of(ctx, kind):
    return [e for e in ctx.events if e["type"] == kind]


def _payload(e):
    return e.get("payload") or {}


def _skip_no_ranking(name):
    return [Result(name, SKIP, "the session has no ranking (rankingEvery 0)")]


# --------------------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------------------

def check_foraging_points(ctx):
    fruits = _of(ctx, "fruit")
    points = ctx.foraging_points
    if ctx.config.get("isInterlude"):
        return [Result("foraging_points", SKIP, "an old Interlude: its trials restart the running total")]
    if points is None:
        return [Result("foraging_points", WARN, "not recorded in session.json")]
    out = []
    totals = [e["running_total"] for e in fruits]
    cumulative = np.cumsum([e["reward"] for e in fruits]) if fruits else np.array([])
    problems = []
    if fruits and abs(totals[-1] - points) > TOL:
        problems.append(f"foraging_points {points} != last running_total {totals[-1]}")
    bad = np.flatnonzero(np.abs(np.array(totals) - cumulative) > TOL) if fruits else []
    if len(bad):
        i = int(bad[0])
        problems.append(f"running_total {totals[i]} != cumulative reward {cumulative[i]} at fruit #{i} (t={fruits[i]['t']:.3f}; {len(bad)} fruits)")
    if not fruits and points != 0:
        problems.append(f"foraging_points {points} with no fruit event")
    out.append(Result("foraging_points = running_total", FAIL if problems else PASS, "; ".join(problems) or f"{points} after {len(fruits)} fruits"))
    total = float(np.sum([e["reward"] for e in fruits])) if fruits else 0.0
    out.append(Result("foraging_points = sum of fruit rewards", FAIL if abs(total - points) > TOL else PASS, f"foraging_points {points}, sum of rewards {total}"))
    return out


def check_fruit_rewards(ctx):
    name = "fruit rewards = world's pre-drawn rewards"
    if ctx.config.get("isInterlude"):
        return [Result(name, SKIP, "an Interlude plays on its own bush table (the .interlude.json), not the world file's")]
    if ctx.fruit_reward is None:
        return [Result(name, WARN, f"world file not available: {ctx.world_note}")]
    set_ids, n, k_max = ctx.set_ids, len(ctx.fruit_reward), ctx.fruit_reward.shape[1]
    problems, checked = [], 0
    for e in _of(ctx, "fruit"):
        tree, k = e["tree_id"], e["k"]
        if tree in set_ids:
            if e["reward"] != 0:
                problems.append(f"ranking-set bush {tree} paid {e['reward']} at t={e['t']:.3f}")
        elif not 0 <= tree < n or not 0 <= k < k_max:
            problems.append(f"fruit of bush {tree} k={k} is not in the world table ({n} bushes x {k_max} fruits) at t={e['t']:.3f}")
        else:
            checked += 1
            if e["reward"] != ctx.fruit_reward[tree, k]:
                problems.append(f"bush {tree} fruit {k} paid {e['reward']}, the world says {ctx.fruit_reward[tree, k]} (t={e['t']:.3f})")
    return [Result(name, FAIL if problems else PASS, "; ".join(problems[:5]) + (f" (+{len(problems) - 5} more)" if len(problems) > 5 else "") if problems else f"{checked} fruits")]


def _scored_values(row):
    """(picked values in rank order, all values) of a ranking_sets row's bushes."""
    bushes = row["bushes"] or []
    picked = sorted((b for b in bushes if b.get("rank") is not None), key=lambda b: b["rank"])
    return [b["value"] for b in picked], [b["value"] for b in bushes]


def check_ranking_sets(ctx):
    names = ("ranking pair scores", "ranking points", "rank_set_end = row")
    if not ctx.has_ranking:
        return [Result(n, SKIP, "the session has no ranking") for n in names]
    if not ctx.ranking_played:
        return [Result(n, SKIP, "no ranking set was played") for n in names]
    if not ctx.sets:
        return [Result(n, WARN if ctx.old_breaks else FAIL, "no ranking_sets rows") for n in names]
    bonus, practice = ctx.config.get("rankingBonusPerPair"), bool(ctx.config.get("isPractice"))
    pairs, points = [], []
    for i, row in enumerate(ctx.sets):
        if not row["bushes"]:
            pairs.append(f"set {i}: no bushes")
            continue
        picked, values = _scored_values(row)
        correct, total = ranking.pair_scores(picked, values, ctx.pool_tolerance)
        if (correct, total) != (row["correct_pairs"], row["total_pairs"]):
            pairs.append(f"set {i}: row {row['correct_pairs']}/{row['total_pairs']}, recomputed {correct}/{total}")
        if bonus is None or row["points"] is None:
            continue
        expect = 0 if practice else row["correct_pairs"] * bonus
        if abs(row["points"] - expect) > TOL:
            points.append(f"set {i}: points {row['points']}, expected {row['correct_pairs']} x {bonus}{' (practice: 0)' if practice else ''} = {expect}")
    out = [Result(names[0], FAIL if pairs else PASS, "; ".join(pairs) or f"{len(ctx.sets)} sets, tolerance {ctx.pool_tolerance}")]
    out.append(Result(names[1], WARN if bonus is None else (FAIL if points else PASS), "rankingBonusPerPair not in the config" if bonus is None else "; ".join(points) or "points = correct pairs x bonus"))
    ends = _of(ctx, "rank_set_end")
    if len(ends) != len(ctx.sets):
        out.append(Result(names[2], SKIP, f"{len(ends)} rank_set_end events for {len(ctx.sets)} rows (see ranking set events)"))
    else:
        diffs = []
        for i, (e, row) in enumerate(zip(ends, ctx.sets)):
            p = _payload(e)
            got = {"correct_pairs": p.get("correct_pairs"), "total_pairs": p.get("total_pairs"), "points": p.get("points", p.get("bonus"))}
            want = {"correct_pairs": row["correct_pairs"], "total_pairs": row["total_pairs"], "points": row["points"]}
            if got != want:
                diffs.append(f"set {i}: event {got}, row {want}")
        out.append(Result(names[2], FAIL if diffs else PASS, "; ".join(diffs) or f"{len(ends)} events"))
    return out


def check_session_totals(ctx):
    name = "ranking_points and session_end"
    out = []
    rp = ctx.row.get("ranking_points")
    if not ctx.has_ranking:
        out.append(Result("ranking_points", SKIP, "the session has no ranking"))
    elif rp is None:
        out.append(Result("ranking_points", WARN, "not recorded"))
    else:
        total = sum(r["points"] or 0 for r in (ctx.sets or []))
        out.append(Result("ranking_points = sum of set points", FAIL if abs(total - rp) > TOL else PASS, f"session.json {rp}, sum of rows {total}"))
    ends = _of(ctx, "session_end")
    if not ends:
        out.append(Result("session_end payload = session row", SKIP if not ctx.completed else WARN, "no session_end event"))
        return out
    p, problems = _payload(ends[-1]), []
    for key, row_value in (("foraging_points", ctx.foraging_points), ("ranking_points", rp)):
        if key in p and row_value is not None and abs(p[key] - row_value) > TOL:
            problems.append(f"{key}: event {p[key]}, session row {row_value}")
    missing = [k for k in ("foraging_points", "ranking_points") if k not in p]
    out.append(Result("session_end payload = session row", FAIL if problems else (WARN if missing and ctx.has_ranking else PASS),
                      "; ".join(problems) or (f"payload lacks {missing}" if missing else "agree")))
    return out


# --------------------------------------------------------------------------------------------------
# Integrity
# --------------------------------------------------------------------------------------------------

def check_event_sequence(ctx):
    ev = ctx.events
    seqs = np.array([e["seq"] for e in ev])
    gaps = np.flatnonzero(np.diff(seqs) != 1) if len(seqs) else []
    seq = Result("events seq contiguous", FAIL if len(gaps) else PASS,
                 f"seq {seqs[gaps[0]]} is followed by {seqs[gaps[0] + 1]} ({len(gaps)} breaks)" if len(gaps) else f"{len(ev)} events")
    back = [i for i in range(1, len(ev)) if ev[i]["t"] < ev[i - 1]["t"] - 1e-9 and ev[i]["type"] != "session_resume"]
    clock = Result("events t non-decreasing", FAIL if back else PASS,
                   f"t goes back from {ev[back[0] - 1]['t']:.3f} to {ev[back[0]]['t']:.3f} at seq {ev[back[0]]['seq']} ({len(back)} times)" if back else "")
    return [seq, clock]


def check_start_end(ctx):
    starts, ends = _of(ctx, "session_start"), _of(ctx, "session_end")
    problems = []
    if len(starts) != 1:
        problems.append(f"{len(starts)} session_start events")
    if ctx.completed and len(ends) != 1:
        problems.append(f"{len(ends)} session_end events in a completed session")
    if len(ends) > 1:
        problems.append(f"{len(ends)} session_end events")
    return [Result("session_start / session_end", FAIL if problems else PASS, "; ".join(problems) or f"1 start, {len(ends)} end" + ("" if ctx.completed else " (not completed)"))]


def check_trajectory_count(ctx):
    count = (ctx.row.get("frame_stats") or {}).get("count")
    if count is None:
        return [Result("trajectory frame count", WARN, "frame_stats.count not recorded")]
    resumed = bool(_of(ctx, "session_resume"))
    if len(ctx.traj) == count:
        return [Result("trajectory frame count", PASS, f"{count} frames")]
    return [Result("trajectory frame count", WARN if resumed else FAIL, f"{len(ctx.traj)} frames, frame_stats.count {count}" + (" (a resumed session)" if resumed else ""))]


def break_pairs(events):
    """([(start, end)] of the breaks that opened and closed in order, [problems]): a start inside an open break and an end outside one are problems; a break open at the end is (start, None)."""
    pairs, problems, open_at = [], [], None
    for e in events:
        if e["type"] == "rank_break_start":
            if open_at is not None:
                problems.append(f"rank_break_start at {e['t']:.3f} inside the break open since {open_at:.3f}")
            else:
                open_at = e["t"]
        elif e["type"] == "rank_break_end":
            if open_at is None:
                problems.append(f"rank_break_end at {e['t']:.3f} with no break open")
            else:
                pairs.append((open_at, e["t"]))
                open_at = None
    if open_at is not None:
        pairs.append((open_at, None))
    return pairs, problems


def check_break_events(ctx):
    if not ctx.has_ranking:
        return _skip_no_ranking("rank_break events balanced")
    pairs, problems = break_pairs(ctx.events)
    if pairs and pairs[-1][1] is None:
        problems.append(f"the break started at {pairs[-1][0]:.3f} never ended")
    return [Result("rank_break events balanced", FAIL if problems else PASS, "; ".join(problems) or f"{len(pairs)} breaks")]


def check_set_events(ctx):
    name = "ranking set events"
    if not ctx.has_ranking:
        return _skip_no_ranking(name)
    if not ctx.ranking_played:
        return [Result(name, SKIP, "no ranking set was played")]
    counts = {k: len(_of(ctx, k)) for k in ("rank_set", "rank_set_start", "rank_set_end")}
    problems = []
    if len(set(counts.values())) != 1:
        problems.append(f"rank_set / rank_set_start / rank_set_end events: {counts['rank_set']} / {counts['rank_set_start']} / {counts['rank_set_end']}")
    rows = len(ctx.sets) if ctx.sets is not None else None
    if rows is None:
        problems.append("no ranking_sets rows")
    elif rows != counts["rank_set_end"]:
        problems.append(f"{rows} ranking_sets rows for {counts['rank_set_end']} rank_set_end events")
    if ctx.sets:
        seqs = [r["seq"] for r in ctx.sets]
        if seqs != list(range(seqs[0], seqs[0] + len(seqs))):
            problems.append(f"ranking_sets seq {seqs} is not contiguous")
    return [Result(name, FAIL if problems else PASS, "; ".join(problems) or f"{counts['rank_set_end']} sets, {rows} rows")]


def check_world(ctx):
    return [Result("world file hash", PASS if ctx.world_found else WARN, ctx.world_note)]


# --------------------------------------------------------------------------------------------------
# Break rules
# --------------------------------------------------------------------------------------------------

def _tiles(centres, xz):
    """Nearest tile of each (x, z) row (WorldData.NearestTile)."""
    out = np.empty(len(xz), dtype=int)
    for lo in range(0, len(xz), 1000):
        d = ((xz[lo:lo + 1000, None, :] - centres[None, :, :]) ** 2).sum(-1)
        out[lo:lo + 1000] = d.argmin(1)
    return out


def _complete_breaks(ctx):
    return [(s, e) for s, e in break_pairs(ctx.events)[0] if e is not None]


def _foraging_time(t, breaks):
    """Foraging seconds at session time t: t minus the time held by the breaks that ended before t (a break open at t holds up to t)."""
    return t - sum(min(e, t) - s for s, e in breaks if s < t)


def check_break_rules(ctx):
    if not ctx.has_ranking:
        return _skip_no_ranking("break rules")
    cfg, breaks = ctx.config, _complete_breaks(ctx)
    out = []
    ev, tr = ctx.events, ctx.traj
    starts = [s for s, _ in breaks]
    every, cooldown = max(ctx.ranking_every, 1), cfg.get("rankingCooldown")
    duration, last = cfg.get("sessionDuration"), cfg.get("rankingLastSeconds")
    resumed = bool(_of(ctx, "session_resume"))

    # a patch switch before each break, and as many as rankingEvery
    if ctx.tile_centres is None:
        out.append(Result("break after a patch switch", WARN, f"tile centres unknown (world file not available: {ctx.world_note})"))
    elif not breaks or not len(tr):
        out.append(Result("break after a patch switch", SKIP, "no complete break"))
    else:
        tile = _tiles(ctx.tile_centres, tr[:, 1:3])
        problems, notes, ref_time = [], [], tr[0, 0]
        start_event = {e["t"]: _payload(e) for e in _of(ctx, "rank_break_start")}
        for k, (s, e) in enumerate(breaks):
            lo, hi = np.searchsorted(tr[:, 0], ref_time, "left"), np.searchsorted(tr[:, 0], s + TIME_EPS, "right")
            seg = tile[lo:hi]
            changes = int((seg[1:] != seg[:-1]).sum()) if len(seg) else 0
            if len(seg) == 0 or (seg == seg[0]).all():
                problems.append(f"break {k + 1} at t={s:.3f}: the player stayed in tile {seg[0] if len(seg) else '?'} since t={ref_time:.3f}")
            elif changes < every:
                (notes if cfg.get("rankingSettleDepth") or resumed else problems).append(f"break {k + 1}: {changes} tile changes since t={ref_time:.3f}, rankingEvery {every}")
            logged = start_event.get(s, {})
            if logged.get("switches") is not None and logged["switches"] < every:
                problems.append(f"break {k + 1}: logged switches {logged['switches']} < rankingEvery {every}")
            if logged.get("tile") is not None and len(seg) and int(seg[-1]) != logged["tile"]:
                notes.append(f"break {k + 1}: logged tile {logged['tile']}, nearest tile at the start {int(seg[-1])}")
            ref_time = e
        out.append(Result("break after a patch switch", FAIL if problems else (WARN if notes else PASS), "; ".join(problems + notes) or f"{len(breaks)} breaks, each after a tile change"))

    # the cooldown
    if cooldown is None:
        out.append(Result("break cooldown", WARN, "rankingCooldown not in the config"))
    else:
        problems = []
        for k in range(1, len(breaks)):
            gap = _foraging_time(breaks[k][0], breaks) - _foraging_time(breaks[k - 1][1], breaks)
            if gap < cooldown - COOLDOWN_TOL:
                problems.append(f"break {k + 1} started {gap:.2f} foraging seconds after break {k} ended (rankingCooldown {cooldown})")
        out.append(Result("break cooldown", FAIL if problems else PASS, "; ".join(problems) or f"{max(len(breaks) - 1, 0)} gaps >= {cooldown} s"))

    # enough bushes harvested before the first break
    need = cfg.get("rankingMinBushes")
    if need is None or not starts:
        out.append(Result("bushes before the first break", WARN if need is None else SKIP, "rankingMinBushes not in the config" if need is None else "no break"))
    else:
        bushes = {e["tree_id"] for e in _of(ctx, "fruit") if e["t"] < starts[0] and e["tree_id"] not in ctx.set_ids}
        out.append(Result("bushes before the first break", FAIL if len(bushes) < need else PASS, f"{len(bushes)} distinct bushes had a fruit before t={starts[0]:.3f}, rankingMinBushes {need}"))

    # not in the last seconds
    if duration is None or last is None:
        out.append(Result("no break in the last seconds", WARN, "sessionDuration or rankingLastSeconds not in the config"))
    else:
        problems, notes = [], []
        for k, (s, _) in enumerate(breaks):
            left = duration - _foraging_time(s, breaks[:k])
            if left <= 0:
                problems.append(f"break {k + 1} started with {left:.2f} s left")
            elif left <= last:        # the switch counted earlier, the start waited for a harvest bout to end: not decidable from the log
                notes.append(f"break {k + 1} started with {left:.2f} s left (rankingLastSeconds {last}; a bout may have delayed it)")
        out.append(Result("no break in the last seconds", FAIL if problems else (WARN if notes else PASS), "; ".join(problems + notes) or "ok"))

    # the player stays and no foraging fruit is taken
    still, fruit = [], []
    set_ends = [e["t"] for e in _of(ctx, "rank_set_end")]
    for k, (s, e) in enumerate(breaks):
        # The player stands from the start until the last set's end (then walks free while the real bushes regrow): one fixed step of momentum
        # may remain in the first frames (up to SETTLE_MOVE), then nothing moves.
        stop = max([t for t in set_ends if s <= t <= e] or [e])
        inside = tr[(tr[:, 0] > s + TIME_EPS) & (tr[:, 0] <= stop + TIME_EPS)]
        if len(tr) and len(inside):
            at_start = tr[max(np.searchsorted(tr[:, 0], s + TIME_EPS, "right") - 1, 0), 1:3]
            settled = inside[inside[:, 0] >= s + SETTLE_SECONDS]
            drift = float(np.max(np.abs(inside[:, 1:3] - at_start)))
            move = float(np.max(np.abs(settled[:, 1:3] - settled[0, 1:3]))) if len(settled) else 0.0
            if move > STILL_TOL or drift > SETTLE_MOVE:
                still.append(f"break {k + 1} ({s:.3f}-{stop:.3f}): the player moved {drift:.4f} from the start, {move:.4f} after {SETTLE_SECONDS} s")
        for f in _of(ctx, "fruit"):
            if s < f["t"] <= e and f["tree_id"] not in ctx.set_ids:
                fruit.append(f"break {k + 1}: fruit of world bush {f['tree_id']} at t={f['t']:.3f}")
    out.append(Result("player still during a break", FAIL if still else PASS, "; ".join(still) or f"{len(breaks)} breaks"))
    out.append(Result("no foraging fruit during a break", FAIL if fruit else PASS, "; ".join(fruit) or f"{len(breaks)} breaks"))

    # the foraging clock
    ends = _of(ctx, "session_end")
    if not ctx.completed or duration is None or not (ends or len(tr)):
        out.append(Result("foraging time = sessionDuration", SKIP, "session not completed"))
    else:
        end = ends[-1]["t"] if ends else float(tr[-1, 0])
        foraging = _foraging_time(end, breaks)
        off = abs(foraging - duration) > CLOCK_TOL
        detail = f"foraging time {foraging:.2f} s (session clock {end:.2f} s minus {end - foraging:.2f} s of breaks), sessionDuration {duration:.2f}"
        out.append(Result("foraging time = sessionDuration", (WARN if ctx.reduced else FAIL) if off else PASS, detail + (" (a reduced run)" if ctx.reduced else "")))

    # the pool, in order
    if not ctx.sets:
        out.append(Result("pool order", SKIP, "no ranking_sets rows"))
    else:
        size = ctx.pool_size or cfg.get("rankingPoolSets")
        idx = [r["pool_index"] for r in ctx.sets]
        first = idx[0]
        bad = [i for i, v in enumerate(idx) if v != (first + i) % size] if size else []
        problems = [f"pool_index {idx} is not consecutive from {first} modulo {size}"] if bad else []
        if first != 0 and not resumed:
            problems.append(f"the first set is pool_index {first}, not 0")
        out.append(Result("pool order", FAIL if problems else PASS, "; ".join(problems) or f"pool_index {idx}"))
    return out


# --------------------------------------------------------------------------------------------------
# Loading and running
# --------------------------------------------------------------------------------------------------

SCORING = ("foraging_points = running_total", "foraging_points = sum of fruit rewards", "fruit rewards = world's pre-drawn rewards")      # stay FAIL in any format
CHECKS = (check_foraging_points, check_fruit_rewards, check_ranking_sets, check_session_totals,
          check_event_sequence, check_start_end, check_trajectory_count, check_break_events, check_set_events, check_world,
          check_break_rules)


def _find_pool(world_path, world_file):
    stem = world_file[:-len(".world")] if world_file.endswith(".world") else world_file
    for folder in (Path(world_path).parent, *sorted(replay.WORLD_DIR.glob("*"))):
        path = Path(folder) / f"{stem}.ranking.json"
        if path.exists():
            return json.loads(path.read_text())
    return None


def load_ctx(folder):
    """A session folder as a Ctx; the world is looked for by replay.find_world_file and its absence is a note, not an error."""
    folder = Path(folder)
    data = rundata.read_session(folder)
    row = data["session"]
    ctx = Ctx(row=row, traj=data["traj"], events=data["events"], sets=data["sets"], truncated=data["truncated"])
    try:
        path = replay.find_world_file(row["world_file"], row["world_sha256"], folder.resolve().parent.parent / "_worlds")
        header, _ = read_unity_world(path)
        ctx.fruit_reward = np.asarray(header["fruitRewards"], dtype=int).reshape(len(header["canopyRadius"]), int(header["fruitCount"]))
        if header.get("tileCentres"):
            ctx.tile_centres = np.asarray(header["tileCentres"], dtype=float).reshape(-1, 2)
        ctx.world_found, ctx.world_note = True, f"{path.name} sha256 {row['world_sha256'][:12]}"
        pool = _find_pool(path, row["world_file"])
        if pool:
            ctx.pool_tolerance, ctx.pool_size = float(pool.get("tieTolerance", ranking.TIE_TOLERANCE)), len(pool.get("sets") or []) or None
    except (FileNotFoundError, KeyError, ValueError, OSError) as err:
        ctx.world_note = f"{type(err).__name__}: {err}"[:300]
    return ctx


def run_checks(ctx):
    out = []
    if ctx.old_interlude:
        out.append(Result("format", WARN, "old format: an Interlude session (trial rows, no ranking breaks); the ranking checks are skipped"))
    for check in CHECKS:
        out.extend(check(ctx))
    if ctx.old_breaks:        # an early prototype of the breaks: its rules and logging were different, so a disagreement is no evidence of a fault
        out = [Result(r.name, WARN, "old format (breaks logged before rank_set_start and ranking_sets): " + r.detail) if r.status == FAIL and r.name not in SCORING else r for r in out]
    if ctx.truncated:
        out.append(Result("files complete", WARN, f"{', '.join(ctx.truncated)} ended mid-line; the last line was dropped"))
    return out


def validate_session(folder):
    """The Results of one session folder; a folder that cannot be read is one FAIL (an old column layout, one WARN)."""
    try:
        ctx = load_ctx(folder)
    except ValueError as err:
        old = "header" in str(err)
        return [Result("load", WARN if old else FAIL, ("old format: " if old else "unreadable: ") + str(err)[:300])]
    except (OSError, KeyError, TypeError) as err:
        return [Result("load", FAIL, f"unreadable: {type(err).__name__}: {err}"[:300])]
    return run_checks(ctx)


def session_folders(path):
    """The session folders at `path`: itself, or the numbered subfolders of a run folder."""
    path = Path(path)
    if (path / "session.json").exists():
        return [path]
    return sorted(p for p in path.iterdir() if p.is_dir() and (p / "session.json").exists()) if path.is_dir() else []


def all_runs(root=None):
    root = Path(root or replay.DATA_DIR)
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "run.json").exists())


def resolve(arg):
    """A session or run folder from a path or a run id (a prefix is enough when unique) under ForagingData/."""
    path = Path(arg)
    if path.exists():
        return path
    if (replay.PROJECT_ROOT / path).exists():
        return replay.PROJECT_ROOT / path
    matches = [p for p in all_runs() if p.name.startswith(str(arg))]
    if len(matches) != 1:
        raise SystemExit(f"{arg}: no such folder, and {len(matches)} runs under {replay.DATA_DIR} start with it")
    return matches[0]


def _label(folder):
    folder = Path(folder)
    return f"{folder.parent.name[:8]}/{folder.name}" if (folder / "session.json").exists() else folder.name[:8]


def format_table(label, results):
    lines = [f"== {label}"]
    width = max(len(r.name) for r in results)
    lines += [f"  {r.status:<4}  {r.name:<{width}}  {r.detail}".rstrip() for r in results]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("target", nargs="?", help="session folder, run folder or run id")
    parser.add_argument("--all", action="store_true", help="every run under ForagingData/")
    parser.add_argument("--json", action="store_true", help="print the results as JSON")
    args = parser.parse_args(argv)
    if not args.all and not args.target:
        parser.error("give a session folder, a run folder or a run id, or --all")
    runs = all_runs() if args.all else [resolve(args.target)]
    sessions = [f for run in runs for f in session_folders(run)]
    if not sessions:
        raise SystemExit("no session folders found")
    report = [(_label(f), validate_session(f)) for f in sessions]
    counts = {s: sum(r.status == s for _, rs in report for r in rs) for s in (PASS, WARN, FAIL, SKIP)}
    if args.json:
        print(json.dumps({"sessions": [{"session": label, "results": [r.__dict__ for r in rs]} for label, rs in report], "summary": counts}, indent=1))
    else:
        for label, rs in report:
            print(format_table(label, rs))
        failing = [label for label, rs in report if any(r.status == FAIL for r in rs)]
        print(f"\n{len(report)} sessions: {counts[PASS]} PASS, {counts[WARN]} WARN, {counts[FAIL]} FAIL, {counts[SKIP]} SKIP"
              + (f"; FAIL in {', '.join(failing)}" if failing else ""))
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
