"""validate_run.py: a golden session passes every check and each injected fault fails exactly the check that is meant to see it; the real browser runs of 2026-11-13
(scripts/fixtures/runs/) pass; a run folder, JSON output and the old formats do not crash."""

import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest

import replay
import rundata
import validate_run as v
import world as world_mod
from validate_run import FAIL, PASS, SKIP, WARN, Ctx

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "runs"

CONFIG = {"sessionDuration": 20.0, "rankingEvery": 1, "rankingCooldown": 5.0, "rankingMinBushes": 1, "rankingLastSeconds": 3.0, "rankingBonusPerPair": 4,
          "rankingPoolSets": 12, "isPractice": False, "rankingSettleDepth": 0}
FRUIT_REWARD = np.array([[5, 6, 7, 8, 9], [1, 2, 3, 4, 5], [2, 2, 2, 2, 2]])        # three world bushes (ids 0-2); the sets' bushes are ids 3-5
CENTRES = np.array([[-40.0, 0.0], [40.0, 0.0]])                                      # two tiles: x < 0 and x > 0
SET_BUSHES = [{"id": 3, "x": 0, "z": 16, "radius": 2, "shape": 0.1}, {"id": 4, "x": 5, "z": 16, "radius": 2, "shape": 0.2}, {"id": 5, "x": 10, "z": 16, "radius": 2, "shape": 0.3}]


def _x(t):
    """Tile 0 until t = 2, walks to tile 1 by t = 3, back to tile 0 over 9 to 10, to tile 1 over 17 to 18."""
    return float(np.interp(t, [0, 2, 3, 9, 10, 17, 18, 30], [-10, -10, 10, 10, -10, -10, 10, 10]))


def make_traj(end=26.0):
    times = np.round(np.arange(0.1, end + 1e-9, 0.1), 3)
    return np.array([[t, _x(t), 0.0, 0.0, 0.0, 0] for t in times])


def event(t, kind, **kw):
    payload = kw.pop("payload", {})
    return {"t": t, "real": t, "type": kind, "tree_id": kw.get("tree_id", -1), "k": kw.get("k", -1), "reward": kw.get("reward", math.nan),
            "running_total": kw.get("running_total", math.nan), "payload": payload}


def fruit(t, tree, k, reward, total):
    return event(t, "fruit", tree_id=tree, k=k, reward=float(reward), running_total=float(total))


def break_events(n, start, set_end, end, correct, points):
    ev = [event(start, "rank_break_start", payload={"break": n, "pool_index": n - 1, "sets": 1, "switches": 1, "tile": 0 if n == 2 else 1}),
          event(start + 0.3, "rank_set", payload={"break": n, "bushes": SET_BUSHES}),
          event(start + 0.6, "rank_set_start", payload={"break": n, "set": n - 1}), event(start + 0.6, "rank_go", payload={"break": n}),
          fruit(start + 1.0, 3, 0, 0, 0)]       # total patched by `golden`
    ev += [event(set_end, "rank_set_end", payload={"break": n, "correct_pairs": correct, "total_pairs": 3, "points": points, "picked": [3, 4, 5]}),
           event(end, "rank_break_end", payload={"break": n})]
    return ev


def set_row(index, bushes_ranks, correct, points):
    values = {3: 3.0, 4: 2.0, 5: 1.0}
    return {"seq": index, "set_index": index, "pool_index": index, "start_x": 0.0, "start_z": 0.0, "timed_out": 0, "response_time": 2.0, "first_harvest_time": 0.5,
            "points": points, "paused_seconds": 0.0, "set_size": 3, "correct_pairs": correct, "total_pairs": 3,
            "bushes": [{"id": i, "rank": r, "value": values[i], "slot": s} for s, (i, r) in enumerate(bushes_ranks)]}


def golden(second=(13.0, 15.5, 16.0)):
    """A session of 20 foraging seconds with two breaks (3 s each; the second at `second` = start, last set's end, end), two ranking sets (3/3 and 2/3 pairs), 16 + 20 points."""
    events = [event(0.0, "session_start"), event(0.5, "pause", payload={"reason": "pointer"}), event(0.6, "resume"),
              fruit(1.0, 0, 0, 5, 5), fruit(1.5, 0, 1, 6, 11), fruit(3.5, 1, 0, 1, 12)]
    events += break_events(1, 4.0, 6.5, 7.0, 3, 12) + [fruit(8.0, 1, 1, 2, 14)]
    events += break_events(2, *second, 2, 8) + [fruit(20.0, 2, 0, 2, 16), event(26.0, "session_end", payload={"foraging_points": 16, "ranking_points": 20})]
    events.sort(key=lambda e: e["t"])
    for e in events:                                # a set bush's fruit keeps the running total
        if e["type"] == "fruit" and e["tree_id"] == 3:
            e["running_total"] = max(f["running_total"] for f in events if f["type"] == "fruit" and f["t"] < e["t"] and f["tree_id"] != 3)
    reseq(events)
    traj = make_traj()
    row = {"name": "T", "config": dict(CONFIG), "completed": True, "foraging_points": 16, "ranking_points": 20, "frame_stats": {"count": len(traj)},
           "world_file": "T.world", "world_sha256": "0" * 64}
    sets = [set_row(0, [(3, 1), (4, 2), (5, 3)], 3, 12), set_row(1, [(4, 1), (3, 2), (5, 3)], 2, 8)]
    return Ctx(row=row, traj=traj, events=events, sets=sets, fruit_reward=FRUIT_REWARD, tile_centres=CENTRES, world_found=True, world_note="synthetic", pool_size=12)


