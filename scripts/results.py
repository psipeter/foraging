"""The results database: every simulated-agent run, keyed by what it was computed from (see CLAUDE.md, "Results database").

    results/results.sqlite      (repo root, gitignored, flat)

An episode (one agent, one world seed) is identified by (agent, environment, code version, seed):
  * the agent by `specs.spec_hash` of its spec (`agents` and `agent_params` hold the spec and its parameters as columns),
  * the environment by `fingerprint.environment_hash` (`environments`),
  * the code by the engine and agents hashes (`code_versions`; identical hashes are identical code, so a later clean commit with the
    same hashes upgrades a dirty record's provenance).
`record_run` looks every seed up first and computes only the missing ones, so asking for a run that exists costs nothing. A `run`
is one call (agent, environment, tag); `run_episodes` links it to every episode it used, computed or reused, so a tag finds exactly
what that call saw. Episodes are never updated: `delete_run` removes what a run computed (and the links to it).

An episode of kind "interlude" is the session played and then the agent's Interlude (the critic frozen), so it carries the session
columns too. `episode_types` holds the Interlude accuracy per trial type, and `episode_fruits` one row per fruit taken in the session (time in session
seconds, bush id, k-th fruit of that bush, reward, running total: the agent's counterpart of the human `fruit` events in events.csv).
`episode_checkpoints` holds, for a run with checkpoints, the Interlude score of a copy of the agent as it was at each checkpoint time (see
sim.run_episode); the episode's own Interlude columns are the score after the whole session. Times are session seconds; unused values are NULL.

Schema changes: bump SCHEMA_VERSION, add the step to MIGRATIONS, never drop data (the file is copied to `<db>.bak-v<old>` first).
"""

import json
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import fingerprint
import specs
from agents import REGISTRY, build_agent

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "results" / "results.sqlite"
SCHEMA_VERSION = 3

SCHEMA_V1 = """
CREATE TABLE agents (
    agent_id TEXT PRIMARY KEY, memory TEXT, critic TEXT, features TEXT, prior TEXT, actor TEXT, choice TEXT, percept TEXT,
    spec_json TEXT NOT NULL
);
CREATE TABLE agent_params (
    agent_id TEXT NOT NULL REFERENCES agents, component TEXT NOT NULL, key TEXT NOT NULL, value,
    PRIMARY KEY (agent_id, component, key)
);
CREATE TABLE environments (
    env_id TEXT PRIMARY KEY, session TEXT NOT NULL, session_hash TEXT NOT NULL, kind TEXT NOT NULL, n_samples INTEGER,
    interlude_hash TEXT, overrides_json TEXT NOT NULL, percept_json TEXT, costs_json TEXT NOT NULL, env_json TEXT NOT NULL
);
CREATE TABLE code_versions (
    code_id INTEGER PRIMARY KEY, engine_hash TEXT NOT NULL, agents_hash TEXT NOT NULL, commit_hash TEXT, dirty INTEGER,
    python TEXT, numpy TEXT, first_seen TEXT NOT NULL, UNIQUE (engine_hash, agents_hash)
);
CREATE TABLE runs (
    run_id INTEGER PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents, env_id TEXT NOT NULL REFERENCES environments,
    code_id INTEGER NOT NULL REFERENCES code_versions, tag TEXT NOT NULL, note TEXT, seeds TEXT NOT NULL, n_seeds INTEGER NOT NULL,
    n_computed INTEGER NOT NULL, n_reused INTEGER NOT NULL, created TEXT NOT NULL
);
CREATE TABLE episodes (
    episode_id INTEGER PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents, env_id TEXT NOT NULL REFERENCES environments,
    code_id INTEGER NOT NULL REFERENCES code_versions, seed INTEGER NOT NULL, computed_by INTEGER NOT NULL REFERENCES runs,
    total REAL, n_visits INTEGER, n_fruits INTEGER, walk_time REAL, harvest_time REAL, idle_time REAL, look_time REAL,
    press_time REAL, interlude_trials INTEGER, interlude_accuracy REAL, interlude_bonus REAL,
    UNIQUE (agent_id, env_id, code_id, seed)
);
CREATE TABLE episode_types (
    episode_id INTEGER NOT NULL REFERENCES episodes, trial_type TEXT NOT NULL, accuracy REAL, PRIMARY KEY (episode_id, trial_type)
);
CREATE TABLE run_episodes (
    run_id INTEGER NOT NULL REFERENCES runs, episode_id INTEGER NOT NULL REFERENCES episodes, PRIMARY KEY (run_id, episode_id)
);
CREATE INDEX episodes_by_agent ON episodes (agent_id, env_id);
CREATE INDEX runs_by_tag ON runs (tag);
"""

