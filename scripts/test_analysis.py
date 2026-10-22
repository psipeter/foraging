import numpy as np
import pytest

import analysis
import fingerprint
from agents import ComposedAgent, DeltaRuleCritic, FullKnowledge, FullMemory, OracleCritic, REGISTRY, RBFFeatures, Softmax, UtilityActor
from results import Store, record_run


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "r.sqlite") as s:
        yield s


def delta(alpha=0.5, utility="rate", features=None, choice=None):
    return ComposedAgent(UtilityActor(utility, 10.0, choice), DeltaRuleCritic(features, None, alpha), FullMemory())


def add(store, agent, totals, tag="t", seeds=None, overrides=None, code=None, by_type=None, accuracy=None):
    """Put a run with these totals (one per seed) straight into the database."""
    spec = agent.spec() if hasattr(agent, "spec") else agent
    agent_id = store.record_agent(spec)
    env_id = store.record_environment(fingerprint.environment("P", overrides or {"session_duration": 20}))
    code_id = store.record_code(code or fingerprint.code_version())
    seeds = list(range(len(totals))) if seeds is None else seeds
    with store.conn:
        run_id = store.conn.execute("INSERT INTO runs VALUES (NULL, ?, ?, ?, ?, NULL, ?, ?, ?, 0, 'now')",
                                    (agent_id, env_id, code_id, tag, ",".join(map(str, seeds)), len(seeds), len(seeds))).lastrowid
    for seed, total in zip(seeds, totals):
        values = {"total": float(total)}
        if accuracy is not None:
            values["interlude_accuracy"] = accuracy
        e = store.add_episode(agent_id, env_id, code_id, seed, run_id, values, by_type)
        with store.conn:
            store.conn.execute("INSERT INTO run_episodes VALUES (?, ?)", (run_id, e))
    return agent_id


NEAREST = [10, 12, 11, 13]


# --- selection -----------------------------------------------------------------------------------------------------

def test_a_selection_is_one_environment_and_the_current_engine_by_default(store):
    a = add(store, REGISTRY["nearest"](), NEAREST)
    old = {**fingerprint.code_version(), "engine_hash": "0" * 12}
    add(store, delta(0.2), [1, 2, 3, 4], code=old)                                    # recorded on other engine code
    sel = analysis.select(store, tag="t")
    assert list(sel.agents) == [a] and sel.env["session"] == "P" and sel.seeds(a) == [0, 1, 2, 3]
    anyone = analysis.select(store, tag="t", engine="any")
    assert len(anyone.agents) == 2 and any("stale" in n for n in anyone.notes)
    only_old = analysis.select(store, engine="0" * 12)
    assert len(only_old.agents) == 1 and only_old.code["engine_hash"] == "0" * 12
    with pytest.raises(analysis.SelectionError):
        analysis.select(store, tag="missing")


def test_a_selection_refuses_to_mix_environments_or_code_versions(store):
    add(store, REGISTRY["nearest"](), NEAREST)
    add(store, delta(), NEAREST, overrides={"session_duration": 30})
    with pytest.raises(analysis.SelectionError, match="2 environments"):
        analysis.select(store)
    assert len(analysis.select(store, overrides={"session_duration": 30}).agents) == 1
    other = {**fingerprint.code_version(), "agents_hash": "f" * 12}
    add(store, REGISTRY["nearest"](), NEAREST, code=other, tag="again")
    with pytest.raises(analysis.SelectionError, match="more than one code version"):
        analysis.select(store, overrides={"session_duration": 20}, engine="any")


def test_agents_are_chosen_by_name_id_or_spec_and_notes_report_stale_agent_code(store):
    a = add(store, REGISTRY["nearest"](), NEAREST)
    add(store, delta(), [1, 2, 3, 4], code={**fingerprint.code_version(), "agents_hash": "e" * 12, "dirty": True})
    sel = analysis.select(store, agents=["nearest"])
    assert list(sel.agents) == [a]
    assert list(analysis.select(store, agents=[a]).agents) == [a]
    assert list(analysis.select(store, agents=[REGISTRY["nearest"]().spec()]).agents) == [a]
    full = analysis.select(store)
    assert any("agents.py" in n for n in full.notes) and any("dirty" in n for n in full.notes)
    with pytest.raises(KeyError):
        analysis.select(store, agents=["no-such-agent"])


