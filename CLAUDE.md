# CLAUDE.md — foraging

Source of truth for conventions and workflow. For the scientific goals,
task design, and open questions, see `docs/SCIENCE.md`. For why past design choices were
made (including rejected alternatives, and the old planned experiments FN, RW, FI, PL, PA and the 2026-11-14 cleanup: historical entries), see `docs/DECISIONS.md`. `README.md` is a short
human-facing description only. Read this file fully before making changes. Reference detail lives elsewhere:
`docs/CODEMAP.md` (every file), `docs/SIMULATION.md` (results database, battery, agents), `docs/ONLINE_DATA_PLAN.md` (online data, "Data logging (as built)"),
`docs/REGENERATING.md` (regeneration recipes).

---

## Session-start checklist

- **Research tool first, game second.** Ecological validity, perceptual
  clarity of bush attributes, and unambiguous reward feedback outrank
  aesthetic polish or gameplay complexity.
- **Drive the open Editor with the Unity CLI** (see "Driving the Unity
  Editor" below) instead of asking the person to click through the UI. If no
  Editor is open or it won't connect, say so — don't claim a change "works"
  from reading code alone, and don't silently fall back to hand-editing.
- **Don't hand-edit scene/prefab/asset YAML.** Use CLI commands
  (`set_serialized_field`, `add_component`, ...). The scene has ~100
  cross-referenced objects; hand edits can corrupt IDs. Never touch `.meta`
  files (Unity generates them; commit them with any new asset).
- **Uncommitted Inspector churn is normal** (`.asset`/`.mat` diffs from the
  person tweaking values). Don't revert it or fold it into your own commits.
- **`ForagingData/` currently holds only debugging output** (no dev or
  participant data has been collected). It is gitignored and not backed up by
  git. Once real collection starts, treat it as read-only participant data.
- Ignore `Library/`, `Builds/`, `Logs/`, `diagnostic.log`, and the
  generated `*.csproj`/`*.slnx` files when searching.
- **The menu offers `TUT` (the tutorial, one practice session) and the pilots `PCX`, `PSC` and `PSP`** (foraging in hexagonal tiles; each session alternates foraging with ranking phases, "ranking breaks"; `docs/SCIENCE.md` "Current design"). TUT must be
  finished before a pilot unlocks. `FOR` (`FOR_S1`) is only the template session the designs copy; it is not in the catalog. The old tutorials, experiments (the old TUT, FN, RW, FI) and the Interlude were removed on 2026-11-14 (`docs/DECISIONS.md`, "Cleanup: everything is FOR", has the glossary of old to new names; tag `pre-cleanup` holds the old code); the present TUT is the new tutorial built on 2026-11-14 to 16. Nothing is called an Interlude.

---

## Stack and environment

- Unity **6000.3.12f1** (URP) — authoritative value is
  `ProjectSettings/ProjectVersion.txt`; C# 9.0
- New Unity Input System (`PlayerInput`, Invoke Unity Events)
- Targets PC (Linux/Windows standalone) and **WebGL** for online participants (`docs/ONLINE_DATA_PLAN.md`, "Deploying the game"). Linux dev machine.
- Git/GitHub; single branch `main`.

---

## Driving the Unity Editor

Tool: the Unity CLI (`~/.local/bin/unity`, not on Claude's PATH — call it by
full path; beta). It controls a **running Editor** through the project's
`com.unity.pipeline` package (experimental, installed in `Packages/`).
Authoritative docs: `unity skill show`; list commands with
`unity command --query <term> --detail full`.

```bash
U="$HOME/.local/bin/unity --no-banner --no-pager"
$U status                         # Editor must show state "ready"
$U command recompile              # after every script edit; reports compile errors
$U command console --result-only  # read console (errors/warnings/logs)
$U command get_scene_hierarchy
$U command get_serialized_fields --target Assets/ScriptableObjects/Experiments/FOR/FOR_S1.asset
$U command set_serialized_field --target <asset> --field rewardStd --value 0.3
$U command eval 'return 1+1;'     # arbitrary C# (needs `return`); can call project code
$U command capture_game_view --source camera --save_path Assets/Temp/x.png
```

Syntax is `unity command <name> --param value`. Run a command with no
arguments to see its required parameters — **but many commands act
immediately** (`editor_play` entered Play mode when called bare), so look
parameters up with `--query` first.

Rules:
- **After editing C#:** run `recompile`, then check `console_status` /
  `console` for errors. If the Editor boots with compile errors it enters
  Safe Mode and the CLI can't connect — fix the code and restart Unity.
- **Edit assets through the CLI**, then `save_all`. Don't change assets the
  person has open mid-edit; try changes on a copy (`copy_asset`) first when
  unsure, and delete the copy.
- **Screenshots save under `Assets/`** (the authoring root, outside it is
  refused). Save to `Assets/Temp/`, view it, then `delete_asset --asset
  Assets/Temp --confirm true` so no image or `.meta` is left behind.
- **Verify behavior, not just compilation:** enter Play mode, confirm the game
  is advancing (e.g. `eval 'return UnityEngine.Time.frameCount;'` twice), read
  the console, capture a frame, then `editor_stop`. Always leave Play mode.
- **Destructive commands** (`delete_asset`, `clear_*`, `package_remove`)
  need `--confirm true`; only run them on things Claude created or the person
  named. Package changes alter `Packages/` — ask first.
- **Temporary editor scripts** (large batch edits via `eval_file`/`create_script`)
  go in `Assets/Editor/TemporaryGeneratedScripts/` and are deleted at the end.
- **A WebGL build switches the Editor's active build target** (`switch_build_target --target WebGL`; reimport, then the build takes minutes, release builds longer) and must be switched back (`StandaloneLinux64`) afterwards; check `list_open_scenes` for unsaved work first. Build with `build --target WebGL --options '["Development"]'` for a development build, none for release. Code under `#if UNITY_WEBGL` is not compiled by a Linux build: prefer runtime checks (`Application.platform`, `StreamingData.NeedsPreload`).
- **A new `SessionConfig` field's default does not reach assets already loaded in the open Editor, and changing a default later does not either** (they keep the
  in-memory value; a restart or a reimport picks it up). After adding or changing a field, read it back with `get_serialized_fields` and set it with
  `set_serialized_field` on the asset being tested (and in the design file, so a rebuild keeps it).
