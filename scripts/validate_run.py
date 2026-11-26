"""Validate logged runs: is the data self-consistent, is the scoring right, and did the game follow the selection-break rules of the design?

    ./venv/bin/python scripts/validate_run.py <session folder | run folder | run id> [--json]
    ./venv/bin/python scripts/validate_run.py --all [--json]       # every run under ForagingData/ (not _worlds, _db_backup*, other non-run folders)

Read-only. One table per session folder (ForagingData/<run>/<NN>/) of checks, each PASS / WARN / FAIL / SKIP with the numbers that disagree, a summary
line, and exit code 1 if any check FAILs. FAIL means the data or the scoring is wrong; WARN is a case the logs cannot decide (a world file
that cannot be found, a reduced run). Three groups (docs/VALIDATION_PLAN.md, Layer 1):

  scoring    foraging_points = the last running_total = the sum of the fruit rewards, each fruit pays the world's pre-drawn reward; each selection set's
             correct_pairs / total_pairs recomputed with `selection.pair_scores`, its points, the `rank_set_end` event, ranking_points and `session_end`.
  integrity  event seq and clock, session_start / session_end, trajectory frame count, selection break and set events, the world file's hash.
  breaks     the design's rules: a patch switch before each break, the cooldown, the minimum of harvested bushes, the last seconds, selectionEvery, the player
             still and no foraging fruit during a break, the foraging clock lasting sessionDuration, the pool played in order.

Each check is a small function from a `Ctx` (one session's loaded data) to a list of `Result`, so tests call them directly.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

import selection
import replay
import rundata
from replay import _payload
from world import read_unity_world

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
TOL = 1e-6              # points are whole numbers; a sum differing by more than this is wrong
CLOCK_TOL = 1.5         # seconds a session's foraging time may differ from sessionDuration
COOLDOWN_TOL = 0.05     # seconds
DENSE_POINTS_TOL = 0.01    # points: the logged bush values are rounded to 4 decimals, so the dense score recomputed from them differs from the game's by up to about 0.002
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
    pool_tolerance: float = selection.TIE_TOLERANCE
    pool_size: int = None
    truncated: list = field(default_factory=list)

    @property
    def config(self):
        return self.row.get("config") or {}

    @property
    def foraging_points(self):
        return self.row.get("foraging_points")

    @property
    def selection_every(self):
        return self.config.get("selectionEvery") or 0

    @property
    def schedule(self):
        """The patch leavings after which a selection is due (selectionLeavings), [] when the rule is 'every selectionEvery-th'."""
        return [int(n) for n in (self.config.get("selectionLeavings") or [])]

    @property
    def has_selection(self):
        return self.selection_every > 0 or any(e["type"] in ("rank_break_start", "rank_set") for e in self.events)

    @property
    def selection_played(self):
        return bool(self.sets) or any(e["type"] in ("rank_set", "rank_set_start", "rank_set_end") for e in self.events)

    @property
    def unsupported(self):
        """Why this log is of a format no longer validated (git history at b7e1895 has the code that handled them), else None."""
        if self.config.get("isInterlude") or (bool(self.sets) and not self.has_selection):
            return "an Interlude session (trial rows, no selection breaks)"
        if "foraging_points" not in self.row and "final_score" in self.row:
            return "the old final_score column (before 2026-11-14)"
        if any(e["type"] == "rank_break_start" for e in self.events) and not self.sets and not _of(self, "rank_set_start"):
            return "selection breaks of the early prototype (no rank_set_start events, no ranking_sets rows)"
        return None

    @property
    def completed(self):
        return bool(self.row["completed"]) if "completed" in self.row else any(e["type"] == "session_end" for e in self.events)

    @property
    def set_ids(self):
        """Tree ids of the bushes of the selection sets: those the `rank_set` events carry, and (world known) every id past the world's table."""
        ids = {int(b["id"]) for e in self.events if e["type"] == "rank_set" for b in (e.get("payload") or {}).get("bushes", [])}
        if self.fruit_reward is not None:
            ids |= {e["tree_id"] for e in self.events if e["tree_id"] >= len(self.fruit_reward)}
        return ids

    @property
    def reduced(self):
        return any(e["type"] == "run_modes" for e in self.events) or (self.config.get("short") or 1) < 1