# --- table and pairing ---------------------------------------------------------------------------------------------

def test_the_table_has_means_labels_that_differ_and_paired_differences(store):
    add(store, REGISTRY["nearest"](), NEAREST)
    add(store, delta(0.2), [14, 17, 13, 18])
    add(store, delta(0.5), [20, 22, 21, 25])
    sel = analysis.select(store)
    rows = analysis.table(sel, baseline="nearest")
    assert [r["mean"] for r in rows] == sorted((r["mean"] for r in rows), reverse=True)
    top = rows[0]
    assert top["mean"] == pytest.approx(22.0) and top["std"] == pytest.approx(np.std([20, 22, 21, 25], ddof=1))
    d = np.array([20, 22, 21, 25]) - np.array(NEAREST)
    assert top["diff"] == pytest.approx(d.mean()) and top["diff_se"] == pytest.approx(d.std(ddof=1) / 2) and top["pairs"] == 4
    base = next(r for r in rows if r["agent_id"] == REGISTRY["nearest"]().spec_hash())
    assert base["diff"] is None
    labels = {r["agent_id"]: r["label"] for r in rows}
    assert any("alpha=0.2" in v for v in labels.values()) and len(set(labels.values())) == 3
    text = analysis.format_table(rows, sel)
    assert "engine " + fingerprint.code_version()["engine_hash"] in text and "(baseline)" in text and "metric total" in text


def test_paired_differences_use_only_the_seeds_both_agents_have(store):
    a = add(store, REGISTRY["nearest"](), [10, 10, 10, 10], seeds=[0, 1, 2, 3])
    b = add(store, delta(), [20, 30, 99], seeds=[1, 2, 7])
    n, diff, se = analysis.paired(analysis.select(store), b, a)
    assert n == 2 and diff == pytest.approx(15.0) and se == pytest.approx(5.0)


def test_metrics_can_be_a_column_a_trial_type_or_a_function(store):
    a = add(store, REGISTRY["nearest"](), [1, 2], by_type={"contrast": 0.5, "graded": 0.75}, accuracy=0.6)
    sel = analysis.select(store, kind=None)
    assert sel.values(a, "interlude_accuracy") == {0: 0.6, 1: 0.6}
    assert sel.values(a, "interlude:graded") == {0: 0.75, 1: 0.75}
    assert sel.values(a, "interlude:extrapolation") == {}
    assert sel.values(a, lambda row: row["total"] * 10) == {0: 10.0, 1: 20.0}


def test_gap_closed_is_the_per_seed_fraction_between_floor_and_ceiling(store):
    add(store, REGISTRY["nearest"](), [10, 10, 10, 10])
    add(store, REGISTRY["greedy_rate_10"](), [30, 20, 10, 50])                       # seed 2: no gap, dropped
    add(store, delta(), [20, 15, 99, 30])
    sel = analysis.select(store)
    n, mean, se, dropped = analysis.gap_closed(sel, delta(), "nearest", "greedy_rate_10")
    fractions = [(20 - 10) / 20, (15 - 10) / 10, (30 - 10) / 40]
    assert n == 3 and dropped == 1 and mean == pytest.approx(np.mean(fractions)) and se == pytest.approx(np.std(fractions, ddof=1) / np.sqrt(3))
    with pytest.raises(KeyError):
        analysis.gap_closed(sel, "greedy_rate_5", "nearest", "greedy_rate_10")


# --- component effect ----------------------------------------------------------------------------------------------

