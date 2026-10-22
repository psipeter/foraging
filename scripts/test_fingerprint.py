import re
import subprocess
import types

import pytest

import costs
import fingerprint
import interlude
import sim
import world
from agents import ComposedAgent, Explore, FullMemory, OracleCritic
from fingerprint import SIM_FIELDS, code_version, environment, environment_hash, git_state, hash_files, params_hash
from perception import ConePercept
from test_agents import Script


# --- the session parameters that count ------------------------------------------------------------------------------

def test_params_hash_is_stable_and_follows_simulation_parameters_only():
    base = params_hash("S1")
    assert base == params_hash("S1") and re.fullmatch(r"[0-9a-f]{12}", base)
    assert params_hash("S1", {"session_duration": 90}) != base
    assert params_hash("S1", {"tree_spacing": 30.0}) != base
    assert params_hash("S1", {"player_move_speed": 8.0}) != base
    # audio, visuals, UI text and the per-episode world seed are not part of what an agent plays in
    assert params_hash("S1", {"sfx_volume": 0.123}) == base
    assert params_hash("S1", {"sun_latitude": 12.0}) == base
    assert params_hash("S1", {"world_seed": 12345}) == base
    assert params_hash("S1") != params_hash("S3")


def test_a_changed_reward_function_changes_the_hash():
    rf = world.load_session("S1").reward_function
    other = {**rf, "colorComponent": {**rf["colorComponent"], "weight": rf["colorComponent"]["weight"] + 1.0}}
    assert params_hash("S1", {"reward_function": other}) != params_hash("S1")


# --- the environment ------------------------------------------------------------------------------------------------

def test_environment_records_what_was_run_and_hashes_every_part():
    env = environment("S1", {"session_duration": 90})
    assert env["session"] == "S1" and env["overrides"] == {"session_duration": 90} and env["kind"] == "session"
    assert env["percept"] is None and env["n_samples"] is None and "interlude_hash" not in env
    assert env["costs"]["TURN_RATE"] == costs.TURN_RATE
    base = environment_hash("S1", {"session_duration": 90})
    assert base == environment_hash("S1", {"session_duration": 90.0})                 # numbers by value
    assert environment_hash("S1", {"session_duration": 120}) != base
    assert environment_hash("S1", {"session_duration": 90}, percept=ConePercept(60, 50)) != base
    assert environment_hash("S1", {"session_duration": 90}, percept=ConePercept(60, 50)) != \
        environment_hash("S1", {"session_duration": 90}, percept=ConePercept(60, 60))
    assert environment_hash("S2", {"session_duration": 90}) != base


def test_an_interlude_environment_adds_its_own_asset_and_sample_count():
    env = environment("S1", kind="interlude", n_samples=200)
    assert env["kind"] == "interlude" and env["n_samples"] == 200 and re.fullmatch(r"[0-9a-f]{12}", env["interlude_hash"])
    assert environment_hash("S1", kind="interlude", n_samples=100) != environment_hash("S1", kind="interlude", n_samples=200)
    assert environment_hash("S1", kind="interlude", n_samples=200) != environment_hash("S1")
    with pytest.raises(ValueError):
        environment("S1", n_samples=5)
    with pytest.raises(ValueError):
        environment("S1", kind="practice")


def test_the_motor_costs_are_part_of_the_environment(monkeypatch):
    before = environment_hash("S1")
    monkeypatch.setattr(costs, "WALK_PRESS_TIME", costs.WALK_PRESS_TIME + 0.1)
    assert environment_hash("S1") != before


def test_an_unknown_override_is_refused():
    with pytest.raises(KeyError):
        params_hash("S1", {"no_such_parameter": 1})


# --- the code -------------------------------------------------------------------------------------------------------

def test_hash_files_follows_content_and_names_not_location(tmp_path):
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text("x = 1\n")
    b.write_text("y = 2\n")
    h = hash_files([a, b])
    assert h == hash_files([b, a])
    b.write_text("y = 3\n")
    assert hash_files([a, b]) != h


def test_git_state_reports_the_commit_and_whether_the_files_are_dirty(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True,
                       env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                            "PATH": __import__("os").environ["PATH"], "HOME": str(tmp_path)})
    git("init", "-q")
    f, g = tmp_path / "f.py", tmp_path / "g.py"
    f.write_text("1\n")
    g.write_text("1\n")
    git("add", "f.py", "g.py")
    git("commit", "-q", "-m", "x")
    commit, dirty = git_state([f], cwd=tmp_path)
    assert re.fullmatch(r"[0-9a-f]{7,}", commit) and dirty is False
    g.write_text("2\n")
    assert git_state([f], cwd=tmp_path)[1] is False          # only the listed files count
    f.write_text("2\n")
    assert git_state([f], cwd=tmp_path)[1] is True
    git("checkout", "f.py")
    new = tmp_path / "new.py"
    new.write_text("1\n")
    assert git_state([new], cwd=tmp_path)[1] is True         # untracked
    assert git_state([f], cwd=tmp_path / "missing") == (None, None)