def _of(ctx, kind):
    return [e for e in ctx.events if e["type"] == kind]


def _skip_no_selection(name):
    return [Result(name, SKIP, "the session has no selection (selectionEvery 0)")]


# --------------------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------------------

def check_foraging_points(ctx):
    fruits = _of(ctx, "fruit")
    points = ctx.foraging_points
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
    if ctx.fruit_reward is None:
        return [Result(name, WARN, f"world file not available: {ctx.world_note}")]
    set_ids, n, k_max = ctx.set_ids, len(ctx.fruit_reward), ctx.fruit_reward.shape[1]
    problems, checked = [], 0
    for e in _of(ctx, "fruit"):
        tree, k = e["tree_id"], e["k"]
        if tree in set_ids:
            if e["reward"] != 0:
                problems.append(f"selection-set bush {tree} paid {e['reward']} at t={e['t']:.3f}")
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


def _check_dense_sets(ctx, names):
    """The dense design's scoring (selection.top_k_score, top_k_hits, paid_set_index; SelectionBreak.FinishSet): a row's correct_pairs is the number of the picked bushes among the grid's best k, total_pairs is k, its points the
    0 to selectionTopKPoints score if the selection pays (selectionPaid 'all', or 'one': the pool set the world seed draws) and 0 in a practice session."""
    cfg = ctx.config
    k, scale = int(cfg.get("selectionPicks") or 5), float(cfg.get("selectionTopKPoints") or 100.0)
    paid_mode, practice = str(cfg.get("selectionPaid") or "all"), bool(cfg.get("isPractice"))
    sets = int(ctx.pool_size or cfg.get("selectionPoolSets") or len(ctx.sets))
    paid_index = selection.paid_set_index(int(cfg.get("worldSeed") or 0), sets)
    pairs, points = [], []
    for i, row in enumerate(ctx.sets):
        if not row["bushes"]:
            pairs.append(f"set {i}: no bushes")
            continue
        bushes = row["bushes"]
        picked = [b for b in sorted((b for b in bushes if b.get("rank") is not None), key=lambda b: b["rank"])]
        by_id = {b["id"]: b["value"] for b in bushes}
        hits = selection.top_k_hits([b["id"] for b in picked], by_id, k)
        if (hits, k) != (row["correct_pairs"], row["total_pairs"]):
            pairs.append(f"set {i}: row {row['correct_pairs']}/{row['total_pairs']}, recomputed {hits}/{k}")
        score = selection.top_k_score([b["value"] for b in picked], list(by_id.values()), k, scale)
        pays = paid_mode == "all" or row["pool_index"] == paid_index
        expect = 0.0 if practice or not pays else score
        if row["points"] is not None and abs(row["points"] - expect) > DENSE_POINTS_TOL:
            points.append(f"set {i}: points {row['points']}, expected {expect:g} (score {score:g}, pays {pays}, mode {paid_mode}){' (practice: 0)' if practice else ''}")
    out = [Result(names[0], FAIL if pairs else PASS, "; ".join(pairs) or f"{len(ctx.sets)} sets, top-{k} hits")]
    out.append(Result(names[1], FAIL if points else PASS, "; ".join(points) or f"points = the top-k score, paid {paid_mode} (set {paid_index} when one)"))
    ends = _of(ctx, "rank_set_end")
    if len(ends) != len(ctx.sets):
        out.append(Result(names[2], SKIP, f"{len(ends)} rank_set_end events for {len(ctx.sets)} rows (see selection set events)"))
    else:
        diffs = []
        for i, (e, row) in enumerate(zip(ends, ctx.sets)):
            p = _payload(e)
            got = {"correct_pairs": p.get("correct_pairs"), "total_pairs": p.get("total_pairs"), "points": p.get("points")}
            want = {"correct_pairs": row["correct_pairs"], "total_pairs": row["total_pairs"], "points": row["points"]}
            if got != want:
                diffs.append(f"set {i}: event {got}, row {want}")
        out.append(Result(names[2], FAIL if diffs else PASS, "; ".join(diffs) or f"{len(ends)} events"))
    return out