def reseq(events):
    for i, e in enumerate(events):
        e["seq"] = i


def by_name(results):
    return {r.name: r for r in results}


def failing(ctx):
    return {r.name for r in v.run_checks(ctx) if r.status == FAIL}


def find(events, kind, nth=0):
    return [e for e in events if e["type"] == kind][nth]


def retotal(ctx):
    """Make every fruit's running_total and the session's foraging_points the cumulative sum of the rewards."""
    total = 0.0
    for e in ctx.events:
        if e["type"] == "fruit":
            total += e["reward"]
            e["running_total"] = total
    set_points(ctx, foraging=total)


def set_points(ctx, foraging=None, ranking=None):
    """Set the session row's and the session_end payload's totals together."""
    end = find(ctx.events, "session_end")["payload"]
    if foraging is not None:
        ctx.row["foraging_points"] = end["foraging_points"] = foraging
    if ranking is not None:
        ctx.row["ranking_points"] = end["ranking_points"] = ranking


# --- the golden session -------------------------------------------------------------------------------------------------------------------

def test_the_golden_session_passes_every_check():
    results = v.run_checks(golden())
    assert [r for r in results if r.status in (FAIL, WARN)] == []
    assert by_name(results)["foraging time = sessionDuration"].status == PASS and by_name(results)["break cooldown"].status == PASS


def test_a_session_without_ranking_skips_the_ranking_checks():
    ctx = golden()
    ctx.row["config"]["rankingEvery"] = 0
    ctx.events = [e for e in ctx.events if not e["type"].startswith("rank_") and e["tree_id"] != 3]
    ctx.sets = None
    set_points(ctx, ranking=0)
    reseq(ctx.events)
    results = by_name(v.run_checks(ctx))
    assert results["break rules"].status == SKIP and results["ranking pair scores"].status == SKIP and results["rank_break events balanced"].status == SKIP
    assert not [r for r in results.values() if r.status in (FAIL, WARN)]


def test_an_old_interlude_session_is_noted_not_failed():
    ctx = golden()
    ctx.row["config"].update(isInterlude=True, rankingEvery=0)
    ctx.events = [e for e in ctx.events if not e["type"].startswith("rank_")]
    ctx.sets = [set_row(0, [(3, 1), (4, 2), (5, 3)], 3, 0)]            # an Interlude's trial row
    reseq(ctx.events)
    results = v.run_checks(ctx)
    assert [r.status for r in results if r.name == "format"] == [WARN] and not [r for r in results if r.status == FAIL]


# --- one injected fault, one failing check ------------------------------------------------------------------------------------------------

def test_a_wrong_running_total_fails_the_running_total_check():
    ctx = golden()
    find(ctx.events, "fruit", 5)["running_total"] = 17.0
    assert failing(ctx) == {"foraging_points = running_total"}


def test_a_wrong_fruit_reward_fails_the_world_reward_check():
    ctx = golden()
    fruits = [e for e in ctx.events if e["type"] == "fruit" and e["tree_id"] != 3]
    fruits[3]["reward"] = 3.0                                                 # bush 1, fruit 1 pays 2
    retotal(ctx)
    assert failing(ctx) == {"fruit rewards = world's pre-drawn rewards"}


def test_a_wrong_correct_pairs_fails_the_pair_score_check():
    ctx = golden()
    ctx.sets[0]["correct_pairs"], ctx.sets[0]["points"] = 2, 8                # the picks were 3 of 3 pairs
    find(ctx.events, "rank_set_end")["payload"].update(correct_pairs=2, points=8)
    set_points(ctx, ranking=16)
    assert failing(ctx) == {"ranking pair scores"}


def test_wrong_points_fail_the_points_check():
    ctx = golden()
    ctx.sets[0]["points"] = 13                                                # 3 pairs x 4 = 12
    find(ctx.events, "rank_set_end")["payload"]["points"] = 13
    set_points(ctx, ranking=21)
    assert failing(ctx) == {"ranking points"}