def test_component_effect_compares_agents_that_differ_only_in_the_factor(store):
    # two matched families (rate and value utility), three alphas each
    base = {"rate": [10, 10, 10, 10], "value": [20, 20, 20, 20]}
    gain = {0.2: 1.0, 0.5: 3.0, 0.8: 2.0}
    for utility, totals in base.items():
        for alpha, g in gain.items():
            add(store, delta(alpha, utility), [t + g * (1 + (utility == "value")) for t in totals])
    add(store, delta(0.5, "rate", choice=Softmax(0.5)), [99, 99, 99, 99])             # differs in two things from the others: unmatched
    sel = analysis.select(store)
    eff = analysis.component_effect(sel, "critic.alpha", reference=0.2)
    assert len(eff.groups) == 2 and eff.reference == "0.2"
    assert eff.levels["0.5"] == "alpha=0.5"
    # alpha 0.5 vs 0.2: +2 in the rate family, +4 in the value family
    assert eff.summary["0.5"]["groups"] == 2 and eff.summary["0.5"]["mean_diff"] == pytest.approx(3.0)
    assert eff.summary["0.5"]["se"] == pytest.approx(np.std([2.0, 4.0], ddof=1) / np.sqrt(2))
    assert eff.summary["0.8"]["mean_diff"] == pytest.approx(1.5)
    assert "alpha=0.5" in analysis.format_effect(eff, sel) and "matched group" in analysis.format_effect(eff)
    default_ref = analysis.component_effect(sel, "critic.alpha")                       # the level present in the most groups
    assert default_ref.reference in {"0.2", "0.5", "0.8"}


def test_a_component_with_parameters_of_its_own_is_one_level(store):
    add(store, delta(features=RBFFeatures(0.3)), [10, 11, 12])
    add(store, delta(features=RBFFeatures(0.15)), [14, 15, 16])
    add(store, delta(features=RBFFeatures(0.3, additive=False, n_centers=4)), [20, 20, 20])
    eff = analysis.component_effect(analysis.select(store), "critic.features", reference={"type": "RBFFeatures", "length_scale": 0.3,
                                                                                        "n_centers": 8, "additive": True})
    assert len(eff.groups) == 1 and len(eff.summary) == 2
    assert sorted(round(s["mean_diff"], 1) for s in eff.summary.values()) == [4.0, 9.0]
    assert all(("length_scale" in label or "n_centers" in label or "additive" in label) for lv, label in eff.levels.items())


def test_a_whole_critic_is_a_level_and_nothing_matched_is_an_error(store):
    for critic in (OracleCritic(), DeltaRuleCritic()):
        add(store, ComposedAgent(UtilityActor("rate", 10.0), critic, FullMemory()), [10, 20] if isinstance(critic, OracleCritic) else [5, 8])
    sel = analysis.select(store)
    eff = analysis.component_effect(sel, "critic")
    assert len(eff.groups) == 1 and len(eff.summary) == 1
    with pytest.raises(analysis.SelectionError):
        analysis.component_effect(sel, "actor.max_walk_time")


# --- from a real recorded run, and the command line ----------------------------------------------------------------

def test_a_recorded_run_flows_through_to_a_table_and_the_command_line(tmp_path, capsys):
    path = tmp_path / "r.sqlite"
    with Store(path) as s:
        for name in ("nearest", "greedy_rate_10"):
            record_run(name, "P", [0, 1, 2], "real", overrides={"session_duration": 20}, store=s)
    with Store(path, readonly=True) as s:
        sel = analysis.select(s, tag="real")
        rows = analysis.table(sel, baseline="nearest")
        assert len(rows) == 2 and rows[0]["pairs"] in (3, None)
        runs = analysis.list_runs(s)
        assert [r["tag"] for r in runs] == ["real", "real"]
    analysis.main(["runs", "--db", str(path)])
    analysis.main(["table", "--tag", "real", "--baseline", "nearest", "--db", str(path)])
    out = capsys.readouterr().out
    assert "paired diff" in out and "engine" in out and "(baseline)" in out and out.count("real") >= 3


def test_the_effect_command_reports_a_factor(tmp_path, capsys):
    path = tmp_path / "r.sqlite"
    with Store(path) as s:
        for alpha, gain in ((0.2, 1), (0.5, 3)):
            add(s, delta(alpha), [10 + gain, 12 + gain, 11 + gain], tag="a")
    analysis.main(["effect", "--tag", "a", "--factor", "critic.alpha", "--reference", "0.2", "--db", str(path)])
    out = capsys.readouterr().out
    assert "effect of critic.alpha against alpha=0.2" in out and "alpha=0.5" in out and "2.00" in out


