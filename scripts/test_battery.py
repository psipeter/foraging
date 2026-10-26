import pytest

import analysis
import battery
import results
from agents import REGISTRY
from battery import Battery, run_battery, session_readout

TINY = Battery("tiny", {"P": 20, "S1": 30}, (0.0, 0.5, 1.0), seeds=(0, 1), interlude_trials=6)


def test_the_standard_battery_is_the_four_sessions_with_checkpoints_as_fractions_of_each():
    b = battery.BATTERIES["standard"]
    assert b.sessions == {"S1": 90, "S2": 120, "S3": 120, "S4": 150}
    assert b.checkpoints("S1") == [0.0, 9.0, 18.0, 31.5, 45.0, 67.5, 90.0]
    assert b.checkpoints("S4") == [0.0, 15.0, 30.0, 52.5, 75.0, 112.5, 150.0]
    assert b.overrides("S3") == {"session_duration": 120, "interlude_trial_count": 50}
    assert (b.n_samples, b.interlude_mode, len(b.seeds)) == (1, "random", 10)          # one pick per trial, like a participant


def test_the_long_battery_has_longer_sessions_and_the_same_design_otherwise():
    long, standard = battery.BATTERIES["long"], battery.BATTERIES["standard"]
    assert long.sessions == {"S1": 120, "S2": 120, "S3": 180, "S4": 180}
    assert long.checkpoint_fractions == standard.checkpoint_fractions and long.checkpoints("S3") == [0.0, 18.0, 36.0, 63.0, 90.0, 135.0, 180.0]
    assert (long.n_samples, long.interlude_mode, long.interlude_trials, long.seeds) == (standard.n_samples, standard.interlude_mode, standard.interlude_trials, standard.seeds)


def test_every_population_builds_round_trips_and_fits_a_figure():
    from agents import build_agent
    assert {n: len(m()) for n, m in battery.POPULATIONS.items()} == {"main": 3, "scan-alpha": 6, "scan-length": 6, "scan-centers": 6, "scan-prior": 6, "scan-window": 4, "choice-noise": 7, "knowledge": 5, "explore-posterior": 7, "delta-noise": 5, "delta-bonus": 7, "learners": 5, "explore-noise": 6, "explore-bonus": 8, "scan-gp-kernel": 7, "scan-gp-prior": 7, "scan-ucb-beta": 7, "scan-ucb-temp": 6, "scan-hybrid-beta": 7, "scan-softmax-temp": 7, "scan-horizon-temp": 7, "scan-curious-beta": 7, "scan-curious-high": 7, "scan-delta-horizon-temp": 7, "scan-delta-curious-beta": 7, "scan-delta-peek-margin": 7, "scan-peek": 7, "scan-ars-radius": 6, "scan-ars-growth": 6, "critic-ladder": 8, "scan-matched-noise": 7, "scan-replay-epochs": 8, "scan-replay-policy": 8}
    for name, make in battery.POPULATIONS.items():
        pop = make()
        assert "nearest" in pop and len(pop) <= 8                                          # the floor is in every figure; the palette holds 8
        assert len({f().spec_hash() for f in pop.values()}) == len(pop)                    # no two aliases are the same agent
        for factory in pop.values():
            spec = factory().spec()
            assert build_agent(spec).spec() == spec


def test_the_standard_agents_share_one_actor_and_see_through_the_view_cone():
    main = battery.POPULATIONS["main"]()
    specs = {name: factory().spec() for name, factory in main.items()}
    assert specs["oracle"]["actor"] == specs["learner"]["actor"] == {"type": "UtilityActor", "utility": "rate", "max_walk_time": 15,
                                                                      "choice": {"type": "Argmax"}}
    assert specs["nearest"]["actor"]["utility"] == "nearest" and specs["nearest"]["actor"]["max_walk_time"] is None
    assert {s["memory"]["type"] for s in specs.values()} == {"FullMemory"}                  # the cone is the default for all three
    assert specs["oracle"]["critic"]["type"] == "OracleCritic" and specs["learner"]["critic"]["type"] == "DeltaRuleCritic"
    knowledge = {name: factory().spec() for name, factory in battery.POPULATIONS["knowledge"]().items()}
    assert knowledge["oracle_fullmap"]["memory"]["type"] == knowledge["learner_fullmap"]["memory"]["type"] == "FullKnowledge"
    assert knowledge["oracle_fullmap"]["actor"] == specs["oracle"]["actor"]
    prior = {n: f().spec()["critic"]["prior"] for n, f in battery.POPULATIONS["scan-prior"]().items() if n.startswith("learner")}
    assert prior["learner"] == {"type": "ConstantPrior", "level": 0.1} and prior["learner_meanprior"] == {"type": "NeutralPrior", "initial": 1}
    assert prior["learner_prior1"] == {"type": "ConstantPrior", "level": 1} and prior["learner_prior2"] == {"type": "ConstantPrior", "level": 2}
    window = {n: f().spec() for n, f in battery.POPULATIONS["scan-window"]().items()}
    assert window["learner_window15"]["actor"]["max_walk_time"] == 15 and window["learner_window60"]["actor"]["max_walk_time"] == 60
    assert window["learner_window15"] == specs["learner"]                                    # the 15 s learner is the standard learner
    noise = battery.POPULATIONS["choice-noise"]()
    assert noise["learner_softmax0.3"]().spec()["actor"]["choice"] == {"type": "Softmax", "temperature": 0.3}
    for scan, key, levels in ((battery.POPULATIONS["scan-alpha"](), "alpha", [0.1, 0.3, 0.5, 0.8]),
                              (battery.POPULATIONS["scan-length"](), "features", [0.1, 0.3, 0.5, 0.7]),
                              (battery.POPULATIONS["scan-centers"](), "features", [4, 8, 12, 16])):
        learners = [f().spec()["critic"] for n, f in scan.items() if n.startswith("learner")]
        got = [c[key] if key == "alpha" else c[key]["length_scale" if levels[0] < 1 else "n_centers"] for c in learners]
        assert got == levels and all(f().spec()["actor"] == specs["oracle"]["actor"] for f in scan.values() if f is not scan["nearest"])
    assert REGISTRY["oracle"]().spec_hash() == main["oracle"]().spec_hash() and REGISTRY["learner"]().spec_hash() == main["learner"]().spec_hash()