MIGRATIONS = {      # old version -> SQL script that brings the file to old + 1
    1: """
CREATE TABLE episode_fruits (
    episode_id INTEGER NOT NULL REFERENCES episodes, seq INTEGER NOT NULL, t REAL NOT NULL, bush INTEGER NOT NULL, k INTEGER NOT NULL,
    reward REAL NOT NULL, running_total REAL NOT NULL, PRIMARY KEY (episode_id, seq)
);
""",
    2: """
CREATE TABLE episode_checkpoints (
    episode_id INTEGER NOT NULL REFERENCES episodes, t REAL NOT NULL, interlude_trials INTEGER, interlude_accuracy REAL,
    interlude_bonus REAL, PRIMARY KEY (episode_id, t)
);
""",
}

EPISODE_COLUMNS = ("total", "n_visits", "n_fruits", "walk_time", "harvest_time", "idle_time", "look_time", "press_time",
                   "interlude_trials", "interlude_accuracy", "interlude_bonus")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(obj):
    return specs.canonical_json(obj)


def _sql_value(value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, list):
        return _json(value)
    return value


def component_columns(spec):
    """The component names the `agents` table keeps as columns (None when a component has no such part)."""
    def type_of(part):
        return part.get("type") if isinstance(part, dict) else None

    critic, actor = spec["critic"], spec["actor"]
    return {"memory": type_of(spec["memory"]), "critic": type_of(critic), "features": type_of(critic.get("features")),
            "prior": type_of(critic.get("prior")), "actor": type_of(actor), "choice": type_of(actor.get("choice")),
            "percept": type_of(spec["percept"])}