def test_code_version_hashes_the_engine_and_the_agents_separately(monkeypatch, tmp_path):
    version = code_version()
    assert set(version) == {"engine_hash", "agents_hash", "commit", "dirty", "python", "numpy"}
    assert version["engine_hash"] != version["agents_hash"]
    assert re.fullmatch(r"[0-9a-f]{12}", version["engine_hash"]) and re.fullmatch(r"[0-9a-f]{12}", version["agents_hash"])
    for name in fingerprint.ENGINE_FILES + fingerprint.AGENT_FILES:
        assert (fingerprint.SCRIPTS / name).exists(), name
    # editing an agent file moves the agents hash and leaves the engine hash alone
    fake = tmp_path
    for name in fingerprint.ENGINE_FILES + fingerprint.AGENT_FILES:
        (fake / name).write_text(f"# {name}\n")
    monkeypatch.setattr(fingerprint, "SCRIPTS", fake)
    before = code_version()
    (fake / "agents.py").write_text("# changed\n")
    after = code_version()
    assert after["agents_hash"] != before["agents_hash"] and after["engine_hash"] == before["engine_hash"]
    (fake / "sim.py").write_text("# changed\n")
    assert code_version()["engine_hash"] != before["engine_hash"]


# --- the list of fields must cover what the simulator reads ---------------------------------------------------------

@pytest.mark.slow
def test_sim_fields_cover_every_session_parameter_the_simulator_reads(monkeypatch):
    accessed = set()

    class Recording(types.SimpleNamespace):
        def __getattribute__(self, name):
            assert name != "__dict__", "something reads the parameters wholesale: the fingerprint cannot tell which fields it uses"
            if not name.startswith("_"):
                accessed.add(name)
            return super().__getattribute__(name)

    original = world.load_session

    def traced(name="S1", **overrides):
        return Recording(**vars(original(name, **overrides)))

    for module in (world, sim, interlude):
        monkeypatch.setattr(module, "load_session", traced)
    from agents import REGISTRY
    for session in ("P", "S1", "S3", "S4"):
        worlds = sim.get_worlds(session, range(2))
        for name in ("nearest", "greedy_rate_10", "plan_beam", "delta_rate_10"):
            for w in worlds:
                sim.run_episode(REGISTRY[name](), w)
        sim.run_episode(ComposedAgent(Script(Explore(0.0, 40.0)), OracleCritic(), FullMemory()), worlds[0])   # walks: reads the mountain block
        sidecar, bonus, practice = sim.get_interlude(session, 0)
        agent = REGISTRY["delta_rate_10"]()
        sim.run_episode(agent, worlds[0])
        sim.evaluate_interlude(agent, sidecar, bonus, practice, n_samples=5)
    missing = accessed - set(SIM_FIELDS) - {"world_seed"}
    assert not missing, f"add to fingerprint.SIM_FIELDS: {sorted(missing)}"
    assert "mountain_block_threshold" in accessed                      # the exploring walk was traced
    assert set(SIM_FIELDS) <= accessed | {"world_seed"}, sorted(set(SIM_FIELDS) - accessed)   # and nothing listed is unread


def test_an_interlude_environment_records_its_mode_and_only_an_interlude_has_one():
    asset_mode = environment("S1", kind="interlude", n_samples=5)["interlude_mode"]                  # whatever the asset says
    assert asset_mode in ("designed", "random")
    other = "designed" if asset_mode == "random" else "random"
    assert environment("S1", kind="interlude", n_samples=5, interlude_mode=asset_mode) == environment("S1", kind="interlude", n_samples=5)
    assert environment("S1", kind="interlude", n_samples=5, interlude_mode=other)["interlude_mode"] == other
    assert environment_hash("S1", kind="interlude", n_samples=5, interlude_mode=other) != environment_hash("S1", kind="interlude", n_samples=5)
    assert environment_hash("S1", {"interlude_trial_count": 50}, kind="interlude", n_samples=5) != environment_hash("S1", kind="interlude", n_samples=5)
    with pytest.raises(ValueError):
        environment("S1", interlude_mode="random")                                    # a session run has no Interlude mode
    with pytest.raises(ValueError):
        environment("S1", kind="interlude", interlude_mode="shuffled")


def test_checkpoints_are_part_of_an_interlude_environment_and_must_fit_the_session():
    base = environment_hash("S1", {"session_duration": 90}, kind="interlude", n_samples=5)
    with_cp = environment_hash("S1", {"session_duration": 90}, kind="interlude", n_samples=5, checkpoints=[0, 30, 90])
    assert with_cp != base
    assert with_cp == environment_hash("S1", {"session_duration": 90}, kind="interlude", n_samples=5, checkpoints=[90.0, 0, 30, 30])
    assert environment("S1", {"session_duration": 90}, kind="interlude", n_samples=5, checkpoints=[30, 0])["checkpoints"] == [0.0, 30.0]
    assert "checkpoints" not in environment("S1", kind="interlude", n_samples=5)
    for bad in ([91], [-1], []):
        with pytest.raises(ValueError):
            environment("S1", {"session_duration": 90}, kind="interlude", n_samples=5, checkpoints=bad)
    with pytest.raises(ValueError):
        environment("S1", checkpoints=[10])
