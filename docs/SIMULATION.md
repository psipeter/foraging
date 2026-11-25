# Simulation: the results database, the battery, the agents

Moved out of `CLAUDE.md` on 2026-11-19 (it was the "Results database" section, verbatim). Read it before running or querying simulated agents.
**Do not edit `scripts/sim.py`, `costs.py`, `perception.py`, `world.py`, `tiles.py` (`ENGINE_FILES`) or `agents.py`, `specs.py` (`AGENT_FILES`)
casually: their bytes are hashed into every recorded result, so even a comment edit moves the code hashes (a false alarm is the safe error); batch
such edits and say so in the commit message.** The rule "do not re-run baselines automatically" (mark SCIENCE baselines stale after a config change; run
`sim.py` only when asked) also applies.

## Results database (`results/results.sqlite`, schema v4; specs, fingerprints, recording and query helpers are built)
A SQLite file of every simulated-agent run, so previous runs can be queried instead of re-run. `results/` is at the repo root,
flat (no subfolders), gitignored, and separate from `ForagingData/` (participant data). Humans use a separate scheme, not this
database. Design rationale and rejected alternatives: `docs/DECISIONS.md` ("Results database").

**Identity and names**
- An agent's identity is the first 12 hex characters of the SHA-256 of its canonical spec JSON (sorted keys, defaults
  resolved; numbers by value, so `10` and `10.0` agree). Every component derives from `specs.Component` and reports `{"type": ClassName,
  <parameter>: <value>, ...}` through `spec()` (nested components are nested specs; a class that replaces `None` by a default overrides
  `params()` to report the effective value); `ComposedAgent.spec()` joins the four and `agents.build_agent(spec)` rebuilds the agent.
  Only library classes (`agents.py`, `perception.py`) build from a spec by name; a component defined elsewhere is passed in `extra`.
- **Names are labels, not data.** Never use a name as a key. When reporting, build the label from the spec showing only the fields
  that differ among the agents in the table (`alpha=0.2` vs `alpha=0.5`; `rbf` vs `ssp`). Old registry names (`nearest`,
  `greedy_rate_15`) stay as aliases that build the *current* spec of that name: `nearest` is now the view-cone agent and `delta_rate_10`
  has the ConstantPrior default, so results recorded under their old definitions are selected by agent id, not by alias.
- An experiment is referred to by its `tag` (free text, e.g. `alpha-sweep-1`). In docs, describe an agent in words (components and
  parameters) plus the tag; a hash appears only where a result must be re-found.

**What is stored** (one row per world seed in `episodes`; no traces; no derived metrics)
- `agents` (hash, component names, spec JSON) and `agent_params` (one row per component/key/value, to query by parameter).
- `environments` (`fingerprint.environment`): session, a hash of the resolved session parameters the simulator reads
  (`fingerprint.SIM_FIELDS`; audio, visuals and the world seed are excluded, so a temporary 15 s duration is visible and an
  Inspector tweak of a volume is not), overrides,
  percept, kind (always `session` since the cleanup of 2026-11-14), motor-cost constants. `code_versions`: a hash of the engine files
  (`sim.py`, `costs.py`, `perception.py`, `world.py`, `tiles.py`), a separate hash of `agents.py`, git commit and dirty flag.
- Schema v4 (2026-11-14) only adds a `schema_notes` table: the Interlude's `episode_checkpoints` table and the Interlude columns of `episodes` stay in old files, unused (a migration never drops data; the old file is copied to `.bak-v<old>` first). Every environment and engine hash changed with the cleanup, so results recorded before it are stale.
- `episode_fruits` (schema v2): one row per fruit taken in the session (`t` in session seconds, `bush`, `k`, `reward`, `running_total`),
  the agent's counterpart of the human `fruit` events in `events.csv`; read with `Store.fruits(episode_id)` or
  `analysis.fruit_events(store, sel, agent, seed)`. No positions, headings or other actions.
- `runs` (agent, environment, code version, tag, time) and `episodes` (total, visits, fruits, walk/harvest/idle/look/press
  time). Unique on (agent, environment, code version, seed).
- A stochastic agent's own seed is part of its record, since results are only reproducible given it.

**Using it**
```bash
./venv/bin/python scripts/sim.py FIX_T0 --seeds 0-99 --agents nearest,delta_rate_10 --record --tag my-experiment [--note "..."] [--set session_duration=90] [--db PATH]
```
`record_run(agent, session, seeds, tag, note=, percept=, overrides=, store=)` in `scripts/results.py` does the same from
Python (`agent` = factory, registry name or spec dict). It looks every seed up by (agent, environment, code version) and
computes only the missing ones; a cut-short run (Ctrl-C, an exception) keeps what it computed, links it to the run and notes
`[interrupted]`. `Store(path, readonly=True)` opens the file for analysis (`select(sql, params)` returns dicts). The agent's own
random stream comes from the world seed, so a result is reproducible from its key; a custom `agent_rng` cannot be recorded.

