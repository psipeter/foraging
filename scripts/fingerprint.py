"""Fingerprints: what a simulated result was computed from, so results from different setups are never confused.

Three things determine a result besides the agent (whose identity is `specs.spec_hash`):

  * the environment: which session, the session parameters the simulation actually reads (`SIM_FIELDS`), any overrides, the sensor
    the run imposed, whether it was a session or an Interlude evaluation (and its `n_samples`), and the motor-cost constants.
    `environment(...)` returns it as a dict and `environment_hash(...)` as 12 hex characters. The world seed is not part of it:
    seeds are the rows of the results, not the setup.
  * the engine code: a hash of the files that decide what the environment does (`ENGINE_FILES`),
  * the agents code: a separate hash of `agents.py` and `specs.py` (`AGENT_FILES`), so editing one agent does not make every
    engine result look stale, yet an agent whose behavior changed under an unchanged spec is still visible.

`code_version()` returns both hashes with the git commit and a dirty flag (any hashed file differs from HEAD, or is untracked). The
hashes are of the file bytes, so a comment edit also changes them: a false alarm is the safe error. Python and numpy versions are
recorded for orientation only (not hashed).

`SIM_FIELDS` is the list of SessionConfig fields (snake_case) the simulator reads. It is checked by
test_fingerprint.py::test_sim_fields_cover_every_session_parameter_the_simulator_reads, which traces a run: when the code starts
reading another field, that test fails and the field must be added here (every environment hash then changes).
"""

import hashlib
import platform
import subprocess
from pathlib import Path

import numpy as np

import costs
from specs import canonical_json
from world import load_session

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent

ENGINE_FILES = ("sim.py", "costs.py", "perception.py", "world.py", "interlude.py")
AGENT_FILES = ("agents.py", "specs.py")

SIM_FIELDS = (
    "camera_field_of_view", "canopy_width_range", "eye_height", "fruit_count", "fruit_harvest_duration", "harvest_max_angle",
    "harvest_range_gap_base", "harvest_range_gap_per_radius", "interlude_bonus_per_correct", "interlude_bush_bearing",
    "interlude_bush_distance", "interlude_for", "interlude_min_elevation_difference", "interlude_mode", "interlude_trial_count", "is_interlude", "is_practice", "moisture_terrace_levels",
    "moisture_terrace_residual", "moisture_terrace_sharpness", "mountain_band_width", "mountain_block_threshold",
    "mountain_boundary_jitter", "mountain_height", "mountain_noise_scale", "placement_jitter", "player_move_speed",
    "reward_function", "reward_std", "session_duration", "session_name", "shape_range", "snow_line_fraction",
    "start_clearing_radius", "terrain_max_elevation", "terrain_mesh_resolution", "terrain_noise_frequency",
    "terrain_noise_octaves", "tree_edge_margin", "tree_spacing", "world_half_extent",
)


def _digest(obj):
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------------------------------

def params_hash(name, overrides=None):
    """Hash of the simulation-relevant fields of the session asset `name` after `overrides` (the audio, visuals, UI text and the world
    seed do not change it)."""
    params = load_session(name, **(overrides or {}))
    return _digest({f: getattr(params, f, None) for f in SIM_FIELDS})      # (None: a field an older asset file does not have yet)


def motor_costs():
    """The constants of costs.py (upper-case numbers) as a dict."""
    return {k: float(v) for k, v in vars(costs).items() if k.isupper() and isinstance(v, (int, float))}


def interlude_mode_of(name, mode=None, overrides=None):
    """The mode an Interlude is generated in: `mode`, else the asset's own `interludeMode` (absent in an older asset = designed)."""
    from interlude import interlude_mode
    return interlude_mode(load_session(name, **(overrides or {})), mode)


def environment(session, overrides=None, percept=None, kind="session", n_samples=None, interlude_mode=None, checkpoints=None):
    """The environment a result was computed in, as a plain dict. `percept` is the run's sensor override (a Component, or None for
    the world's own); `kind` is "session" or "interlude" (then `n_samples` is the number of repeated choices per trial and
    `interlude_mode` the trial design, "designed" or "random", None = the Interlude asset's own, and `checkpoints` the session times
    (seconds) at which a copy of the agent is also scored on the Interlude)."""
    if kind not in ("session", "interlude"):
        raise ValueError(f"kind must be 'session' or 'interlude', not '{kind}'")
    overrides = dict(overrides or {})
    if kind == "session" and n_samples is not None:
        raise ValueError("n_samples applies to an Interlude evaluation only")
    env = {"session": session, "session_hash": params_hash(session, overrides), "overrides": overrides,
           "percept": None if percept is None else percept.spec(), "kind": kind,
           "n_samples": None if n_samples is None else int(n_samples), "costs": motor_costs()}
    if kind == "interlude":
        env["interlude_hash"] = params_hash(f"{session}_Interlude", overrides)
        env["interlude_mode"] = interlude_mode_of(f"{session}_Interlude", interlude_mode, overrides)
        if checkpoints is not None:
            times = sorted({float(t) for t in checkpoints})
            length = float(load_session(session, **overrides).session_duration)
            if not times or times[0] < 0.0 or times[-1] > length:
                raise ValueError(f"checkpoints must be session times between 0 and {length:g} s, got {list(checkpoints)}")
            env["checkpoints"] = times
    elif interlude_mode is not None or checkpoints is not None:
        raise ValueError("interlude_mode and checkpoints apply to an Interlude evaluation only")
    return env


def environment_hash(*args, **kwargs):
    return _digest(environment(*args, **kwargs))


# --------------------------------------------------------------------------------------------------
# Code
# --------------------------------------------------------------------------------------------------

def hash_files(paths):
    """12 hex characters over the names and bytes of these files (sorted by name)."""
    h = hashlib.sha256()
    for path in sorted(Path(p) for p in paths):
        h.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()[:12]


def git_state(paths, cwd=ROOT):
    """(short commit, dirty) for the repository containing `cwd`: dirty when any of `paths` has uncommitted changes or is untracked.
    (None, None) when git cannot answer."""
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain", "--", *[str(p) for p in paths]], cwd=cwd, capture_output=True,
                                text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None, None
    return commit, bool(status.strip())


def code_version():
    """The code a result was computed with: {engine_hash, agents_hash, commit, dirty, python, numpy}."""
    engine = [SCRIPTS / f for f in ENGINE_FILES]
    agents = [SCRIPTS / f for f in AGENT_FILES]
    commit, dirty = git_state(engine + agents)
    return {"engine_hash": hash_files(engine), "agents_hash": hash_files(agents), "commit": commit, "dirty": dirty,
            "python": platform.python_version(), "numpy": np.__version__}