def test_a_set_end_event_that_differs_from_the_row_fails():
    ctx = golden()
    find(ctx.events, "rank_set_end", 1)["payload"]["total_pairs"] = 2
    assert failing(ctx) == {"rank_set_end = row"}


def test_ranking_points_must_equal_the_sum_of_the_sets():
    ctx = golden()
    ctx.row["ranking_points"] = 19
    assert failing(ctx) == {"ranking_points = sum of set points", "session_end payload = session row"}


def test_a_practice_session_pays_no_points():
    ctx = golden()
    ctx.row["config"]["isPractice"] = True
    assert failing(ctx) == {"ranking points"}


def test_a_missing_rank_set_end_fails_the_set_events_check():
    ctx = golden()
    ctx.events.remove(find(ctx.events, "rank_set_end", 1))
    reseq(ctx.events)
    assert failing(ctx) == {"ranking set events"}


def test_unbalanced_break_events_fail_the_balance_check():
    ctx = golden()
    ctx.events.insert(find(ctx.events, "rank_break_start").get("seq") + 1, event(4.0, "rank_break_start", payload={"break": 1}))
    reseq(ctx.events)
    assert failing(ctx) == {"rank_break events balanced"}


def test_an_event_seq_gap_fails_the_seq_check():
    ctx = golden()
    ctx.events.remove(find(ctx.events, "pause"))
    assert failing(ctx) == {"events seq contiguous"}


def test_time_going_back_fails_the_clock_check_except_at_a_resume():
    ctx = golden()
    find(ctx.events, "resume")["t"] = 0.2
    assert failing(ctx) == {"events t non-decreasing"}
    ctx = golden()
    ctx.events.insert(7, event(0.1, "session_resume"))
    reseq(ctx.events)
    assert "events t non-decreasing" not in failing(ctx)


def test_a_break_inside_the_cooldown_fails_the_cooldown_check():
    assert failing(golden(second=(10.5, 13.0, 13.5))) == {"break cooldown"}      # 3.5 foraging seconds after the first break ended, cooldown 5


def test_movement_during_a_break_fails_the_stillness_check():
    ctx = golden()
    ctx.traj[(ctx.traj[:, 0] > 5.0) & (ctx.traj[:, 0] <= 5.5), 1] += 2.0
    assert failing(ctx) == {"player still during a break"}


def test_walking_after_the_last_set_is_allowed_and_a_little_momentum_at_the_start_too():
    ctx = golden()
    ctx.traj[(ctx.traj[:, 0] > 6.6) & (ctx.traj[:, 0] <= 7.0), 1] += 2.0         # after the set's end: the player is free
    ctx.traj[(ctx.traj[:, 0] > 4.0) & (ctx.traj[:, 0] <= 4.1), 1] += 0.1         # one frame of momentum
    assert failing(ctx) == set()


def test_a_world_fruit_during_a_break_fails_the_break_fruit_check():
    ctx = golden()
    ctx.events.append(fruit(5.5, 0, 2, 7, 19))
    ctx.events.sort(key=lambda e: e["t"])
    reseq(ctx.events)
    retotal(ctx)
    assert failing(ctx) == {"no foraging fruit during a break"}


def test_a_break_without_a_tile_change_fails():
    ctx = golden()
    ctx.traj[:, 1] = np.where(ctx.traj[:, 0] < 9.0, -10.0, ctx.traj[:, 1])       # the player never leaves the first tile before break 1
    ctx.traj[(ctx.traj[:, 0] > 7.0) & (ctx.traj[:, 0] < 17.0), 1] = 10.0
    assert "break after a patch switch" in failing(ctx)


def test_a_break_before_enough_bushes_were_harvested_fails():
    ctx = golden()
    ctx.row["config"]["rankingMinBushes"] = 3
    assert failing(ctx) == {"bushes before the first break"}


def test_a_break_in_the_last_seconds_is_noticed():
    ctx = golden()
    ctx.row["config"]["sessionDuration"] = 20.0
    ctx.row["config"]["rankingLastSeconds"] = 11.0                               # break 2 starts with 10 s left
    results = by_name(v.run_checks(ctx))
    assert results["no break in the last seconds"].status == WARN                # a harvest bout may have delayed the start: undecidable
    ctx.row["config"]["sessionDuration"] = 10.0
    assert "no break in the last seconds" in failing(ctx) or "foraging time = sessionDuration" in failing(ctx)


def test_the_foraging_time_must_be_the_session_duration_and_a_reduced_run_only_warns():
    ctx = golden()
    ctx.row["config"]["sessionDuration"] = 30.0
    ctx.row["config"]["rankingLastSeconds"] = 3.0
    assert failing(ctx) == {"foraging time = sessionDuration"}
    ctx.events.insert(1, event(0.0, "run_modes", payload={"short": 0.3}))
    reseq(ctx.events)
    results = by_name(v.run_checks(ctx))
    assert results["foraging time = sessionDuration"].status == WARN