class Store:
    """An open results database. `Store(path)` creates or migrates the file; `readonly=True` opens an existing file without write
    access (use it for analysis)."""

    def __init__(self, path=None, readonly=False):
        self.path = Path(path) if path is not None else DEFAULT_PATH
        self.readonly = readonly
        if readonly:
            if not self.path.exists():
                raise FileNotFoundError(f"no results database at {self.path}")
            self.conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.path)
            self._migrate()
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self.conn.close()

    @property
    def version(self):
        return self.conn.execute("PRAGMA user_version").fetchone()[0]

    def _migrate(self):
        version = self.version
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"{self.path} has schema version {version}; this code knows up to {SCHEMA_VERSION}")
        if version == 0:
            with self.conn:
                self.conn.executescript(SCHEMA_V1 + "".join(MIGRATIONS[v] for v in range(1, SCHEMA_VERSION))
                                        + f"PRAGMA user_version = {SCHEMA_VERSION};")
            return
        if version < SCHEMA_VERSION:
            self.conn.close()
            shutil.copy(self.path, self.path.with_name(self.path.name + f".bak-v{version}"))
            self.conn = sqlite3.connect(self.path)
            for old in range(version, SCHEMA_VERSION):
                with self.conn:
                    self.conn.executescript(MIGRATIONS[old] + f"PRAGMA user_version = {old + 1};")

    def select(self, sql, params=()):
        """Rows of a SELECT as dicts."""
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    # ---- the things an episode is keyed by -------------------------------------------------------------------------

    def record_agent(self, spec):
        agent_id = specs.spec_hash(spec)
        if self.conn.execute("SELECT 1 FROM agents WHERE agent_id = ?", (agent_id,)).fetchone():
            return agent_id
        cols = component_columns(spec)
        with self.conn:
            self.conn.execute("INSERT INTO agents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                              (agent_id, cols["memory"], cols["critic"], cols["features"], cols["prior"], cols["actor"],
                               cols["choice"], cols["percept"], _json(spec)))
            for component in ("memory", "critic", "actor", "percept"):
                if spec[component] is None:
                    continue
                for key, value in specs.flatten(spec[component]).items():
                    self.conn.execute("INSERT INTO agent_params VALUES (?, ?, ?, ?)", (agent_id, component, key, _sql_value(value)))
        return agent_id

    def record_environment(self, env):
        env_id = specs.spec_hash(env)
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO environments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                              (env_id, env["session"], env["session_hash"], env["kind"], env["n_samples"], env.get("interlude_hash"),
                               _json(env["overrides"]), None if env["percept"] is None else _json(env["percept"]),
                               _json(env["costs"]), _json(env)))
        return env_id

    def record_code(self, code):
        """The id of this code version (engine and agents hashes). A dirty record is upgraded when the same code is later seen on
        a clean commit."""
        dirty = None if code["dirty"] is None else int(code["dirty"])
        row = self.conn.execute("SELECT code_id, dirty FROM code_versions WHERE engine_hash = ? AND agents_hash = ?",
                                (code["engine_hash"], code["agents_hash"])).fetchone()
        with self.conn:
            if row is None:
                cur = self.conn.execute("INSERT INTO code_versions VALUES (NULL, ?, ?, ?, ?, ?, ?, ?)",
                                        (code["engine_hash"], code["agents_hash"], code["commit"], dirty, code["python"],
                                         code["numpy"], _now()))
                return cur.lastrowid
            if row["dirty"] == 1 and dirty == 0:
                self.conn.execute("UPDATE code_versions SET commit_hash = ?, dirty = 0 WHERE code_id = ?", (code["commit"], row["code_id"]))
        return row["code_id"]

    # ---- episodes --------------------------------------------------------------------------------------------------

    def lookup(self, agent_id, env_id, code_id, seeds):
        """{seed: episode row} for the seeds already recorded for this (agent, environment, code version)."""
        seeds = [int(s) for s in seeds]
        if not seeds:
            return {}
        marks = ",".join("?" * len(seeds))
        rows = self.select(f"SELECT * FROM episodes WHERE agent_id = ? AND env_id = ? AND code_id = ? AND seed IN ({marks})",
                           (agent_id, env_id, code_id, *seeds))
        return {r["seed"]: r for r in rows}

    def add_episode(self, agent_id, env_id, code_id, seed, run_id, values, by_type=None, fruits=None, checkpoints=None):
        unknown = set(values) - set(EPISODE_COLUMNS)
        if unknown:
            raise KeyError(f"unknown episode column(s) {sorted(unknown)}")
        cols = list(values)
        with self.conn:
            cur = self.conn.execute(
                f"INSERT INTO episodes (agent_id, env_id, code_id, seed, computed_by{''.join(', ' + c for c in cols)}) "
                f"VALUES (?, ?, ?, ?, ?{', ?' * len(cols)})",
                (agent_id, env_id, code_id, int(seed), run_id, *[values[c] for c in cols]))
            episode_id = cur.lastrowid
            for trial_type, accuracy in (by_type or {}).items():
                self.conn.execute("INSERT INTO episode_types VALUES (?, ?, ?)", (episode_id, trial_type, float(accuracy)))
            self.conn.executemany("INSERT INTO episode_fruits VALUES (?, ?, ?, ?, ?, ?, ?)",
                                  [(episode_id, seq, float(t), int(bush), int(k), float(reward), float(total))
                                   for seq, (t, bush, k, reward, total) in enumerate(fruits or [])])
            self.conn.executemany("INSERT INTO episode_checkpoints VALUES (?, ?, ?, ?, ?)",
                                  [(episode_id, float(t), int(n), float(acc), float(bonus))
                                   for t, (n, acc, bonus) in sorted((checkpoints or {}).items())])
        return episode_id

    def checkpoints(self, episode_id):
        """One episode's checkpoint scores by time: dicts with t, interlude_trials, interlude_accuracy, interlude_bonus."""
        return self.select("SELECT t, interlude_trials, interlude_accuracy, interlude_bonus FROM episode_checkpoints "
                           "WHERE episode_id = ? ORDER BY t", (episode_id,))

    def fruits(self, episode_id):
        """The fruits of one episode in the order they were taken: dicts with t, bush, k, reward, running_total."""
        return self.select("SELECT t, bush, k, reward, running_total FROM episode_fruits WHERE episode_id = ? ORDER BY seq", (episode_id,))

    def delete_run(self, run_id):
        """Remove a run, the episodes it computed and every link to them (other runs that reused those episodes lose them too).
        For a run that should never have been recorded; returns the number of episodes removed."""
        with self.conn:
            ids = [r[0] for r in self.conn.execute("SELECT episode_id FROM episodes WHERE computed_by = ?", (run_id,))]
            for episode_id in ids:
                self.conn.execute("DELETE FROM episode_types WHERE episode_id = ?", (episode_id,))
                self.conn.execute("DELETE FROM episode_fruits WHERE episode_id = ?", (episode_id,))
                self.conn.execute("DELETE FROM episode_checkpoints WHERE episode_id = ?", (episode_id,))
                self.conn.execute("DELETE FROM run_episodes WHERE episode_id = ?", (episode_id,))
                self.conn.execute("DELETE FROM episodes WHERE episode_id = ?", (episode_id,))
            self.conn.execute("DELETE FROM run_episodes WHERE run_id = ?", (run_id,))
            self.conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        return len(ids)

    def run_episodes(self, run_id):
        """The episodes a run used (computed or reused), by seed, each with its per-type Interlude accuracies under `by_type`."""
        rows = self.select("SELECT e.* FROM episodes e JOIN run_episodes r USING (episode_id) WHERE r.run_id = ? ORDER BY e.seed", (run_id,))
        for row in rows:
            row["by_type"] = {t["trial_type"]: t["accuracy"] for t in
                              self.select("SELECT trial_type, accuracy FROM episode_types WHERE episode_id = ?", (row["episode_id"],))}
        return rows