def check_ranking_sets(ctx):
    names = ("selection pair scores", "selection points", "rank_set_end = row")
    if not ctx.has_selection:
        return [Result(n, SKIP, "the session has no selection") for n in names]
    if not ctx.selection_played:
        return [Result(n, SKIP, "no selection set was played") for n in names]
    if not ctx.sets:
        return [Result(n, FAIL, "no ranking_sets rows") for n in names]
    if str(ctx.config.get("selectionDesign") or "") == "dense":
        return _check_dense_sets(ctx, names)
    bonus, practice, mode = ctx.config.get("selectionBonusPerPair"), bool(ctx.config.get("isPractice")), ctx.config.get("selectionPointsMode") or "pair"
    pairs, points = [], []
    if mode not in selection.POINTS_MODES:
        return [Result(n, FAIL, f"unknown selectionPointsMode {mode!r}") for n in names]
    for i, row in enumerate(ctx.sets):
        if not row["bushes"]:
            pairs.append(f"set {i}: no bushes")
            continue
        picked, values = _scored_values(row)
        expected_points, correct, total = selection.selections_to_points(picked, values, bonus or 0.0, mode, ctx.pool_tolerance)
        if (correct, total) != (row["correct_pairs"], row["total_pairs"]):
            pairs.append(f"set {i}: row {row['correct_pairs']}/{row['total_pairs']}, recomputed {correct}/{total}")
        if bonus is None or row["points"] is None:
            continue
        expect = 0 if practice else expected_points
        if abs(row["points"] - expect) > TOL:
            points.append(f"set {i}: points {row['points']}, expected {expect:g} ({row['correct_pairs']} correct pairs, bonus {bonus}, mode {mode or 'pair'}){' (practice: 0)' if practice else ''}")
    out = [Result(names[0], FAIL if pairs else PASS, "; ".join(pairs) or f"{len(ctx.sets)} sets, tolerance {ctx.pool_tolerance}")]
    out.append(Result(names[1], WARN if bonus is None else (FAIL if points else PASS), "selectionBonusPerPair not in the config" if bonus is None else "; ".join(points) or f"points = the payout rule, mode {mode}"))
    ends = _of(ctx, "rank_set_end")
    if len(ends) != len(ctx.sets):
        out.append(Result(names[2], SKIP, f"{len(ends)} rank_set_end events for {len(ctx.sets)} rows (see selection set events)"))
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
    if not ctx.has_selection:
        out.append(Result("ranking_points", SKIP, "the session has no selection"))
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
    out.append(Result("session_end payload = session row", FAIL if problems else (WARN if missing and ctx.has_selection else PASS),
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
    if not ctx.has_selection:
        return _skip_no_selection("rank_break events balanced")
    pairs, problems = break_pairs(ctx.events)
    if pairs and pairs[-1][1] is None:
        problems.append(f"the break started at {pairs[-1][0]:.3f} never ended")
    return [Result("rank_break events balanced", FAIL if problems else PASS, "; ".join(problems) or f"{len(pairs)} breaks")]


def _aborted_windows(ctx):
    """[(start, end)] of the breaks a resume cut short (their end event says `aborted`): the game played such a break again, so its unscored try is not a set."""
    aborted = {e["t"] for e in _of(ctx, "rank_break_end") if _payload(e).get("aborted")}
    return [(s, e) for s, e in break_pairs(ctx.events)[0] if e is not None and e in aborted]


def check_set_events(ctx):
    name = "selection set events"
    if not ctx.has_selection:
        return _skip_no_selection(name)
    if not ctx.selection_played:
        return [Result(name, SKIP, "no selection set was played")]
    counts = {k: len(_of(ctx, k)) for k in ("rank_set", "rank_set_start", "rank_set_end")}
    for s, e in _aborted_windows(ctx):          # a try cut short by a resume has its rank_set (and maybe rank_set_start) but no rank_set_end
        inside = {k: sum(s <= x["t"] <= e for x in _of(ctx, k)) for k in counts}
        counts["rank_set"] -= max(inside["rank_set"] - inside["rank_set_end"], 0)
        counts["rank_set_start"] -= max(inside["rank_set_start"] - inside["rank_set_end"], 0)
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


SCHEDULE_TOL = 0.25      # seconds: a break may not start earlier than its scheduled foraging second (the frame it fell due in)


def _scheduled_breaks(ctx, breaks, times, start_payload, number, resumed):
    """The fixed schedule (selectionTimes, SelectionBreak.TickSchedule): break k starts at its scheduled foraging second or after, at most selectionMaxWait (the bout that outlasts it is cancelled) and one more
    second later; every scheduled break of a completed session happens; each `rank_due` event is numbered 1, 2, ... and says the scheduled time."""
    cfg = ctx.config
    wait = float(cfg.get("selectionMaxWait") if cfg.get("selectionMaxWait") is not None else 10.0)
    problems = []
    for k, (s, _) in enumerate(breaks):
        nb = number(k, s)
        if nb > len(times):
            problems.append(f"break {nb} is beyond the schedule of {len(times)}")
            continue
        elapsed = _foraging_time(s, breaks[:k])
        if elapsed < times[nb - 1] - SCHEDULE_TOL:
            problems.append(f"break {nb} started at foraging second {elapsed:.2f}, before its time {times[nb - 1]:g}")
        elif elapsed > times[nb - 1] + wait + 1.0 and not resumed:
            problems.append(f"break {nb} started at foraging second {elapsed:.2f}, later than its time {times[nb - 1]:g} plus selectionMaxWait {wait:g}")
    due = [_payload(e) for e in _of(ctx, "rank_due")]
    if not resumed:
        if [p.get("n") for p in due] != list(range(1, len(due) + 1)):
            problems.append(f"the rank_due numbers are {[p.get('n') for p in due][:8]}, not 1, 2, 3, ...")
        for p in due:
            if p.get("n", 0) <= len(times) and abs(float(p.get("scheduled", -1)) - times[p["n"] - 1]) > 1e-6:
                problems.append(f"rank_due {p['n']} says scheduled {p.get('scheduled')}, the schedule says {times[p['n'] - 1]:g}")
    duration = cfg.get("sessionDuration")
    if ctx.completed and duration is not None and not resumed and not ctx.reduced and len(breaks) != len([x for x in times if x <= duration - 1.0]):
        problems.append(f"{len(breaks)} breaks for the schedule {times} in a session of {duration:g} s")
    return [Result("scheduled breaks", FAIL if problems else PASS, "; ".join(problems) or f"{len(breaks)} breaks at or after {times[:len(breaks)]}")]


def check_break_rules(ctx):
    if not ctx.has_selection:
        return _skip_no_selection("break rules")
    cfg, breaks = ctx.config, _complete_breaks(ctx)
    out = []
    ev, tr = ctx.events, ctx.traj
    starts = [s for s, _ in breaks]
    every, cooldown = max(ctx.selection_every, 1), cfg.get("selectionCooldown")
    sched = ctx.schedule
    start_payload = {e["t"]: _payload(e) for e in _of(ctx, "rank_break_start")}

    def number(k, s):                   # a break's number: the logged one (a break played again after a resume keeps it), else its position
        return start_payload.get(s, {}).get("break") or k + 1
    duration, last = cfg.get("sessionDuration"), cfg.get("selectionLastSeconds")
    resumed = bool(_of(ctx, "session_resume"))
    times = [float(x) for x in (cfg.get("selectionTimes") or [])]
    scheduled = bool(times)
    if scheduled:
        out += _scheduled_breaks(ctx, breaks, times, start_payload, number, resumed)

    # a patch switch before each break, and as many as selectionEvery
    if scheduled:
        pass                                      # (the fixed schedule replaces the patch-switch rules: the checks above)
    elif ctx.tile_centres is None:
        out.append(Result("break after a patch switch", WARN, f"tile centres unknown (world file not available: {ctx.world_note})"))
    elif not breaks or not len(tr):
        out.append(Result("break after a patch switch", SKIP, "no complete break"))
    else:
        tile = _tiles(ctx.tile_centres, tr[:, 1:3])
        problems, notes, ref_time = [], [], tr[0, 0]
        for k, (s, e) in enumerate(breaks):
            logged = start_payload.get(s, {})
            if logged.get("resumed"):          # a break played again straight after the resume that cut it short: no walking in between
                ref_time = e
                continue
            lo, hi = np.searchsorted(tr[:, 0], ref_time, "left"), np.searchsorted(tr[:, 0], s + TIME_EPS, "right")
            seg = tile[lo:hi]
            changes = int((seg[1:] != seg[:-1]).sum()) if len(seg) else 0
            if len(seg) == 0 or (seg == seg[0]).all():
                problems.append(f"break {k + 1} at t={s:.3f}: the player stayed in tile {seg[0] if len(seg) else '?'} since t={ref_time:.3f}")
            nb = number(k, s)
            need = (sched[nb - 1] - (sched[nb - 2] if nb > 1 else 0)) if nb <= len(sched) else every          # leavings since the last break: the schedule's step, or selectionEvery
            if len(seg) and not (seg == seg[0]).all() and changes < need:
                (notes if cfg.get("selectionSettleDepth") or resumed else problems).append(f"break {k + 1}: {changes} tile changes since t={ref_time:.3f}, {need} leavings due")
            if not sched and logged.get("switches") is not None and logged["switches"] < every:
                problems.append(f"break {k + 1}: logged switches {logged['switches']} < selectionEvery {every}")
            if logged.get("tile") is not None and len(seg) and int(seg[-1]) != logged["tile"]:
                notes.append(f"break {k + 1}: logged tile {logged['tile']}, nearest tile at the start {int(seg[-1])}")
            ref_time = e
        out.append(Result("break after a patch switch", FAIL if problems else (WARN if notes else PASS), "; ".join(problems + notes) or f"{len(breaks)} breaks, each after a tile change"))

    # the scheduled leavings (selectionLeavings): each break comes at the next number of the schedule, and the qualifying leavings are numbered 1, 2, 3, ... (a resume restarts the count)
    if sched and not scheduled:
        problems, leaving_events = [], [_payload(e) for e in _of(ctx, "rank_leaving")]
        if not resumed:
            numbers = [p.get("n") for p in leaving_events]
            if numbers != list(range(1, len(numbers) + 1)):
                problems.append(f"the rank_leaving numbers are {numbers[:12]}, not 1, 2, 3, ...")
            numbers_seen = {number(k, s) for k, (s, _) in enumerate(breaks)}
            if len(numbers_seen) > len(sched):
                problems.append(f"{len(numbers_seen)} breaks for a schedule of {len(sched)}")
            for k, (s, _) in enumerate(breaks):
                nb, logged = number(k, s), start_payload.get(s, {}).get("leaving")
                if nb <= len(sched) and logged is not None and logged != sched[nb - 1]:
                    problems.append(f"break {nb} came at leaving {logged}, the schedule says {sched[nb - 1]}")
            for p in leaving_events:
                if p.get("due") and p.get("n") not in sched and not any(q.get("due") for q in leaving_events if q.get("n", 0) < p.get("n", 0)):
                    problems.append(f"leaving {p.get('n')} was flagged due but is not in the schedule {sched}")
        out.append(Result("scheduled leavings", FAIL if problems else PASS, "; ".join(problems) or f"{len(leaving_events)} leavings, {len(breaks)} breaks, schedule {sched}"))

    # the cooldown
    if scheduled:
        pass
    elif cooldown is None:
        out.append(Result("break cooldown", WARN, "selectionCooldown not in the config"))
    else:
        problems = []
        for k in range(1, len(breaks)):
            if start_payload.get(breaks[k][0], {}).get("resumed"):
                continue
            gap = _foraging_time(breaks[k][0], breaks) - _foraging_time(breaks[k - 1][1], breaks)
            if gap < cooldown - COOLDOWN_TOL:
                problems.append(f"break {k + 1} started {gap:.2f} foraging seconds after break {k} ended (selectionCooldown {cooldown})")
        out.append(Result("break cooldown", FAIL if problems else PASS, "; ".join(problems) or f"{max(len(breaks) - 1, 0)} gaps >= {cooldown} s"))

    # enough bushes harvested between breaks (selectionMinBushes since the last selection ended, since the session began before the first; a resume does not restore the count, so a break right after one only warns)
    need = cfg.get("selectionMinBushes")
    if scheduled:
        pass
    elif need is None or not starts:
        out.append(Result("bushes between breaks", WARN if need is None else SKIP, "selectionMinBushes not in the config" if need is None else "no break"))
    else:
        problems, notes, since = [], [], 0.0
        resume_times = [e["t"] for e in _of(ctx, "session_resume")]
        for k, (s, e) in enumerate(breaks):
            bushes = {f["tree_id"] for f in _of(ctx, "fruit") if since <= f["t"] < s and f["tree_id"] not in ctx.set_ids}
            if len(bushes) < need:
                (notes if any(since <= t <= s for t in resume_times) else problems).append(f"break {number(k, s)} started after {len(bushes)} distinct bushes had a fruit since t={since:.3f}, selectionMinBushes {need}")
            since = e
        out.append(Result("bushes between breaks", FAIL if problems else (WARN if notes else PASS), "; ".join(problems + notes) or f"{len(breaks)} breaks, each after at least {need} bushes"))

    # not in the last seconds
    if scheduled:
        pass
    elif duration is None or last is None:
        out.append(Result("no break in the last seconds", WARN, "sessionDuration or selectionLastSeconds not in the config"))
    else:
        problems, notes = [], []
        for k, (s, _) in enumerate(breaks):
            left = duration - _foraging_time(s, breaks[:k])
            if left <= 0:
                problems.append(f"break {k + 1} started with {left:.2f} s left")
            elif left <= last:        # the switch counted earlier, the start waited for a harvest bout to end: not decidable from the log
                notes.append(f"break {k + 1} started with {left:.2f} s left (selectionLastSeconds {last}; a bout may have delayed it)")
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
        size = ctx.pool_size or cfg.get("selectionPoolSets")
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
            ctx.pool_tolerance, ctx.pool_size = float(pool.get("tieTolerance", selection.TIE_TOLERANCE)), len(pool.get("sets") or []) or None
    except (FileNotFoundError, KeyError, ValueError, OSError) as err:
        ctx.world_note = f"{type(err).__name__}: {err}"[:300]
    return ctx


def run_checks(ctx):
    if ctx.unsupported:
        return [Result("format", FAIL, "unsupported log format: " + ctx.unsupported)]
    out = []
    for check in CHECKS:
        out.extend(check(ctx))
    if ctx.truncated:
        out.append(Result("files complete", WARN, f"{', '.join(ctx.truncated)} ended mid-line; the last line was dropped"))
    return out


def validate_session(folder):
    """The Results of one session folder; a folder that cannot be read is one FAIL (an old column layout says so)."""
    try:
        ctx = load_ctx(folder)
    except ValueError as err:
        old = "header" in str(err)
        return [Result("load", FAIL, ("unsupported log format: " if old else "unreadable: ") + str(err)[:300])]
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