- **Failures** (timeout, connection drop, Editor quit, never reaches `ready`):
  report what you ran and what failed; don't retry in a loop or fall back to
  editing YAML. Offer `unity bug` but never run it unasked (it sends logs).
- Unity prints a benign `Unrecognized thread niceness ... setpriority` error
  on Linux; ignore it.
- There are **no tests yet**. Real EditMode tests would need the game scripts
  moved into an assembly definition (test assemblies can't reference
  `Assembly-CSharp`). `unity test` runs but finds 0 tests.

**Editor closed? Use headless batch mode** (verified working with the
Personal license; each call spawns a batch Editor, so the project must NOT be
open in another Editor — the project lock will refuse it):
- `unity test <project> --mode EditMode --output <file>.xml` — ~15 s; also a
  compile check: compile errors abort with a nonzero exit (6) and
  "Scripts have compiler errors" (details in the Editor log).
- `unity build <project> --target StandaloneLinux64 -o <dir>/foraging` —
  ~40 s; does not modify the project. Write output outside the repo (e.g. the
  scratchpad), not to `Builds/`.
Headless can't do Play mode/screenshots/scene edits; use the live-Editor
commands above for those. Never close the person's open Editor without
`save_all` and a clean `list_open_scenes` first (`unity close` exits without
saving). After headless runs, the next Editor launch may open an empty
"Untitled" scene (Hierarchy looks wiped; the scene file is fine) — tell the
person, and restore with `open_scene --path Assets/Scenes/SampleScene.unity`.

### Playing the game without touching the person's desktop

Real keyboard/mouse input goes to whichever window is focused, and the Editor
drops keyboard input and throttles when unfocused — so **never use `xdotool`
on the person's display (`:1`) and never drive Play mode with
`simulate_key`** (it did not register; Space on the instructions screen was
ignored). Instead play a **standalone build on a private virtual display**:

1. Build with the live Editor: `unity command build --target StandaloneLinux64
   --outputPath <scratchpad>/xbuild/foraging --confirm true`, poll
   `build_status` (~40 s). Outputs outside the repo; `ForagingData/` for that
   run lands next to the build, not in the project.