def test_fruit_events_come_back_as_arrays_for_one_agent_and_seed(tmp_path):
    with Store(tmp_path / "r.sqlite") as s:
        record_run("greedy_rate_10", "P", [0, 1], "f", overrides={"session_duration": 20}, store=s)
        sel = analysis.select(s, tag="f")
        ev = analysis.fruit_events(s, sel, "greedy_rate_10", 1)
        row = next(iter(sel.rows.values()))[1]
        assert set(ev) == {"t", "bush", "k", "reward", "running_total"} and len(ev["t"]) == row["n_fruits"]
        assert ev["reward"].sum() == pytest.approx(row["total"]) and np.all(np.diff(ev["t"]) > 0)
        assert ev["bush"].dtype.kind == "i" and ev["t"].dtype.kind == "f"
        with pytest.raises(KeyError):
            analysis.fruit_events(s, sel, "greedy_rate_10", 99)


# --- cumulative reward over the session ---------------------------------------------------------------------------

def recorded(tmp_path, agents=("nearest", "greedy_rate_10"), seeds=(0, 1, 2, 3), duration=30):
    s = Store(tmp_path / "r.sqlite")
    for name in agents:
        record_run(name, "P", list(seeds), "c", overrides={"session_duration": duration}, store=s)
    return s, analysis.select(s, tag="c")


def test_one_seed_has_no_interval_and_episodes_without_fruit_events_are_refused(tmp_path):
    s, sel = recorded(tmp_path, agents=("nearest",), seeds=(0,))
    with s:
        c = next(iter(analysis.cumulative_curve(s, sel).agents.values()))
        assert c["n"] == 1 and np.isnan(c["lo"]).all() and np.isfinite(c["mean"]).all()
        add(s, delta(), [1, 2], tag="old", overrides={"session_duration": 30})            # no fruits stored, but fruits were taken
        s.conn.execute("UPDATE episodes SET n_fruits = 7 WHERE agent_id NOT IN (SELECT agent_id FROM runs WHERE tag = 'c')")
        s.conn.commit()
        with pytest.raises(analysis.SelectionError, match="no stored fruit events"):
            analysis.cumulative_curve(s, analysis.select(s, tag="old"))


# --- learning curves from checkpoints -----------------------------------------------------------------------------

def recorded_checkpoints(tmp_path, agents=("nearest", "delta_rate_10"), seeds=(0, 1, 2, 3)):
    s = Store(tmp_path / "r.sqlite")
    for name in agents:
        record_run(name, "P", list(seeds), "lc", kind="interlude", n_samples=5, interlude_mode="random", checkpoints=[0, 10, 30],
                   overrides={"session_duration": 30, "interlude_trial_count": 6}, store=s)
    return s, analysis.select(s, tag="lc", kind="interlude")


@pytest.mark.slow
def test_the_learning_curve_is_the_checkpoint_score_per_agent_with_an_interval(tmp_path):
    from scipy import stats
    s, sel = recorded_checkpoints(tmp_path)
    with s:
        curves = analysis.checkpoint_curve(s, sel)
        assert list(curves.t) == [0.0, 10.0, 30.0] and curves.metric == "interlude_accuracy" and len(curves.agents) == 2
        for aid, c in curves.agents.items():
            by_hand = np.array([[cp["interlude_accuracy"] for cp in s.checkpoints(sel.rows[aid][seed]["episode_id"])] for seed in c["seeds"]])
            assert np.allclose(c["per_seed"], by_hand) and np.allclose(c["mean"], by_hand.mean(axis=0))
            half = stats.t.ppf(0.975, 3) * by_hand.std(axis=0, ddof=1) / 2.0
            assert np.allclose(c["hi"] - c["mean"], half)
            assert np.allclose(c["per_seed"][:, -1], [sel.rows[aid][sd]["interlude_accuracy"] for sd in c["seeds"]])   # last checkpoint = the session's
        assert analysis.checkpoint_curve(s, sel, "interlude_bonus").metric == "interlude_bonus"
        import plots
        out = plots.plot_learning_curve(curves, tmp_path / "lc.png")
        assert out.exists() and out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    analysis.main(["learning", "--tag", "lc", "--kind", "interlude", "--out", str(tmp_path / "cmd.png"), "--db", str(tmp_path / "r.sqlite")])
    assert (tmp_path / "cmd.png").exists()