def test_resolve_takes_population_names_then_registry_names():
    chosen = battery.resolve(["nearest", "oracle", "delta_rate_10"], "main")
    assert list(chosen) == ["nearest", "oracle", "delta_rate_10"]
    assert len(battery.resolve(None, "main")) == 3
    with pytest.raises(KeyError):
        battery.resolve(["nonexistent"], "main")


@pytest.mark.slow
def test_a_battery_run_records_every_session_with_its_checkpoints_and_reuses_them(tmp_path):
    agents = battery.resolve(["nearest", "learner"], "main")
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


def test_the_command_line_lists_and_runs(tmp_path, capsys, monkeypatch):
    battery.main(["list"])
    out = capsys.readouterr().out
    assert "battery standard" in out and "battery long" in out and "population main: 3 agents" in out
    assert battery.DEFAULT_BATTERY == "long"
    monkeypatch.setitem(battery.BATTERIES, battery.DEFAULT_BATTERY, TINY)
    battery.main(["run", "--agents", "nearest,learner", "--tag", "cli", "--seeds", "0-1", "--db", str(tmp_path / "r.sqlite")])
    out = capsys.readouterr().out
    assert "P: total reward" in out and "S1: Interlude accuracy at the end" in out and "learner" in out


@pytest.mark.slow
def test_plot_battery_saves_the_three_figures_of_a_group_with_one_panel_per_session(tmp_path, monkeypatch):
    agents = battery.resolve(["nearest", "learner"], "main")
    monkeypatch.setitem(battery.POPULATIONS, "tiny", lambda: agents)
    with results.Store(tmp_path / "r.sqlite") as store:
        run_battery(agents, TINY, "pt", store=store, progress=None)
        paths = battery.plot_battery(store, "pt", TINY, population="tiny", out_dir=tmp_path)
    assert [p.name for p in paths] == ["pt_tiny_reward.png", "pt_tiny_advantage.png", "pt_tiny_interlude.png"]
    assert all(p.exists() and p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" for p in paths)
    monkeypatch.setitem(battery.BATTERIES, battery.DEFAULT_BATTERY, TINY)
    battery.main(["plot", "--tag", "pt", "--population", "tiny", "--kinds", "interlude", "--out", str(tmp_path / "cli"), "--db", str(tmp_path / "r.sqlite")])
    assert (tmp_path / "cli" / "pt_tiny_interlude.png").exists()


@pytest.mark.slow
def test_scores_summarize_each_agent_in_each_session(tmp_path):
    agents = battery.resolve(["nearest", "oracle", "learner"], "main")
    with results.Store(tmp_path / "r.sqlite") as store:
        run_battery(agents, TINY, "sc", store=store, progress=None)
        rows = battery.scores(store, "sc", TINY, "main")
    assert [(r["session"], r["agent"]) for r in rows] == [(s, a) for s in TINY.sessions for a in ("nearest", "oracle", "learner")]
    for r in rows:
        assert r["quality"] + r["efficiency"] == pytest.approx(r["lead"])                          # the lead is exactly its two parts
        assert r["total"] == pytest.approx(r["fruits"] * r["per_fruit"])
        if r["agent"] == "nearest":
            assert r["lead"] == 0.0 and r["quality"] == 0.0 and r["efficiency"] == 0.0
        if r["agent"] == "oracle":
            assert r["accuracy"] == 1.0 and r["auc"] == pytest.approx(1.0) and r["t80"] == 0.0
        assert -1.0 <= r["auc"] <= 1.0 and (r["t80"] != r["t80"] or 0.0 <= r["t80"] <= 1.0)
        assert "gap" not in r
    text = battery.format_scores(rows)
    assert "P:" in text and "S1:" in text and "learner" in text and "t80" in text and "quality" in text
