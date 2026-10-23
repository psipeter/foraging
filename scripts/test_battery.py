import pytest

import analysis
import battery
import results
from agents import REGISTRY, PlannerAgent
from battery import Battery, run_battery, session_readout

TINY = Battery("tiny", {"P": 20, "S1": 30}, (0.0, 0.5, 1.0), seeds=(0, 1), interlude_trials=6)


def test_the_standard_battery_is_the_four_sessions_with_checkpoints_as_fractions_of_each():
    b = battery.BATTERIES["standard"]
    assert b.sessions == {"S1": 90, "S2": 120, "S3": 120, "S4": 150}
    assert b.checkpoints("S1") == [0.0, 9.0, 18.0, 31.5, 45.0, 67.5, 90.0]
    assert b.checkpoints("S4") == [0.0, 15.0, 30.0, 52.5, 75.0, 112.5, 150.0]
    assert b.overrides("S3") == {"session_duration": 120, "interlude_trial_count": 50}
    assert (b.n_samples, b.interlude_mode, len(b.seeds)) == (1, "random", 10)          # one pick per trial, like a participant


def test_the_main_population_is_24_distinct_agents_that_build_and_round_trip():
    from agents import build_agent
    pop = battery.main_population()
    assert len(pop) == 24 and "nearest" in pop
    hashes = {name: factory().spec_hash() for name, factory in pop.items()}
    assert len(set(hashes.values())) == 24                                              # no two aliases are the same agent
    for name, factory in pop.items():
        spec = factory().spec()
        assert build_agent(spec).spec() == spec
    ref = pop["learner_rate_w15"]().spec()
    assert ref["critic"]["type"] == "DeltaRuleCritic" and ref["memory"]["type"] == "FullMemory" and ref["actor"]["max_walk_time"] == 15
    assert pop["oracle_rate_w15"]().spec()["memory"]["type"] == "FullKnowledge"
    assert pop["oracle_cone_rate_w15"]().spec()["critic"]["type"] == "OracleCritic" and pop["oracle_cone_rate_w15"]().spec()["memory"]["type"] == "FullMemory"
    assert pop["learner_fullmap_rate_w15"]().spec()["memory"]["type"] == "FullKnowledge"
    assert pop["learner_softmax0.3"]().spec()["actor"]["choice"] == {"type": "Softmax", "temperature": 0.3}
    assert pop["learner_joint"]().spec()["critic"]["features"]["additive"] is False


def test_resolve_takes_population_names_then_registry_names():
    chosen = battery.resolve(["nearest", "learner_alpha0.2", "delta_rate_10"], "main")
    assert list(chosen) == ["nearest", "learner_alpha0.2", "delta_rate_10"]
    assert len(battery.resolve(None, "main")) == 24
    with pytest.raises(KeyError):
        battery.resolve(["nonexistent"], "main")


@pytest.mark.slow
def test_a_battery_run_records_every_session_with_its_checkpoints_and_reuses_them(tmp_path):
    agents = battery.resolve(["nearest", "learner_rate_w15"], "main")
    with results.Store(tmp_path / "r.sqlite") as store:
        reports = run_battery(agents, TINY, "t", store=store, progress=None)
        assert list(reports) == ["P", "S1"] and all(len(r) == 2 and r[0].n_computed == 2 for r in reports.values())
        sel = analysis.select(store, tag="t/S1", kind="interlude")
        assert sel.env["session"] == "S1" and sel.env["overrides"] == {"session_duration": 30, "interlude_trial_count": 6}
        assert sel.env["checkpoints"] == [0.0, 15.0, 30.0] and sel.env["n_samples"] == 1 and sel.env["interlude_mode"] == "random"
        curves = analysis.checkpoint_curve(store, sel)
        assert list(curves.t) == [0.0, 15.0, 30.0]
        row = reports["S1"][1].rows[0]
        assert row["interlude_trials"] == 6 and row["interlude_accuracy"] * 6 == pytest.approx(round(row["interlude_accuracy"] * 6))   # one pick per trial
        again = run_battery(agents, TINY, "t2", store=store, progress=None)
        assert all(r.n_computed == 0 and r.n_reused == 2 for rs in again.values() for r in rs)
        text = session_readout(store, "t", TINY, {r.agent_id: "nearest-alias" for r in reports["S1"][:1]})
        assert "P: total reward" in text and "S1: Interlude accuracy" in text and "nearest-alias" in text


def test_an_agent_that_plans_for_the_deadline_is_refused_before_anything_runs(tmp_path):
    with results.Store(tmp_path / "r.sqlite") as store:
        with pytest.raises(ValueError, match="cannot be checkpointed"):
            run_battery({"planner": lambda: PlannerAgent("beam")}, TINY, "t", store=store, progress=None)
        assert store.select("SELECT COUNT(*) AS n FROM runs")[0]["n"] == 0


def test_the_command_line_lists_and_runs(tmp_path, capsys, monkeypatch):
    battery.main(["list"])
    out = capsys.readouterr().out
    assert "battery standard" in out and "population main: 24 agents" in out
    monkeypatch.setitem(battery.BATTERIES, "standard", TINY)
    battery.main(["run", "--agents", "nearest,learner_rate_w15", "--tag", "cli", "--seeds", "0-1", "--db", str(tmp_path / "r.sqlite")])
    out = capsys.readouterr().out
    assert "P: total reward" in out and "S1: Interlude accuracy at the end" in out and "learner_rate_w15" in out


@pytest.mark.slow
def test_plot_battery_saves_the_three_figures_of_a_group_with_one_panel_per_session(tmp_path, monkeypatch):
    monkeypatch.setitem(battery.GROUPS, "tiny", ["nearest", "learner_rate_w15"])
    agents = battery.resolve(["nearest", "learner_rate_w15"], "main")
    with results.Store(tmp_path / "r.sqlite") as store:
        run_battery(agents, TINY, "pt", store=store, progress=None)
        paths = battery.plot_battery(store, "pt", TINY, groups=["tiny"], out_dir=tmp_path)
    assert [p.name for p in paths] == ["pt_tiny_cumulative.png", "pt_tiny_advantage.png", "pt_tiny_learning.png"]
    assert all(p.exists() and p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" for p in paths)
    monkeypatch.setitem(battery.BATTERIES, "standard", TINY)
    battery.main(["plot", "--tag", "pt", "--groups", "tiny", "--kinds", "learning", "--out", str(tmp_path / "cli"), "--db", str(tmp_path / "r.sqlite")])
    assert (tmp_path / "cli" / "pt_tiny_learning.png").exists()