**Querying with `scripts/analysis.py`** (read-only; open with `Store(path, readonly=True)`)
```bash
./venv/bin/python scripts/analysis.py runs [--tag T]
./venv/bin/python scripts/analysis.py table  --tag T [--baseline nearest] [--metric total] [--engine current|any|HASH]
./venv/bin/python scripts/analysis.py effect --tag T --factor critic.alpha [--reference 0.5]
```
- `select(store, tag=, session=, kind=, env_id=, overrides=, agents=, engine=)` returns one comparable set: exactly one environment and
  one code version per episode, or it raises `SelectionError` saying what to narrow. Only the current engine code is searched by
  default; an older or mixed selection carries `notes` ("stale", "agents.py changed", "dirty tree") that a report must repeat.
  `describe`/`format_table` print the header a report needs (session, overrides, sensor, seeds, metric, tag, environment, engine,
  agents hash, commit, dirty).
- `table` gives mean, std, se per agent and, against a `baseline` (id, registry name, spec or agent), the paired difference with its
  standard error and number of pairs (only seeds both agents have). Labels come from `specs.labels`: only the fields that differ.
- `component_effect(sel, factor)`: `factor` is a path into the spec (`critic.alpha`, `critic.features`, `actor.choice`, `critic`);
  everything under the path is the factor, agents are matched on every parameter outside it, and each matched group gives paired
  differences to its reference level; the summary averages over groups (standard error across groups, so it needs two or more).
  Agents that differ in anything else are never compared by it. Use it instead of eyeballing a table when more than one thing varies.