def test_a_selection_without_checkpoints_cannot_make_a_learning_curve(tmp_path):
    s, sel = recorded(tmp_path)
    with s:
        with pytest.raises(analysis.SelectionError, match="without checkpoints"):
            analysis.checkpoint_curve(s, sel)
        with pytest.raises(ValueError):
            analysis.checkpoint_curve(s, sel, "total")


# --- cumulative reward ---------------------------------------------------------------------------------------------

def test_cumulative_reward_ends_at_the_total_never_decreases_and_matches_the_fruits(tmp_path):
    s, sel = recorded(tmp_path)
    with s:
        curves = analysis.cumulative_curve(s, sel, step=1.0)
        assert curves.quantity == "cumulative" and curves.t[0] == 0.0 and curves.t[-1] == 30.0 and len(curves.t) == 31
        for aid, c in curves.agents.items():
            assert np.all(np.diff(c["per_seed"], axis=1) >= 0) and np.all(c["per_seed"][:, 0] == 0.0)
            assert np.allclose(c["per_seed"][:, -1], [sel.rows[aid][sd]["total"] for sd in c["seeds"]])         # the total at the end
            fruits = s.fruits(sel.rows[aid][c["seeds"][0]]["episode_id"])
            at_15 = sum(f["reward"] for f in fruits if f["t"] <= 15.0)
            assert c["per_seed"][0, 15] == pytest.approx(at_15)
        coarse = analysis.cumulative_curve(s, sel, step=10.0)
        assert list(coarse.t) == [0.0, 10.0, 20.0, 30.0]


def test_the_cumulative_curve_has_a_t_interval_across_seeds(tmp_path):
    from scipy import stats
    s, sel = recorded(tmp_path)
    with s:
        curves = analysis.cumulative_curve(s, sel)
        for c in curves.agents.values():
            m = c["per_seed"]
            assert c["n"] == 4 and m.shape == (4, 31)
            assert np.allclose(c["mean"], m.mean(axis=0))
            assert np.allclose(c["hi"] - c["mean"], stats.t.ppf(0.975, 3) * m.std(axis=0, ddof=1) / 2.0)
            assert np.allclose(c["lo"], 2 * c["mean"] - c["hi"])


def test_the_advantage_over_a_baseline_is_the_paired_difference_of_cumulative_reward(tmp_path):
    s, sel = recorded(tmp_path)
    with s:
        plain = analysis.cumulative_curve(s, sel)
        lead = analysis.cumulative_curve(s, sel, baseline="nearest")
        base_id = REGISTRY["nearest"]().spec_hash()
        assert lead.quantity == "advantage" and base_id not in lead.agents and len(lead.agents) == 1 and lead.baseline
        (aid, c), = lead.agents.items()
        assert np.allclose(c["per_seed"], plain.agents[aid]["per_seed"] - plain.agents[base_id]["per_seed"])
        assert np.allclose(c["per_seed"][:, -1], [sel.rows[aid][sd]["total"] - sel.rows[base_id][sd]["total"] for sd in c["seeds"]])
        only = analysis.select(s, tag="c", agents=["nearest"])
        with pytest.raises(analysis.SelectionError, match="only agent"):
            analysis.cumulative_curve(s, only, baseline="nearest")


def test_the_cumulative_and_advantage_figures_and_commands_are_written(tmp_path, capsys):
    import plots
    s, sel = recorded(tmp_path)
    with s:
        for kw in ({}, {"baseline": "nearest"}):
            out = plots.plot_cumulative_reward(analysis.cumulative_curve(s, sel, **kw), tmp_path / f"c{len(kw)}.png")
            assert out.exists() and out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    db = str(tmp_path / "r.sqlite")
    analysis.main(["curve", "--tag", "c", "--out", str(tmp_path / "cum.png"), "--db", db])
    assert "cumulative reward" in capsys.readouterr().out and (tmp_path / "cum.png").exists()
    analysis.main(["curve", "--tag", "c", "--baseline", "nearest", "--out", str(tmp_path / "adv.png"), "--db", db])
    assert "advantage in cumulative reward" in capsys.readouterr().out and (tmp_path / "adv.png").exists()