2. `Xvfb :99 -screen 0 1280x720x24 +extension GLX &`, then from the build dir
   `DISPLAY=:99 ./foraging -screen-fullscreen 0 -screen-width 1280
   -screen-height 720 -force-glcore -logFile <log>` (renders fine with Mesa
   software GL).
3. Drive it with `DISPLAY=:99 xdotool` (window id via `xdotool search --class
   foraging`; `windowfocus` it; `keydown`/`keyup` with a short hold rather than
   a bare `key`). Screenshot with `DISPLAY=:99 import -window root x.png`.
4. Navigate closed-loop from the game's own logs: `trajectory.csv` (position,
   yaw, session time) and the world file (`scripts/replay.py` loads the bush table). Calibrate mouse-turn gain first (heading degrees per px);
   un-calibrated turning oscillates and burns the session (60-150 s). Session time
   ticks in real time, so keep per-step latency low.
5. Verify with `events.csv` (`fruit` rows) against screenshots, and run `scripts/replay.py <folder>`.
6. Clean up: kill the player and `Xvfb :99` by PID (`pkill -f` with a pattern
   that appears in your own command line kills your shell).

Facts learned: harvest starts within `harvestRangeGapBase` (7) of the canopy edge, i.e. 7 + the canopy
radius from the tree's center (wide canopies block the player earlier); Enter on the last session's end screen
returns to the experiment menu (after an experiment played directly, the offline menu).


## Repository structure

One line per directory; the file-by-file description is `docs/CODEMAP.md`. **Keep `docs/CODEMAP.md` in sync when files are added, moved, or retired.**

- `Assets/Scripts/Player|Trees|World|Session|UI|Data/` — the game: player and camera; bushes and fruit; world loading and terrain; `SessionConfig` (ALL parameters), `GameManager`, `RankingBreak`, menu, `HarvestManager`; HUD, popups, tutorial hints, crosshair; `DataLogger`, `DataPipeline`, sinks, `PauseGate`.
- `Assets/ScriptableObjects/Experiments/<code>/` — one folder per experiment (`<code>.asset` and `<code>_S<n>.asset`); `FOR_S1` is the template session, `TUT`, `PCX`, `PSC`, `PSP` are in the menu. Made by `scripts/build_experiment.py` from `scripts/design/<code>.py`.
- `Assets/StreamingAssets/Experiments/<code>/` — what one experiment downloads: instruction texts, generated `<session>_seed<N>.world` and `.ranking.json`. Shared texts (consent, introduction, resume) at the root.
- `Assets/Editor/` — `BuildInfoWriter`, `ExperimentBuilder`, `ExperimentPlayer`, `SessionPreview`; `Assets/Shaders/`, `Materials/`, `Prefabs/`, `Audio/Ambient/`, `Scenes/SampleScene.unity` (the single scene).
- `supabase/` — migrations, Edge Functions, local server (deploy: `docs/ONLINE_DATA_PLAN.md`).
- `docs/` — `SCIENCE.md`, `DECISIONS.md`, `ONLINE_DATA_PLAN.md`, `SIMULATION.md`, `REGENERATING.md`, `CODEMAP.md`, `REVIEW_POLICY.md`, `SESSION_FACTORS_PLAN.md`, `pilots/`.
- `.claude/` — agents (simplifier, red-team, arbiter) and the adversarial-review skill.
- `scripts/` (Python, `./venv/bin/python`; `venv/` and `worlds/` gitignored) in groups:
  worlds (`world.py`, `tiles.py`, `ranking.py`, `value_maps.py`, `factors.py`, `cells.py`, `design/`, `build_experiment.py`);
  logged data (`replay.py`, `visibility.py`, `rundata.py`, `human_data.py`, `validate_run.py`, `trajectory_codec.py`);
  simulator and agents (`sim.py`, `perception.py`, `costs.py`, `agents.py`, `specs.py`, `battery.py`, `results.py`, `analysis.py`, `plots.py`, `fingerprint.py`, `patch_foraging.py`, `agent_benchmark.py`, `pilot_report.py`);
  online and deployment (`database.py`, `server_*.py`, `load_test.py`, `webgl_smoke.mjs`, `deploy_webgl.sh`, `perf_*`);
  tests and review (`test_*.py`, `run_tests.py`, `conftest.py`, `synthetic.py`, `fixtures/`, `mutation_check.py`).