- `cumulative_curve(store, sel, step=1, baseline=None)`: reward collected so far against session time (ends at the episode's total; the
  default of `analysis.py curve`), mean and 95% t-interval across seeds. With a `baseline` (`curve --baseline nearest`) each agent's curve is
  the paired difference to the baseline's cumulative reward in the same worlds (the baseline is left out): flat at zero until an agent
  starts beating it, then rising. (A reward-rate curve with binning or low-pass smoothing was built and removed: too hard to read, flat and
  wiggly with the world's layout; see DECISIONS.)
- **Figures are grids of panels, one per session** (2 x 2 for the battery's T1-T4): `plots.plot_cumulative_reward(panels, path, names=, order=)`
  takes `{session: curves}` (or one curves object) and draw each agent with `seaborn.lineplot` from the per-seed
  curves (`plots.long_form`): mean and 95% bootstrap interval across seeds, `hue` = agent name, the same colour for the same agent in every
  panel, one shared legend, one linestyle per agent as well as one colour (`plots.SERIES`, `plots.STYLES`), at most 8 agents per figure (the palette) and a warning above 5 (`plots.MAX_DISTINCT`). The advantage figure uses the **lowest-performing agent of each session**
  as its baseline (`cumulative_curve(..., baseline="lowest")`, `curve --baseline lowest`). For the battery, `battery.py plot --tag T --population P [--kinds reward,advantage]` saves one figure per kind as
  `results/<tag>_<population>_<kind>.png`; each population (all including `nearest`; more than 5 agents warns) is one figure group, except that the `scan-*`, `explore-*`, `delta-*` and `learners` figures leave out `nearest` and `oracle` (`battery.FIGURE_OMITS`; the figure then holds up to 6 or 7 agents, past the 5-agent warning and within the palette's 8; they stay in the population for `scores`), so their advantage baseline is the lowest learner.
- **Figure size and font conventions** (`plots.MODES`, from the evidence_integration project's `utils/plot_style.py` / `make_figures.py`): `mode="paper"`
  (default; `battery.py plot --mode`) is 6.5 in wide (a letter-page `\textwidth`) with 9 pt text (axis titles 10, ticks and legend 8, axes 0.8 pt,
  lines 2 pt, 300 dpi); `mode="presentation"` is 10.6 in wide with 15 pt text (labels 17, titles 18, ticks 13, legend 14, axes 1.2 pt, 200 dpi). Height is
  `rows * panel_height + extra_height` (foraging's own values), and the title, subtitle, legend and footer are placed from the font sizes (`plots._margins`).
  Seaborn's `ticks` theme, no gridlines, shared x axes across panels (the reward and advantage panels have their own y axes, since sessions differ in maximum reward). Battery figures are saved as `<tag>_<population>_{reward,advantage}.png`. Unlike evidence_integration, figures are PNG, not SVG.
- **Figure colour conventions** (`plots.SERIES`, `plots.STYLES`, `plots.MAX_DISTINCT`; rationale and the recipe that generated the palette in
  `docs/DECISIONS.md`, "Figure colours"): at most **5 agents per figure** (a warning above that; the palette holds 8 as a hard limit), each agent keeps one colour **and**
  one linestyle in every panel and figure; a new plot type must take its colours from `plots.SERIES` in order (lines also `STYLES`; scatter
  adds a marker per agent) and never hard-code colours. Colour is never the only channel for line or scatter plots. Check a new figure under simulated
  colour-blindness (deuteranopia, protanopia, tritanopia) before relying on it, and do not change the palette without re-measuring the worst pair.

**The assessment battery** (`scripts/battery.py`; "battery" because "test suite" already means pytest). One definition of how agents are compared:
the labels T1 to T4 of the one frozen tiles session `FIX_T0`, at the durations of the default `long` battery (60, 90, 120, 120 s, passed as `session_duration` overrides; `--battery standard` is the shorter 45, 60, 60, 90 s one), each label on its own worlds (world seeds shifted by 100 per label); reward only since the cleanup of 2026-11-14 (the
Interlude half and the checkpoint scores are gone, and no selection evaluation exists yet; the environment is a frozen tiles session); 10 seeds by default; each agent starts fresh in every session.
```bash
./venv/bin/python scripts/battery.py list
./venv/bin/python scripts/battery.py run --population main --tag <name> [--agents a,b,...] [--seeds 0-9] [--db PATH]   # records <name>/<session> runs
```
It is just `record_run` per agent per session, sessions as the outer loop. Populations (`POPULATIONS`: `main` = `nearest`, `oracle`, `learner`, the standard agents; the GP critic (`gp_mean`) and the exploration policies are in `learners`, `explore-noise`, `explore-bonus` and `explore-posterior` (GP critic), `delta-noise` and `delta-bonus` (the same actors on the delta-rule critic) and the one-parameter `scan-*` populations (each includes `gp_mean` as its reference); `learner-parameters`, `choice-noise` and `knowledge` are
the investigations; names are labels, identity is the spec hash) live in `battery.py`, not `agents.py`, so editing them does not move the agents-code hash.
**Standard agents:** the actor is the rate utility within 15 s of walking and the map comes from the view cone (`FullMemory`); `whole_map=True` gives the
full-information variant, and the registry's `greedy_*` entries stay full-information benchmarks. **Scores and plots are deliberately not part of the run**: they are
computed from the database afterwards: `battery.py scores --tag T --population P` prints, per session and agent, the paired reward lead over `nearest`
(in reward points, with its standard error), its split into **quality** (picks better bushes) and **efficiency** (takes more fruits) with fruits and reward per fruit,
there is no
normalised score (no share of a floor-to-ceiling gap): see DECISIONS, "What a score is for".

**Adding things**
- *A parameter on a component:* give it a default and include its resolved value in `spec()`. This changes the hash of every agent
  using the component, so run the re-hash migration (it recomputes ids from the stored spec JSON; nothing is lost). Never edit
  `spec_json` or `agent_params` rows by hand.
- *A new kind of component:* a new `type` string. Never reuse a type name for different behavior; if behavior changes under an
  unchanged spec, the `agents.py` hash will differ, so say so in the commit message and rename the type if old results should not be
  pooled with new ones.
- *A new `episodes` column:* add at the end, nullable; old rows stay NULL (not 0). Never change what an existing column means. Prefer
  a metric computed at query time to a stored one (the performance metric is still a TODO(PI)).
- *Schema changes:* bump `schema_version`, write the migration in `scripts/results.py`, never drop data, and copy the file before
  migrating (it is not in git).
- *Environment changes* (session assets, reward function, terrain) change the environment hash on their own; nothing needs
  invalidating by hand.
- *The simulator starts reading another SessionConfig field:* add it to `fingerprint.SIM_FIELDS` (every environment hash then changes).
  `test_sim_fields_cover_every_session_parameter_the_simulator_reads` traces a run and fails until you do.
- *Code hashes* are of file bytes (`ENGINE_FILES`: sim, costs, perception, world, tiles; `AGENT_FILES`: agents, specs), so even a
  comment edit moves them (a false alarm is the safe error); `dirty` means a hashed file differs from HEAD or is untracked.

**Querying**
- Use the helpers in `scripts/results.py` or parameterized SQL, and open the file read-only for analysis. Never UPDATE or
  DELETE `episodes` by hand; remove a bad run by `run_id` through the helper and say you did.
- **Look up before running.** A lookup of an existing (agent, environment, code version, seed) is free. Do not re-run baselines
  unprompted (see above); run new agents or new conditions when asked.
- Compare agents on identical environment and seeds and pair on seed: report the paired mean difference with its standard error,
  not two unpaired means.
- Default to results from the current engine hash; when citing older ones, say so. Treat a different engine hash as stale, not as
  wrong.
- A report states: session and duration (check for temporary overrides), number of seeds, tag, short engine hash, and whether the
  tree was dirty. Prefer a clean-tree run before a result goes into a doc.
- Compare components by holding the others fixed (agents that differ in exactly one parameter or component), via `agent_params`.
- The agent/human performance metric is not decided: store raw scores, compute any metric at query time, and name it in the report.