# --------------------------------------------------------------------------------------------------
# Running and recording
# --------------------------------------------------------------------------------------------------

@dataclass
class RunReport:
    run_id: int
    agent_id: str
    env_id: str
    code_id: int
    tag: str
    seeds: list
    rows: list                 # episode rows by seed (with `by_type`)
    n_computed: int
    n_reused: int
    code: dict = field(default_factory=dict)

    @property
    def totals(self):
        return np.array([r["total"] for r in self.rows], dtype=float)


def _factory(agent):
    """A zero-argument agent factory from a factory, a registry name or a spec dict."""
    if isinstance(agent, str):
        return REGISTRY[agent]
    if isinstance(agent, dict):
        return lambda: build_agent(agent)
    return agent


def record_run(agent, session, seeds, tag, *, note=None, kind="session", percept=None, overrides=None, n_samples=200,
               interlude_mode=None, checkpoints=None, store=None, progress=None):
    """Run `agent` (a factory, a registry name or a spec dict) on one world per seed and record it, computing only the seeds that are
    not already recorded for this agent, environment and code version. kind="interlude" also evaluates each agent on that world's
    Interlude (n_samples repeated choices per trial; `interlude_mode` "designed" or "random", None = the asset's own; the trial count is
    the override interlude_trial_count) and records the accuracy. `checkpoints` (kind interlude, session times in seconds) also scores a copy of the agent as
    it was at each time, a learning curve from one session per seed; refused for an agent that plans for the end of the session. `store` is a Store (default: the project database,
    opened and closed here). Returns a RunReport."""
    if store is None:
        with Store() as own:
            return record_run(agent, session, seeds, tag, note=note, kind=kind, percept=percept, overrides=overrides,
                              n_samples=n_samples, interlude_mode=interlude_mode, checkpoints=checkpoints, store=own, progress=progress)
    import sim
    seeds = [int(s) for s in seeds]
    if len(set(seeds)) != len(seeds):
        raise ValueError("duplicate seeds")
    factory = _factory(agent)
    spec = factory().spec()
    overrides = dict(overrides or {})
    env = fingerprint.environment(session, overrides, percept, kind, n_samples if kind == "interlude" else None, interlude_mode, checkpoints)
    code = fingerprint.code_version()
    agent_id = store.record_agent(spec)
    env_id = store.record_environment(env)
    code_id = store.record_code(code)

    have = store.lookup(agent_id, env_id, code_id, seeds)
    missing = [s for s in seeds if s not in have]
    with store.conn:
        cur = store.conn.execute("INSERT INTO runs VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                 (agent_id, env_id, code_id, tag, note, ",".join(map(str, seeds)), len(seeds), len(missing),
                                  len(seeds) - len(missing), _now()))
    run_id = cur.lastrowid

    def finalize(done, interrupted=None):
        """Link the run to the episodes of `done` seeds (a run cut short keeps what it computed and says so)."""
        found = store.lookup(agent_id, env_id, code_id, done)
        computed = len([s for s in done if s in missing])
        with store.conn:
            store.conn.executemany("INSERT INTO run_episodes VALUES (?, ?)", [(run_id, found[s]["episode_id"]) for s in done])
            store.conn.execute("UPDATE runs SET seeds = ?, n_seeds = ?, n_computed = ?, n_reused = ?, note = ? WHERE run_id = ?",
                               (",".join(map(str, done)), len(done), computed, len(done) - computed,
                                " ".join(x for x in (note, f"[interrupted: {interrupted}]" if interrupted else None) if x) or None,
                                run_id))
        return computed

    done = [s for s in seeds if s in have]
    try:
        worlds = sim.get_worlds(session, missing, **overrides) if missing else []
        for seed, world in zip(missing, worlds):
            player = factory()
            res = sim.run_episode(player, world, percept=percept, checkpoints=env.get("checkpoints", ()))
            values = {"total": res.total, "n_visits": res.n_visits, "n_fruits": res.n_fruits, "walk_time": res.walk_time,
                      "harvest_time": res.harvest_time, "idle_time": res.idle_time, "look_time": res.look_time,
                      "press_time": res.press_time}
            by_type, scores = None, {}
            if kind == "interlude":
                sidecar, bonus, practice = sim.get_interlude(session, seed, env["interlude_mode"], **overrides)
                score = sim.evaluate_interlude(player, sidecar, bonus, practice, n_samples=n_samples)
                values.update(interlude_trials=score.n_trials, interlude_accuracy=score.accuracy, interlude_bonus=score.bonus)
                by_type = score.by_type
                for t, snapshot in res.snapshots.items():
                    cs = sim.evaluate_interlude(snapshot, sidecar, bonus, practice, n_samples=n_samples)
                    scores[t] = (cs.n_trials, cs.accuracy, cs.bonus)
            store.add_episode(agent_id, env_id, code_id, seed, run_id, values, by_type, res.fruits, scores)
            done.append(seed)
            if progress is not None:
                progress(seed, res.total)
    except BaseException as exc:
        finalize(sorted(done), interrupted=type(exc).__name__)
        raise
    finalize(seeds)
    return RunReport(run_id, agent_id, env_id, code_id, tag, seeds, store.run_episodes(run_id), len(missing),
                     len(seeds) - len(missing), code)
