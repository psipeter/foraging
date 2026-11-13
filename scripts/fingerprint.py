"""Fingerprints: what a simulated result was computed from, so results from different setups are never confused.

Three things determine a result besides the agent (whose identity is `specs.spec_hash`):

  * the environment: which session, the session parameters the simulation actually reads (`SIM_FIELDS`), any overrides, the sensor
    the run imposed, and the motor-cost constants (the dict keeps `kind` = "session" and `n_samples` = None, the keys of the schema before the forced-choice evaluation was retired).
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
import tiles
from specs import canonical_json
from world import load_session

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent

ENGINE_FILES = ("sim.py", "costs.py", "perception.py", "world.py", "ranking.py", "tiles.py")
AGENT_FILES = ("agents.py", "specs.py")

TILE_FIELDS = (*tiles.TILE_PARAMS, "tile_arrangement", "tile_value_mode", "tile_within_mode")


SIM_FIELDS = (
    "camera_field_of_view", "canopy_height_range", "canopy_width_range", "color_varies", "color_when_fixed", "eye_height", "fruit_count", "fruit_harvest_duration", "harvest_max_angle",
    "harvest_range_gap_base", "harvest_range_gap_per_radius", "layout", "assignment", "reward_stage", "moisture_varies", "moisture_when_fixed",
    "mountain_band_width", "mountain_block_threshold", "mountain_boundary_jitter", "mountain_height", "mountain_noise_scale", "player_move_speed",
    "random_bush_value_range", "reward_function", "reward_std", "session_duration", "shape_range", "shape_varies", "shape_when_fixed", "snow_line_fraction",
    "terrain_max_elevation", "terrain_mesh_resolution", "tree_edge_margin", "world_half_extent",
    *TILE_FIELDS,
)


def _digest(obj):
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------------------------------

def _reward_without_new_defaults(rf):
    """The reward function as it was hashed before `factors` and a bump's `angle` existed: an empty `factors` list and a zero `angle` are left out, so re-saving an asset in the Editor
    (which writes both) moves no stored hash."""
    if not isinstance(rf, dict):
        return rf
    out = {k: v for k, v in rf.items() if not (k == "factors" and not v)}
    if out.get("bumps"):
        out["bumps"] = [{k: v for k, v in b.items() if not (k == "angle" and not v)} for b in out["bumps"]]
    return out


def params_hash(name, overrides=None):
    """Hash of the simulation-relevant fields of the session asset `name` after `overrides` (the audio, visuals, UI text and the world
    seed do not change it)."""
    params = load_session(name, **(overrides or {}))
    fields = {f: getattr(params, f, None) for f in SIM_FIELDS}      # (None: a field an older asset file does not have yet)
    fields["reward_function"] = _reward_without_new_defaults(fields["reward_function"])
    return _digest(fields)


def motor_costs():
    """The constants of costs.py (upper-case numbers) as a dict."""
    return {k: float(v) for k, v in vars(costs).items() if k.isupper() and isinstance(v, (int, float))}


def environment(session, overrides=None, percept=None):
    """The environment a result was computed in, as a plain dict. `percept` is the run's sensor override (a Component, or None for
    the world's own)."""
    overrides = dict(overrides or {})
    return {"session": session, "session_hash": params_hash(session, overrides), "overrides": overrides,
            "percept": None if percept is None else percept.spec(), "kind": "session", "n_samples": None, "costs": motor_costs()}


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