- **Hash-sensitive files:** `ENGINE_FILES` (`sim.py`, `costs.py`, `perception.py`, `world.py`, `tiles.py`) and `AGENT_FILES` (`agents.py`, `specs.py`) are hashed into every recorded simulation result: even a comment edit moves the hashes. Edit them only when needed and batch the edits (`docs/SIMULATION.md`).
- **Mirrored pairs (change both):** `HarvestManager` range/bearing/timer rules with `replay.py` (camera, canopy and terrain sampling also with `visibility.py`); `RankingBreak` timing, blocks and events with `replay.py` and `visibility.py`; `RankingSets.ScorePairs` / `PairWeight` with `ranking.rankings_to_points`; `scripts/world.py`'s placement, attribute and reward rules with the C# generator-side rules `WorldData` reads.

---

## Architecture principles

- **`GameManager` is the single point of `SessionConfig` assignment.**
  Never wire a `SessionConfig` in the Inspector on individual components;
  `GameManager.Awake()` (execution order -20) distributes the active config.
  It holds the ordered list of session configs and advances through them
  (scene reload between sessions, static `CurrentSessionIndex`).
- **`SessionConfig` is the single source of truth** for every session and
  visual parameter. Never hardcode a value a researcher might want to change.
  Visual ranges (colors, scales) live there too.
- Components that receive the config from `GameManager` use
  `public SessionConfig sessionConfig` (no `[SerializeField]`).
- Inspector-wired references use `[SerializeField] private`.
  `[SerializeField] public` is never correct.
- New config parameter = `[SerializeField] private` field with a default,
  plus a public read-only property, under the right `[Header]`.
- Game events are C# `Action`s, not UnityEvents.
- No `FindObjectOfType`; use direct references (`FindObjectsByType` is
  acceptable for infrequent calls).
