import sqlite3
import sys

import numpy as np
import pytest

import fingerprint
import results
import sim
from agents import ComposedAgent, DeltaRuleCritic, FullMemory, UtilityActor, REGISTRY
from perception import ConePercept
from results import Store, record_run


SEEDS = [0, 1, 2]
OVERRIDES = {"session_duration": 20}


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "r.sqlite") as s:
        yield s


def run(store, agent="nearest", seeds=SEEDS, tag="t", **kw):
    kw.setdefault("overrides", OVERRIDES)
    return record_run(agent, "P", seeds, tag, store=store, **kw)


# --- schema --------------------------------------------------------------------------------------------------------

def test_a_new_file_gets_the_schema_and_reopens(tmp_path):
    path = tmp_path / "sub" / "r.sqlite"
    with Store(path) as s:
        assert s.version == results.SCHEMA_VERSION
        names = {r["name"] for r in s.select("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"agents", "agent_params", "environments", "code_versions", "runs", "episodes", "episode_types", "run_episodes"} <= names
    with Store(path) as s:
        assert s.version == results.SCHEMA_VERSION
    with Store(path, readonly=True) as s, pytest.raises(sqlite3.OperationalError):
        s.conn.execute("DELETE FROM runs")


def test_a_newer_file_is_refused_and_a_missing_one_is_not_created_read_only(tmp_path):
    path = tmp_path / "r.sqlite"
    Store(path).close()
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {results.SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError):
        Store(path)
    with pytest.raises(FileNotFoundError):
        Store(tmp_path / "none.sqlite", readonly=True)


def test_an_older_file_is_copied_before_it_is_migrated(tmp_path, monkeypatch):
    path = tmp_path / "r.sqlite"
    Store(path).close()
    monkeypatch.setattr(results, "SCHEMA_VERSION", results.SCHEMA_VERSION + 1)
    monkeypatch.setitem(results.MIGRATIONS, results.SCHEMA_VERSION - 1, "CREATE TABLE extra (x INTEGER);")
    with Store(path) as s:
        assert s.version == results.SCHEMA_VERSION and s.select("SELECT name FROM sqlite_master WHERE name = 'extra'")
    assert (tmp_path / f"r.sqlite.bak-v{results.SCHEMA_VERSION - 1}").exists()


def test_a_version_1_file_gains_the_fruit_table_and_keeps_its_rows(tmp_path):
    path = tmp_path / "r.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(results.SCHEMA_V1 + "PRAGMA user_version = 1;")
    conn.execute("INSERT INTO agents (agent_id, spec_json) VALUES ('abc', '{}')")
    conn.commit()
    conn.close()
    with Store(path) as s:
        assert s.version == results.SCHEMA_VERSION
        assert s.select("SELECT agent_id FROM agents") == [{"agent_id": "abc"}]
        assert s.select("SELECT COUNT(*) AS n FROM episode_fruits")[0]["n"] == 0
    assert (tmp_path / "r.sqlite.bak-v1").exists()


# --- agents, environments, code ------------------------------------------------------------------------------------

def test_an_agent_is_stored_once_with_its_components_and_parameters(store):
    spec = REGISTRY["delta_rate_10"]().spec()
    agent_id = store.record_agent(spec)
    assert agent_id == store.record_agent(spec) == REGISTRY["delta_rate_10"]().spec_hash()
    row = store.select("SELECT * FROM agents WHERE agent_id = ?", (agent_id,))[0]
    assert (row["memory"], row["critic"], row["features"], row["prior"], row["actor"], row["choice"], row["percept"]) == \
        ("FullMemory", "DeltaRuleCritic", "RBFFeatures", "ConstantPrior", "UtilityActor", "Argmax", None)
    params = {(r["component"], r["key"]): r["value"] for r in store.select("SELECT * FROM agent_params WHERE agent_id = ?", (agent_id,))}
    assert params[("critic", "alpha")] == 0.5 and params[("critic", "features.length_scale")] == 0.3
    assert params[("actor", "utility")] == "rate" and params[("critic", "features.additive")] == 1
    assert store.select("SELECT typeof(value) AS t FROM agent_params WHERE key = 'alpha'")[0]["t"] == "real"
    assert store.select("SELECT COUNT(*) AS n FROM agents")[0]["n"] == 1


def test_parameters_can_be_queried_across_agents(store):
    for alpha in (0.2, 0.5, 0.8):
        store.record_agent(ComposedAgent(UtilityActor("rate", 10.0), DeltaRuleCritic(alpha=alpha), FullMemory()).spec())
    rows = store.select("SELECT a.agent_id FROM agents a JOIN agent_params p USING (agent_id) "
                        "WHERE p.component = 'critic' AND p.key = 'alpha' AND p.value >= 0.5")
    assert len(rows) == 2


def test_environments_and_code_versions_are_recorded_and_deduplicated(store):
    env = fingerprint.environment("P", OVERRIDES)
    assert store.record_environment(env) == store.record_environment(env)
    assert store.select("SELECT COUNT(*) AS n FROM environments")[0]["n"] == 1
    code = {"engine_hash": "e1", "agents_hash": "a1", "commit": "abc1234", "dirty": True, "python": "3", "numpy": "2"}
    first = store.record_code(code)
    assert store.record_code(code) == first
    assert store.record_code({**code, "agents_hash": "a2"}) != first
    store.record_code({**code, "commit": "def5678", "dirty": False})                # the same code on a clean commit
    row = store.select("SELECT * FROM code_versions WHERE code_id = ?", (first,))[0]
    assert row["dirty"] == 0 and row["commit_hash"] == "def5678"
    store.record_code({**code, "commit": "later", "dirty": True})                    # a clean record is never made dirty again
    assert store.select("SELECT dirty FROM code_versions WHERE code_id = ?", (first,))[0]["dirty"] == 0


# --- recording and lookup ------------------------------------------------------------------------------------------

def test_a_run_is_computed_once_and_then_looked_up(store):
    first = run(store)
    assert (first.n_computed, first.n_reused) == (3, 0) and first.seeds == SEEDS and len(first.rows) == 3
    again = run(store, tag="other")
    assert (again.n_computed, again.n_reused) == (0, 3)
    assert list(again.totals) == list(first.totals) and again.run_id != first.run_id
    assert store.select("SELECT COUNT(*) AS n FROM episodes")[0]["n"] == 3
    wider = run(store, seeds=[1, 2, 3, 4])
    assert (wider.n_computed, wider.n_reused) == (2, 2)
    assert store.select("SELECT COUNT(*) AS n FROM episodes")[0]["n"] == 5


def test_recorded_episodes_equal_what_the_engine_gives(store):
    report = run(store, "greedy_rate_10")
    direct = sim.run_n(REGISTRY["greedy_rate_10"], "P", SEEDS, **OVERRIDES)
    assert np.allclose(report.totals, direct.totals)
    row = report.rows[0]
    assert row["n_visits"] == direct.results[0].n_visits and row["walk_time"] == pytest.approx(direct.results[0].walk_time)
    assert row["interlude_accuracy"] is None and row["interlude_trials"] is None        # (the retired columns stay NULL)


def test_anything_that_changes_the_setup_makes_a_new_record(store, monkeypatch):
    base = run(store)
    other = run(store, overrides={"session_duration": 30})                          # another environment
    assert other.n_computed == 3 and other.env_id != base.env_id
    sensed = run(store, percept=ConePercept(60, 50))
    assert sensed.n_computed == 3 and sensed.env_id not in (base.env_id, other.env_id)
    changed = run(store, "greedy_rate_10")                                          # another agent
    assert changed.n_computed == 3 and changed.agent_id != base.agent_id
    real = fingerprint.code_version
    monkeypatch.setattr(fingerprint, "code_version", lambda: {**real(), "engine_hash": "0" * 12})   # other engine code
    recoded = run(store)
    assert recoded.n_computed == 3 and recoded.code_id != base.code_id
    assert store.select("SELECT COUNT(*) AS n FROM episodes")[0]["n"] == 15


def test_an_agent_can_be_given_as_a_factory_a_name_or_a_spec(store):
    by_name = run(store, "nearest")
    by_factory = run(store, REGISTRY["nearest"], tag="f")
    by_spec = run(store, REGISTRY["nearest"]().spec(), tag="s")
    assert by_name.agent_id == by_factory.agent_id == by_spec.agent_id
    assert (by_factory.n_computed, by_spec.n_computed) == (0, 0)


def test_a_tag_finds_exactly_what_its_run_used(store):
    run(store, tag="a")
    run(store, seeds=[1, 2, 3], tag="b")
    for tag, seeds in (("a", [0, 1, 2]), ("b", [1, 2, 3])):
        rows = store.select("SELECT e.seed FROM episodes e JOIN run_episodes re USING (episode_id) JOIN runs r USING (run_id) "
                            "WHERE r.tag = ? ORDER BY e.seed", (tag,))
        assert [r["seed"] for r in rows] == seeds


def test_the_same_episode_cannot_be_recorded_twice(store):
    report = run(store)
    row = report.rows[0]
    with pytest.raises(sqlite3.IntegrityError):
        store.add_episode(row["agent_id"], row["env_id"], row["code_id"], row["seed"], report.run_id, {"total": 1.0})
    with pytest.raises(KeyError):
        store.add_episode(row["agent_id"], row["env_id"], row["code_id"], 99, report.run_id, {"bogus": 1.0})


def test_a_duplicate_seed_is_refused_and_a_failed_run_keeps_what_it_computed(store, monkeypatch):
    with pytest.raises(ValueError):
        run(store, seeds=[1, 1])
    real = sim.run_episode
    calls = []

    def flaky(agent, world, *a, **kw):
        calls.append(world.seed)
        if len(calls) == 3:
            raise KeyboardInterrupt
        return real(agent, world, *a, **kw)

    monkeypatch.setattr(sim, "run_episode", flaky)
    with pytest.raises(KeyboardInterrupt):
        run(store, tag="cut")
    row = store.select("SELECT * FROM runs WHERE tag = 'cut'")[0]
    assert row["seeds"] == "0,1" and row["n_computed"] == 2 and "interrupted" in row["note"]
    monkeypatch.setattr(sim, "run_episode", real)
    resumed = run(store, tag="resume")
    assert (resumed.n_computed, resumed.n_reused) == (1, 2)


def test_deleting_a_run_removes_its_episodes_and_links(store):
    a = run(store, tag="a")
    b = run(store, tag="b", seeds=[2, 3])                                            # reuses seed 2 from run a
    assert store.delete_run(a.run_id) == 3
    assert store.select("SELECT COUNT(*) AS n FROM episodes")[0]["n"] == 1           # only seed 3, computed by b
    assert [r["seed"] for r in store.run_episodes(b.run_id)] == [3]
    assert store.select("SELECT COUNT(*) AS n FROM runs")[0]["n"] == 1


# --- the command line ----------------------------------------------------------------------------------------------

def cli(monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, "argv", ["sim.py", *args])
    sim.main()
    return capsys.readouterr().out


def test_sim_record_stores_the_runs_reuses_them_and_prints_the_table(monkeypatch, capsys, tmp_path):
    db = str(tmp_path / "r.sqlite")
    args = ("P", "--seeds", "0-2", "--agents", "nearest,greedy_rate_10", "--set", "session_duration=20", "--record", "--tag", "cli",
            "--db", db)
    out = cli(monkeypatch, capsys, *args)
    assert "computed 3, reused 0" in out and "diff vs nearest" in out and "tag cli" in out
    again = cli(monkeypatch, capsys, *args)
    assert "computed 0, reused 3" in again
    with Store(db, readonly=True) as s:
        assert s.select("SELECT COUNT(*) AS n FROM runs")[0]["n"] == 4
        assert s.select("SELECT COUNT(*) AS n FROM episodes")[0]["n"] == 6


def test_sim_record_needs_a_tag_and_the_flags_need_record(monkeypatch, capsys, tmp_path):
    with pytest.raises(SystemExit):
        cli(monkeypatch, capsys, "P", "--agents", "nearest", "--record", "--db", str(tmp_path / "r.sqlite"))
    with pytest.raises(SystemExit):
        cli(monkeypatch, capsys, "P", "--agents", "nearest", "--tag", "x")
    out = cli(monkeypatch, capsys, "P", "--seeds", "0-1", "--agents", "nearest,greedy_rate_10", "--set", "session_duration=20")
    assert "agent" in out and not (tmp_path / "r.sqlite").exists()


# --- per-fruit events ----------------------------------------------------------------------------------------------

def test_every_fruit_taken_is_stored_in_order_and_matches_the_engine(store):
    report = run(store, "greedy_rate_10", seeds=[0, 1])
    world = sim.get_worlds("P", [0], **OVERRIDES)[0]
    direct = sim.run_episode(REGISTRY["greedy_rate_10"](), world)
    row = report.rows[0]
    fruits = store.fruits(row["episode_id"])
    assert len(fruits) == row["n_fruits"] == direct.n_fruits > 0
    assert [f["reward"] for f in fruits] == [f[3] for f in direct.fruits]
    assert sum(f["reward"] for f in fruits) == pytest.approx(row["total"])
    assert fruits[-1]["running_total"] == pytest.approx(row["total"])
    t = [f["t"] for f in fruits]
    assert t == sorted(t) and 0.0 < t[0] and t[-1] <= OVERRIDES["session_duration"] + 1e-9
    for f in fruits:                                                    # the k-th fruit of a bush pays what the world file says
        assert f["reward"] == world.fruit_reward[f["bush"], f["k"]]
    assert all(f["running_total"] >= 0 for f in fruits)


def test_reused_episodes_keep_their_fruits_and_deleting_a_run_removes_them(store):
    a = run(store, tag="a")
    again = run(store, tag="again")
    assert again.n_computed == 0
    assert store.fruits(again.rows[0]["episode_id"]) == store.fruits(a.rows[0]["episode_id"]) != []
    assert store.select("SELECT COUNT(*) AS n FROM episode_fruits")[0]["n"] > 0
    store.delete_run(a.run_id)
    assert store.select("SELECT COUNT(*) AS n FROM episode_fruits")[0]["n"] == 0


# --- checkpoints ---------------------------------------------------------------------------------------------------


# --- the migration that retired the forced-choice evaluation (schema 4) ---------------------------------------------

def _old_file(path, version):
    """A results file as an older code wrote it, with one episode of the retired kind in it."""
    conn = sqlite3.connect(path)
    conn.executescript(results.SCHEMA_V1 + "".join(results.MIGRATIONS[v] for v in range(1, version)) + f"PRAGMA user_version = {version};")
    conn.executescript("""
        INSERT INTO agents VALUES ('a1', NULL, NULL, NULL, NULL, NULL, NULL, NULL, '{}');
        INSERT INTO environments VALUES ('e1', 'S1', 'h', 'interlude', 5, 'ih', '{}', NULL, '{}', '{}');
        INSERT INTO code_versions VALUES (1, 'eh', 'ah', 'c', 0, '3', '1', 't');
        INSERT INTO runs VALUES (1, 'a1', 'e1', 1, 'old', NULL, '0', 1, 1, 0, 't');
        INSERT INTO episodes (episode_id, agent_id, env_id, code_id, seed, computed_by, total, interlude_trials, interlude_accuracy, interlude_bonus)
            VALUES (1, 'a1', 'e1', 1, 0, 1, 12.0, 6, 0.75, 3.0);
        INSERT INTO episode_types VALUES (1, 'random', 0.75);
    """)
    conn.commit()
    conn.close()


@pytest.mark.parametrize("version", [2, 3])
def test_an_older_file_keeps_its_retired_interlude_rows_and_is_backed_up(tmp_path, version):
    path = tmp_path / "r.sqlite"
    _old_file(path, version)
    with Store(path) as s:
        assert s.version == results.SCHEMA_VERSION == 4
        row = s.select("SELECT * FROM episodes WHERE episode_id = 1")[0]
        assert row["interlude_accuracy"] == 0.75 and row["total"] == 12.0
        assert s.select("SELECT COUNT(*) AS n FROM episode_types")[0]["n"] == 1
        assert s.select("SELECT version FROM schema_notes")[0]["version"] == 4
    assert (tmp_path / f"r.sqlite.bak-v{version}").exists()


def test_a_retired_interlude_record_is_never_selected_or_mixed_with_sessions(tmp_path):
    import analysis
    path = tmp_path / "r.sqlite"
    _old_file(path, 3)
    with Store(path) as s:
        with pytest.raises(analysis.SelectionError):
            analysis.select(s, engine="any")