def test_the_pool_must_be_played_in_order_wrapping_at_its_size():
    ctx = golden()
    ctx.sets[1]["pool_index"] = 5
    assert failing(ctx) == {"pool order"}
    ctx = golden()
    ctx.sets[0]["pool_index"], ctx.sets[1]["pool_index"], ctx.pool_size = 1, 0, 2
    assert "pool order" in failing(ctx)                                         # starts at 1 without a resume
    ctx.events.insert(1, event(0.0, "session_resume"))
    reseq(ctx.events)
    assert "pool order" not in failing(ctx)                                     # a resumed session continues the pool anywhere, wrapping


def test_a_missing_world_warns_where_it_is_needed():
    ctx = golden()
    ctx.fruit_reward = ctx.tile_centres = None
    ctx.world_found, ctx.world_note = False, "no such file"
    results = by_name(v.run_checks(ctx))
    assert results["fruit rewards = world's pre-drawn rewards"].status == WARN and results["break after a patch switch"].status == WARN
    assert results["world file hash"].status == WARN and not [r for r in results.values() if r.status == FAIL]


def test_a_trajectory_with_the_wrong_frame_count_fails():
    ctx = golden()
    ctx.row["frame_stats"]["count"] += 3
    assert failing(ctx) == {"trajectory frame count"}


# --- loading from disk, the run folder, the command line ---------------------------------------------------------------------------------

def test_a_written_session_loads_and_validates(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("replay.DATA_DIR", tmp_path)
    monkeypatch.setattr("replay.WORLD_DIR", tmp_path / "none")
    wfile = tmp_path / "FIX_T0_seed1.world"
    world_mod.export_unity(world_mod.make_world("FIX_T0", 1), wfile)
    sha = replay._sha256(wfile)
    (tmp_path / "_worlds").mkdir()
    (tmp_path / "_worlds" / f"{sha[:8]}_FIX_T0_seed1.world").write_bytes(wfile.read_bytes())
    row = {"name": "FIX_T0", "config": {"sessionDuration": 1.0}, "completed": True, "foraging_points": 0, "world_file": "FIX_T0_seed1.world", "world_sha256": sha,
           "frame_stats": {"count": 2}}
    traj = np.array([[0.01, 0.0, 0.0, 0.0, 0.0, 0], [0.02, 0.0, 0.0, 0.0, 0.0, 0]])
    events = [{"t": 0.01, "type": "session_start"}, {"t": 0.02, "type": "session_end", "payload": {"foraging_points": 0}}]
    folder = rundata.write_session(tmp_path, "run1", 0, row, traj, events)
    ctx = v.load_ctx(folder)
    assert ctx.world_found and ctx.fruit_reward is not None
    assert not [r for r in v.validate_session(folder) if r.status == FAIL]
    assert v.session_folders(tmp_path / "run1") == [folder]
    assert v.main([str(folder)]) == 0
    assert "PASS" in capsys.readouterr().out
    assert v.main([str(tmp_path / "run1"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["FAIL"] == 0


def test_an_unreadable_session_is_one_fail_and_an_old_header_a_warn(tmp_path):
    folder = tmp_path / "run" / "00"
    folder.mkdir(parents=True)
    (folder / "session.json").write_text(json.dumps({"config": {}, "world_file": "x.world", "world_sha256": "0" * 64}))
    (folder / "events.csv").write_text("a,b\n0,0.0\n")
    (folder / "trajectory.csv").write_text("seq,t,x,z,yaw,pitch,keys\n")
    assert [r.status for r in v.validate_session(folder)] == [WARN]


# --- the real browser runs of 2026-11-13 --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("run", ["0ef0ba46", "d0a5fb74"])
def test_the_real_browser_runs_pass(run):
    results = v.validate_session(FIXTURES / run / "00")
    assert [r for r in results if r.status == FAIL] == []
    names = by_name(results)
    assert names["world file hash"].status == PASS and names["foraging_points = running_total"].status == PASS
    assert names["ranking pair scores"].status == PASS and names["break after a patch switch"].status == PASS


def test_a_fault_in_a_real_run_is_found(tmp_path):
    import shutil
    shutil.copytree(FIXTURES / "d0a5fb74", tmp_path / "run")
    shutil.copytree(FIXTURES / "_worlds", tmp_path / "_worlds")
    path = tmp_path / "run" / "00" / "session.json"
    row = json.loads(path.read_text())
    row["foraging_points"] += 1
    path.write_text(json.dumps(row))
    assert v.main([str(tmp_path / "run")]) == 1