- **Worlds are generated in Python, not Unity.** `scripts/world.py` is the source
  of truth for placement, attributes, terrain fields and per-fruit rewards, all from
  one seed; Unity loads the result (`WorldData`) and only renders/plays it. After
  changing any world-shaping SessionConfig value (tile fields, terrain,
  mountains, canopy width/shape ranges, the value map and reward std, fruit count) re-run
  `./venv/bin/python scripts/world.py FOR_S1 --unity`; `GameManager` warns at
  startup when a file is stale. Never hand-edit `.world` files. Fruits are
  runtime-instantiated, never prefab children (their on-bush layout is still seeded
  in C# from `fruitSeed`; it is visual only).
- **A ranking break is part of a foraging session, not a session kind.** `RankingBreak` is created at runtime by `GameManager` (no scene wiring) when `rankingEvery` > 0, the world has tiles
  and the pool file exists; every parameter is a `SessionConfig.ranking*` field. The set always stands on a floating disc drawn by an overlay camera (`RankingDisc`, `docs/DECISIONS.md` "The ranking stage"; the old on-terrain ranking was removed 2026-11-16) and its bushes log a ground height `y` that replay and visibility use (a log without it, from before the stage, falls back to the terrain). A break never sets the camera, writes no shared
  material, moves no score (its bushes pay 0) and holds the session clock through `SunController.ClockHeld`. Outcomes are hidden through `RankingBreak.Active`. **Change `RankingBreak`'s timing, blocks and events
  together with `replay.py` and `visibility.py`.**
- **The harvest rule** is the range plus the crosshair's hidden circle (see "Data logging" below); `HarvestManager.Aimed` and `replay.py`'s `_aimed` are one rule in two languages.
- The reward function is modular and defined entirely in `SessionConfig`
  (per-attribute basis function + weight/peak/width), never hardcoded.
- Layers: `Default` (misc), `Terrain` (ground), `Tree`, `Player`. Collision
  matrix: Player↔Terrain off, Player↔Tree on. Terrain following is a
  downward raycast each `FixedUpdate`, not gravity.
- **What responds to the sun:** the sun's *direction* drives the terrain (`VertexColor.shader`
  lights with `0.15 + 0.85 * shadow * N.L`, ignoring the light's colour and intensity) and the
  fruit shaders; only the canopy (URP Lit), the sky and the ambient probe respond to its colour and
  intensity, and post-exposure affects everything. The scene's ambient source is Skybox, so
  `RenderSettings.ambientLight` has no effect. See `docs/DECISIONS.md` ("Lighting").
- **Never write to a shared material or other asset at runtime** (`sharedMaterial`,
  a material referenced from the scene): in the Editor the change is saved into the
  file after Play and shows up as churn in every commit. Use `new Material(...)` /
  `renderer.material` instances (as `SunController` does for the sky).
- Custom shaders must be in Project Settings → Graphics → Always Included
  Shaders, or `Shader.Find()` returns null in standalone builds.

### Reward system (do not "fix")
`R_bush` = the sum of the session's Gaussian bumps over (shape, color) (the **value map**, `scripts/value_maps.py`; a bump has a centre, a spread along each axis (`width` along shape, `widthColor` along color, 0 = the same), an `angle` that turns it, and a height; the one primitive: the ladder additive / multiplicative / non-separable is positions in its parameters, `docs/SCIENCE.md` "Reward complexity ladder"), **no
normalization**. Moisture never pays (decoration). The ramp components, the product and two-factor terms, the random per-bush value and the moisture reward were removed on 2026-11-17 (`docs/DECISIONS.md`, "Reward function: the Gaussian bump is the only term"). The old `spatialBalance` and `featureBalance` (which dealt records over the lattice to even the reward) are gone from the Python generator (2026-11-13): in a tiles world the features are dealt tile by tile (`scripts/tiles.py`). Per-fruit reward = `max(0, round(Gaussian(R_bush,
rewardStd)))`, sampled independently per fruit and pre-drawn in the world file
(the k-th fruit taken from a bush pays `fruit_reward[bush][k]`); harvest total is the sum.

### Data logging
Full text: `docs/ONLINE_DATA_PLAN.md`, "Data logging (as built)". The invariants:
- **The online database is the default** (`docs/DECISIONS.md` "Online data collection"). `DataLogger` records trajectory frames, events (JSON `payload`), the session row (full `SessionConfig`, world hashes, build) and one `ranking_sets` row per ranking set, and hands them in batches to `DataPipeline`.
- The pipeline **always writes a local copy** under `<project root>/ForagingData/<run id>/<session:00>/` (read by `scripts/rundata.py`) and, when `StreamingAssets/online.json` is enabled, uploads the same rows to Supabase. Uploads are acknowledged; unacknowledged data holds the game behind a message (`PauseGate`). **Only `PauseGate` may set `Time.timeScale`.**
- **The harvest rule** (range plus the crosshair's hidden circle, `SessionConfig.crosshairRadius`) is mirrored by `scripts/replay.py`: **change `HarvestManager`'s range/bearing/timer rules and `replay.py` together** (and the camera, canopy or terrain-sampling rules with `visibility.py`).
- **The table columns and their meaning are fixed once real data exists — changing them breaks downstream analysis and comparability.** Add columns only at the end, and say so.
- The clock `t` is unpaused session seconds; trajectory time is quantized to a microsecond because replay sums frame times.
- **Ranking breaks** hold the session clock; **change `RankingBreak`'s timing, blocks and events together with `replay.py` and `visibility.py`** (a log has `rank_break_start`/`rank_break_end`, `rank_set`, `rank_leaving`; points are `foraging_points` + `ranking_points`).
- **Resume:** a participant returning with the same Prolific ID continues the unfinished run (`DataLogger` restores clock, pose, score, fruits; the log gets `session_resume`, a discontinuity for `replay.py`).
- `BuildInfoWriter` writes the gitignored `StreamingAssets/build_info.json`; the server refuses a commit not registered (`database.py register-release`).

---

## Hard research constraints

- Never rescale or cap a session's reward values inside the session — intentional: no per-fruit cap, no division by a maximum, the points are raw points. A per-session gain chosen at design time to equalise the points earnable across sessions is allowed (PI, 2026-11-17; `docs/DECISIONS.md`, "Reward scale per session").
- Fruit count is constant across all bushes — never vary it per bush.
- Fruit color is the plasma ramp in `SessionConfig.fruitColorRamp` (blue-purple, magenta, orange, yellow), generated by `scripts/fruit_ramp.py`; never hand-edit the stops (`docs/DECISIONS.md`, "Fruit colour ramp").
- Fruits use the **unlit** shader (color must be readable under any
  lighting). Canopy uses **double-sided** URP/Lit. Don't change either.
- Player is a non-kinematic Rigidbody with a zero-friction material.
- `FruitMaterialManager`'s cache intentionally persists across Play sessions.
- Attribute channels must stay visually distinct and independent
  (shape = canopy aspect ratio, color = fruit hue, moisture = ground
  color + elevation). Changes to any visual channel are a *scientific*
  change — propose it, don't just implement it.

---

## Code conventions

- Match surrounding style (naming, brace style, comment density).
- Private fields `_camelCase`; public/serialized members as in existing files.
- Always keep a null-safe fallback where a script can run before
  `GameManager` has assigned its config (existing pattern, e.g.
  `sessionConfig != null ? ... : default`).
- No diagnostic `Debug.Log` left in committed code (a cleanup pass already
  removed them).

---

## Workflow guidelines

### Before making changes
1. Read the relevant scripts fully first.
2. Check `SessionConfig.cs` before adding any parameter.
3. Propose a plan for structural changes before executing.

### Suggesting vs. implementing
When a question or observation implies a change *might* be warranted,
describe it and ask first — especially anything touching the visual
channels, reward system, data format, or session flow (all are scientific
design). Implement immediately only on an explicit request.

### Git and commit messages
The person commits and pushes; never run `git commit`/`git push` unprompted.
Write thorough commit messages for anything diffable — the body is the
primary home for that narrative (`git log --grep`, `git log --follow`).
Reserve `docs/DECISIONS.md` for what git can't hold: rejected alternatives,
design rationale, conclusions reached before code existed. Commit before
starting a large Claude task so the diff is reviewable.

### What to regenerate after a change
The generated files are manual steps (nothing runs them at build time); the recipes and the per-field lists are in `docs/REGENERATING.md`.
- **World-shaping SessionConfig value** (tile fields, terrain, mountains, canopy ranges, value map, reward std, fruit count): `./venv/bin/python scripts/world.py <sessions> --unity`. Unity warns at startup when a world file is stale.
- **An experiment's sessions** (reward function, features, terrain, duration, instruction file, hints): edit `scripts/design/<code>.py`, then `./venv/bin/python scripts/build_experiment.py <code>` (open Editor; `--no-generate`, `--remove-stale`). The engine tests use the frozen `FIX_T0`.
- **Tutorial** (`design/TUT.py`): `build_experiment.py TUT`; a hints file needs no regeneration.
- **Ranking pool** (`ranking*` fields that shape it, or the reward function of a session with rankings): `./venv/bin/python scripts/ranking.py pool <session>`.
- **No regeneration needed:** `targetFrameRate`, `sessionDuration`, `fruitHarvestDuration`, `playerMoveSpeed`, `rankingSeconds`, `rankingBonusPerPair`, audio volumes, instruction text.

### Long-running commands (experiments, regeneration, builds)
Run the real command once with `run_in_background: true` and its output redirected to a log (`... > "$SCRATCH/x.log" 2>&1`); the harness
notifies when that process exits, and only then do you read the log and report. Do not wrap it in `nohup ... &` (the wrapper exits at once
and its "completed" notification is about the wrapper) and do not write watcher loops with `pgrep -f '<pattern>'` (the watcher's own
command line matches the pattern, so it never ends). To see progress, read the log or run `analysis.py runs --tag T`. `sim.py` prints its
results table as its last output, which is the completion marker. This went wrong twice in one session; see the memory note.

### Testing
Full text (policy, what the engine tests use, validator details): `docs/REGENERATING.md`, "Testing (full text)". The rules:
- While iterating run `./venv/bin/python scripts/run_tests.py --fast` (it runs only the test files the changed files can affect; `--dry-run` shows the decision). Run the plain command after touching a session asset, `world.py`, `ranking.py` or the planner, and `--all` (about 13 minutes) before committing.
- **Slow tests (`slow` marker, `--all`) run only when the PI approves, after a major change and before a commit.**
- **Tests state their configuration; they do not name a shipped session** (PI, 2026-11-09): generator tests build sessions with `scripts/synthetic.py` on the frozen tiles session `FIX_T0`; engine-level tests use `FIX_T0` as an arbitrary environment. Only freshness and design tests read the real assets. Tests write nothing into the project. There are no Unity-side tests.
- **Validate a pilot run before trusting it:** `./venv/bin/python scripts/validate_run.py <run id or folder>` (read-only; `--all`, `--json`). It recomputes scoring independently of the C# code and checks the log's integrity and the ranking-break rules. FAIL = the data or scoring is wrong; WARN = undecidable; old log formats are unsupported (FAIL with "unsupported log format").

### Results database and simulator
`results/results.sqlite` holds every simulated-agent run; the full rules (agent identity, what is stored, `record_run`, querying, the battery, figure conventions, adding things) are in `docs/SIMULATION.md`. The short version:
- Names are labels, never keys; identity is the spec hash. **Look up before running; never re-run baselines unprompted.** Never UPDATE or DELETE `episodes` by hand.
- Compare agents on identical environments and seeds and report the paired difference with its standard error; a report states session, duration, seeds, tag, short engine hash and dirty flag.
- Figures: at most 5 agents, colours and linestyles from `plots.SERIES` / `plots.STYLES`, never hard-coded.
- A schema change bumps `schema_version` with a migration and copies the file first; a new `episodes` column goes at the end, nullable.
- If the simulator starts reading another SessionConfig field, add it to `fingerprint.SIM_FIELDS`.

### Simplifier agent
`.claude/agents/simplifier.md` reviews code for needless complexity (strips comments from a scratch copy, has a cold reader describe the code, treats whatever is hard to follow as a finding); run on its own it applies small behavior-preserving fixes (verified by `recompile` / `run_tests.py`) and proposes larger ones. Invoke it after a feature works and before the person commits, not during exploration; it does not hunt bugs (the red-team does). It also runs a compactness pass (the five largest simplifications) and a readability pass (how easy a newcomer or a naive agent would find the code). It does not weigh the hash cost of editing `ENGINE_FILES` / `AGENT_FILES`: the caller batches those and says so.

### Adversarial review (red-team, simplifier, arbiter)
`/adversarial-review [--since REF] [--no-rebuttal] [--save] [paths]` reviews a diff before the person commits: the **red-team**
(`.claude/agents/red-team.md`) and the **simplifier** (dry-run, first, so the red-team sees what it proposes to delete), an **arbiter** for what stays disputed. The protocol is in
`.claude/skills/adversarial-review/SKILL.md` and the goals, complexity budget, escalation rules and **Known and deferred** list in
`docs/REVIEW_POLICY.md`. Scientific design, the hash/meaning of stored results, and disagreements about goals go to the person, never to
the arbiter. Nothing is applied until the person agrees. `scripts/mutation_check.py` (an optional aid the red-team uses only for engine, planner or replay changes; also runnable by hand)
mutates the lines you changed in a scratch copy and lists the mutants the tests do not notice.

### Docs upkeep
Update `docs/SCIENCE.md` when the task design, session configs, or findings
change; add a `docs/DECISIONS.md` entry for rejected alternatives or any
design choice future-us might be tempted to "fix". Keep the README minimal.

---

## What NOT to do

- Do not modify `ProjectSettings/` or `Packages/` unless explicitly asked.
- Do not edit `.meta` files or `.git/`.
- Do not assign `SessionConfig` directly on components in the Inspector.
- Do not use `FindObjectOfType` or UnityEvents for game events.
- Do not switch fruits to a lit material or the canopy to single-sided.
- Do not reintroduce the terrain-projected highlight disc or the whole-canopy
  emission-pulse highlight — the highlight is the CanopyRim rim light (see
  `docs/DECISIONS.md`).
- Do not reintroduce hemisphere meshes, border objects, or border walls —
  trees are half-buried spheres and the border is the mountain band built into
  the terrain geometry (see `docs/DECISIONS.md`).
- Do not vary fruit count per bush, cap or rescale rewards inside a session, or hand-edit the fruit colour ramp.
- Do not change the `ForagingData/` output location.

