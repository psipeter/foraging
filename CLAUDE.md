# CLAUDE.md — foraging

Source of truth for conventions and workflow. For the scientific goals,
task design, session/reward-function inventory, and open questions, see
`docs/SCIENCE.md`. For why past design choices were made (including
rejected alternatives), see `docs/DECISIONS.md`. `README.md` is a short
human-facing description only. Read this file fully before making changes.

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
- **Check `docs/SCIENCE.md` for TEMPORARY test settings** (currently
  `sessionDuration` is 15 s on P and S1–S4; the design values are in the
  session table) before committing configs or running a pilot.

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
$U command get_serialized_fields --target Assets/ScriptableObjects/SessionConfig/S1.asset
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
   un-calibrated turning oscillates and burns the session (60-150 s by design, 15 s while the temporary durations are set). Session time
   ticks in real time, so keep per-step latency low.
5. Verify with `events.csv` (`fruit` rows) or `harvests.csv` against screenshots, and run `scripts/replay.py <folder>`.
6. Clean up: kill the player and `Xvfb :99` by PID (`pkill -f` with a pattern
   that appears in your own command line kills your shell).

Facts learned: harvest starts within `harvestRangeGapBase` (7) of the canopy edge, i.e. 7 + the canopy
radius from the tree's center (wide canopies block the player earlier); Enter on the last session's end screen
quits the app.

---

## Repository structure

```
Assets/
  Scripts/
    Player/    PlayerController (non-kinematic Rigidbody, W/S movement along
               the camera heading, raycast terrain following, trigger harvest
               detection), CameraController (first-person yaw/pitch, eye
               height, FOV), ILookInput + MouseLookInput (look input source)
    Trees/     Tree (applies attributes, generates fruits/colliders,
               rim-light highlight + progress ring), TreeAttributes (shape/color/
               moisture, floats 0-1), FruitMaterialManager (static unlit
               fruit material cache)
    World/     WorldData (loads StreamingAssets/Worlds/<session>_seed<N>.world:
               bush table + terrain grids + per-fruit rewards), TerrainManager (builds the
               valley + mountain-band mesh from the world's grids; sampling, walkable mask),
               TreeGenerator (instantiates bushes from the world file)
    Session/   SessionConfig (ScriptableObject — ALL parameters),
               GameManager, InterludeManager (between-session forced-choice trials), HarvestManager, SunController, QuitHandler,
               RewardFunction / RewardComponent / BasisFunctionType
    UI/        HarvestUI (+X popups, score), SessionTimerUI (timer, bar, end screen), InstructionsPanel,
               FeedbackAudio (synthesized sound cues), AmbientAudio (footsteps, cicada bed, birds), HudWidgets (runtime plates/bars)
    Data/      DataLogger (the recorder: rows per frame/event/trial, batched), DataPipeline (DontDestroyOnLoad: starts the server run, owns the
               sinks, the "saving" gate and the quit/leave drain), FileSink (local copy) and HttpSink (upload), TrajectoryCodec (chunk format),
               PauseGate (the only writer of Time.timeScale), StreamingData (reads StreamingAssets; in a browser from memory, filled by the Boot scene), PointerLockGuard (browser: hold the game while the mouse capture is released), OnlineSettings (StreamingAssets/online.json + command line), DataRows, Json;
               see "Data logging"
  ScriptableObjects/SessionConfig/   P (practice), S1-S4 (the experiment's sessions), and P/S1-S4_Interlude (their forced-choice Interludes)
  Audio/Ambient/                     CC0 recordings: Footsteps/ (Kenney Impact Sounds grass steps), Cicadas/ (BigSoundBank
                                     loop); each folder has licence/source notes
  StreamingAssets/instructions*.txt  instructions text read at runtime (practice: instructions.txt;
                                     S1-S4: instructions_S<n>.txt; Interludes: instructions_interlude_P.txt and
                                     instructions_interlude.txt; placeholders {session} {total} {interlude}
                                     {trial_seconds}; file chosen per session by SessionConfig.instructionsFile)
  StreamingAssets/Worlds/            generated <session>_seed<N>.world files (written by scripts/world.py) and
                                     <name>_Interlude_seed<N>.interlude.json (bush table + trials, scripts/interlude.py)
  Scenes/SampleScene.unity           the single scene
  Editor/    BuildInfoWriter (writes the gitignored StreamingAssets/build_info.json: git commit + dirty flag)
  Shaders/   VertexColor (terrain: moisture textures + mountain rock/snow; ignores
             mesh vertex colors), VertexColorUnlit, FruitUnlit, CanopyRim (additive
             fresnel highlight overlay) and HarvestRing (clock-style progress ring)
  Materials/ Prefabs/ Resources/Textures
supabase/    migrations/ (online database), functions/ (Edge Functions run-start, append, run-finish; _shared/), local/serve.ts (runs them
             without Docker); deployed to the Supabase project emdgczidpqdhftzujyte; deploy with the CLI, see docs/ONLINE_DATA_PLAN.md
docs/        SCIENCE.md, DECISIONS.md, ONLINE_DATA_PLAN.md (planned online data collection: schema, upload protocol, resume, build
             phases; nothing built yet, the "Data logging" section below still describes the current logger), REVIEW_POLICY.md (what
             code review optimizes; see "Adversarial review")
.claude/     agents/ (simplifier, red-team, arbiter) and skills/adversarial-review/
scripts/     Python (run with ./venv/bin/python; venv/ and worlds/ are gitignored):
             interlude.py (Interlude stimulus design + bush placement on the session's terrain), world.py (reads SessionConfig .asset YAML; generates worlds from one seed — mirrors the
             C# placement/attribute/reward rules; exports .npz), sim.py (fast session engine: actions, cone percept, Interlude
             evaluation; run_n / compare), perception.py (the sensor model: what the simulated observer sees; part of the environment, not the agent: `ConePercept` is the default, `OccludedConePercept` adds terrain and bush occlusion and holds the geometry `visibility.py` shares), costs.py (turning and key-press time costs and the `approach` arithmetic shared by the engine and the actors; provisional values fitted to debug logs), conftest.py (tests run with motor costs off unless marked `motor_costs`), agents.py (agent components memory / critic / actor, ComposedAgent, registry), battery.py (the assessment battery: every session S1-S4 plus its Interlude with checkpoints, populations of agents, a serial runner and command line), plots.py (matplotlib/seaborn figures for the results database, PNG into `results/`: a 2 x 2 grid of sessions, `sns.lineplot` per agent; colour-blind-safe `glasbey` colours plus a matplotlib linestyle per agent, warns above 5 agents), analysis.py (queries over the results database: `select`, `table`, `paired`, `component_effect`, `cumulative_curve`, `checkpoint_curve`, command line), results.py (the results database: schema, `Store`, `record_run`, `lookup`, `delete_run`), fingerprint.py (environment hash over the session parameters the simulator reads, engine-code and agents-code hashes, git commit and dirty flag), specs.py (agent specs: `Component` base that records constructor arguments, `spec()`, `spec_hash`, `build`, `flatten`, `labels`), replay.py (loads a logged session, legacy or online layout, replays its harvests, resamples for agents), rundata.py (the online data layout: local mirror of the database tables, reader and writer), trajectory_codec.py (compact chunk format for trajectories; see docs/ONLINE_DATA_PLAN.md), convert_legacy.py (legacy DataLogger folder to the online layout), webgl_smoke.mjs (a WebGL build in headless Chromium: loads, plays, uploads; Playwright from evidence_integration) and deploy_webgl.sh (a WebGL build as one fresh commit in a GitHub Pages repository; never pushes), server_client.py (reference client of the online server's protocol), server_admin.py (register releases/worlds, list runs, pull a run into the local layout), server_smoke.py (one throwaway run through the deployed endpoints, with latencies), test_server.py (end to end: real Edge Functions under Deno over a real PostgreSQL via pgserver; skipped without deno/pgserver/psycopg), visibility.py (reconstructs which bushes were in view per step, with egocentric coordinates), mutation_check.py (mutation testing of the changed lines in a scratch copy; see "Adversarial review"), test_*.py (pytest; run them with `scripts/run_tests.py`, which
             runs only the test files the changed files can affect, or `--all` before committing; `--fast` skips `slow`-marked tests)
```

Keep this tree in sync when files are added, moved, or retired.

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
  changing any world-shaping SessionConfig value (spacing, jitter, clearing, terrain,
  moisture terracing, mountains, canopy width/shape ranges, reward weights/std, fruit count) re-run
  `./venv/bin/python scripts/world.py P S1 S2 S3 S4 --unity`; `GameManager` warns at
  startup when a file is stale. Never hand-edit `.world` files. Fruits are
  runtime-instantiated, never prefab children (their on-bush layout is still seeded
  in C# from `fruitSeed`; it is visual only).
- **An Interlude is a session kind** (`SessionConfig.isInterlude`), not a
  separate scene: it runs in its session's own world (the `WorldData` terrain is
  loaded from the probed session's world file, `worldSeed` equal to the session's)
  with the bush table replaced by the small `*_Interlude_seed<N>.interlude.json`
  from `scripts/interlude.py`, and `InterludeManager` drives the trials. There is
  no Interlude-specific terrain logic: bush moisture/elevation are the terrain's
  at the position chosen by the placement search. An Interlude asset is a copy of
  its session's asset (reward function and terrain parameters must match; the
  script checks). Outcomes are hidden by the consumers of `HarvestManager`'s
  events (`HarvestUI`, `FeedbackAudio`, `InstructionsPanel`), not by suppressing
  the events. See `docs/SCIENCE.md` ("Interlude").
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
`R_bush = w1·f1(shape) + w2·f2(color) + w3·f3(moisture)`, **no
normalization**. Per-fruit reward = `max(0, round(Gaussian(R_bush,
rewardStd)))`, sampled independently per fruit and pre-drawn in the world file
(the k-th fruit taken from a bush pays `fruit_reward[bush][k]`); harvest total is the sum.
Basis functions: Linear, InvertedLinear, GaussianPeak, InvertedGaussian,
Constant.

### Data logging
**The online database is the default** (`docs/ONLINE_DATA_PLAN.md`, `docs/DECISIONS.md` "Online data collection"). `DataLogger` records
rows (a trajectory frame per rendered frame: `t, x, z, yaw, pitch, keys`, the state `HarvestManager` reads that frame, quantized by
`TrajectoryCodec`; events: pause/resume with a `reason`, harvest press/release/pause/resume, every fruit, teleports, Interlude trials,
focus changes, session start/end, each with a JSON `payload`; the session row: the full `SessionConfig`, world hashes, camera, display,
frame statistics, build; for an Interlude its shuffled trial order and one row per trial) and hands them in batches to `DataPipeline`.
The pipeline always writes the **local copy** under `<project root>/ForagingData/<run id>/<session:00>/` (`events.csv`, `trajectory.csv`,
`interlude_trials.csv`, `interlude_plan.json`, `session.json`, and `run.json` above them: the database's tables as files, read by
`scripts/rundata.py`) and, when `StreamingAssets/online.json` is enabled (or `-onlineUrl`/`-onlineKey` are given), uploads the same rows to
the Supabase project (off in the Editor unless `uploadInEditor`). Uploads are acknowledged: if the server leaves data unacknowledged
longer than `SessionConfig.uploadGraceSeconds`, or cannot be reached, the game holds still behind a message (`PauseGate`; a `pause`
event with reason `upload`) until it has stored everything; leaving a session or quitting waits for the drain. Only `PauseGate` may set
`Time.timeScale`. `scripts/replay.py` loads a session folder, re-derives the harvests from the trajectory (mirroring `HarvestManager`)
and checks them against the log: **change `HarvestManager`'s range/bearing/timer rules and `replay.py` together** (and the camera,
canopy or terrain-sampling rules with `visibility.py`). The clock `t` is unpaused session seconds. Trajectory time is quantized to a
microsecond because replay sums frame times (DECISIONS has the measurement). World files are archived once by hash in
`ForagingData/_worlds/`. **The table columns and their meaning are fixed once real data exists — changing them breaks downstream
analysis and comparability.** Add columns only at the end, and say so. `Assets/Editor/BuildInfoWriter.cs` writes the gitignored
`StreamingAssets/build_info.json` (git commit, dirty flag) that the session row and `run-start` read; the server refuses a commit that
is not registered (`server_admin.py register-release`). **Resume:** a participant who returns with the same Prolific ID (`-pid`) continues an unfinished run: `DataPipeline` reloads the scene for the session to continue and `DataLogger`/`InterludeManager` restore the clock, pose, score, fruits taken and Interlude order (`ResumeInfo`; `docs/ONLINE_DATA_PLAN.md`, section 4); the log gets a `session_resume` event, which `replay.py` treats as a discontinuity.

---

## Hard research constraints

- Never normalize the reward function output — intentional.
- Fruit count is constant across all bushes — never vary it per bush.
- Fruit color is the blue→orange axis only — no red/green hues.
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
The generated files are manual steps (nothing runs them at build time):
- **Session world** (terrain, seed, spacing, jitter, mountains, canopy width/shape ranges,
  reward weights/std, fruit count, moisture terracing): `./venv/bin/python scripts/world.py <sessions> --unity`.
  Unity warns at startup when a session world is stale.
- **Interlude** (its session's terrain, seed or reward function; or
  `interludeMode`, `interludeTrialCount`, `interludeBushDistance`, `interludeBushBearing`, `interludeMinElevationDifference`): copy the
  changed values onto the `*_Interlude` asset, then
  `./venv/bin/python scripts/interlude.py <names>_Interlude`. Unity does **not** warn
  when an Interlude file is stale.
- **No regeneration needed:** `targetFrameRate`, `sessionDuration`, `fruitHarvestDuration`, `playerMoveSpeed`,
  `interludeTrialSeconds`, `interludeHarvestFruits`, `interludeBonusPerCorrect`,
  audio volumes, instruction text.

### Long-running commands (experiments, regeneration, builds)
Run the real command once with `run_in_background: true` and its output redirected to a log (`... > "$SCRATCH/x.log" 2>&1`); the harness
notifies when that process exits, and only then do you read the log and report. Do not wrap it in `nohup ... &` (the wrapper exits at once
and its "completed" notification is about the wrapper) and do not write watcher loops with `pgrep -f '<pattern>'` (the watcher's own
command line matches the pattern, so it never ends). To see progress, read the log or run `analysis.py runs --tag T`. `sim.py` prints its
results table as its last output, which is the completion marker. This went wrong twice in one session; see the memory note.

### Testing
`./venv/bin/python scripts/run_tests.py` runs only the Python test files the changed
files can affect (`--all` before committing; `--dry-run` shows the decision). `--fast`
additionally skips tests marked `slow` (freshness checks of committed generated files, long
planner/Interlude searches): a few seconds vs about 35 s for everything, so use it while iterating, but run
the plain command after touching a session/Interlude asset, `world.py`, `interlude.py` or the
planner. The tests call the real generators in memory and write nothing into the project. There
are no Unity-side tests.

### Results database (`results/results.sqlite`, schema v3; specs, fingerprints, recording and query helpers are built)
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
  percept, kind (session or Interlude), Interlude `n_samples`, motor-cost constants. `code_versions`: a hash of the engine files
  (`sim.py`, `costs.py`, `perception.py`, `world.py`, `interlude.py`), a separate hash of `agents.py`, git commit and dirty flag.
- `episode_checkpoints` (schema v3): for a run recorded with `--checkpoints T1,T2,...` (kind interlude), the Interlude score (trials,
  accuracy, bonus) of a deep copy of the agent as it was at each session time. The copy is taken just before the first update to the agent
  after that time, so it equals the agent of a session that really ended there; the episode's own Interlude columns are the score after the whole
  session, equal to the checkpoint at the session's length. **For an agent whose behavior does not depend on the session's length this
  equals a shorter session; for one that does (`deadline_dependent = True`: the planners, a horizon softmax; any new actor whose choices depend on
  the time left must set it) the checkpoint is the agent as it stood at that time of a session of the battery's length, which is what a participant
  has at that moment, not what a shorter session would give** (such actors used to be refused). The checkpoint times are part of the environment hash.
- `episode_fruits` (schema v2): one row per fruit taken in the session (`t` in session seconds, `bush`, `k`, `reward`, `running_total`),
  the agent's counterpart of the human `fruit` events in `events.csv`; read with `Store.fruits(episode_id)` or
  `analysis.fruit_events(store, sel, agent, seed)`. No positions, headings or other actions.
- `runs` (agent, environment, code version, tag, time) and `episodes` (total, visits, fruits, walk/harvest/idle/look/press
  time, Interlude accuracy overall and by trial type, bonus). Unique on (agent, environment, code version, seed, kind).
- A stochastic agent's own seed is part of its record, since results are only reproducible given it.

**Using it**
```bash
./venv/bin/python scripts/sim.py S1 --seeds 0-99 --agents nearest,delta_rate_10 --record --tag my-experiment [--note "..."] [--interlude --n-samples 200] [--set session_duration=90] [--db PATH]
```
`record_run(agent, session, seeds, tag, kind=, percept=, overrides=, n_samples=, store=)` in `scripts/results.py` does the same from
Python (`agent` = factory, registry name or spec dict). It looks every seed up by (agent, environment, code version) and
computes only the missing ones; a cut-short run (Ctrl-C, an exception) keeps what it computed, links it to the run and notes
`[interrupted]`. `Store(path, readonly=True)` opens the file for analysis (`select(sql, params)` returns dicts). An Interlude
episode (`kind="interlude"`) is the session played and then the Interlude, so it carries the session columns too. The agent's own
random stream comes from the world seed, so a result is reproducible from its key; a custom `agent_rng` cannot be recorded.

**Querying with `scripts/analysis.py`** (read-only; open with `Store(path, readonly=True)`)
```bash
./venv/bin/python scripts/analysis.py runs [--tag T]
./venv/bin/python scripts/analysis.py table  --tag T [--baseline nearest] [--metric total|interlude_accuracy|interlude:<type>] [--engine current|any|HASH]
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
- **Figures are grids of panels, one per session** (2 x 2 for S1-S4): `plots.plot_cumulative_reward(panels, path, names=, order=)` and
  `plots.plot_learning_curve(...)` take `{session: curves}` (or one curves object) and draw each agent with `seaborn.lineplot` from the per-seed
  curves (`plots.long_form`): mean and 95% bootstrap interval across seeds, `hue` = agent name, the same colour for the same agent in every
  panel, one shared legend, one linestyle per agent as well as one colour (`plots.SERIES`, `plots.STYLES`), at most 8 agents per figure (the palette) and a warning above 5 (`plots.MAX_DISTINCT`). The advantage figure uses the **lowest-performing agent of each session**
  as its baseline (`cumulative_curve(..., baseline="lowest")`, `curve --baseline lowest`). For the battery, `battery.py plot --tag T --population P [--kinds reward,advantage,interlude]` saves one figure per kind as
  `results/<tag>_<population>_<kind>.png`; each population (all including `nearest`; more than 5 agents warns) is one figure group, except that the `scan-*`, `explore-*`, `delta-*` and `learners` figures leave out `nearest` and `oracle` (`battery.FIGURE_OMITS`; the figure then holds up to 6 or 7 agents, past the 5-agent warning and within the palette's 8; they stay in the population for `scores`), so their advantage baseline is the lowest learner.
- **Figure size and font conventions** (`plots.MODES`, from the evidence_integration project's `utils/plot_style.py` / `make_figures.py`): `mode="paper"`
  (default; `battery.py plot --mode`) is 6.5 in wide (a letter-page `\textwidth`) with 9 pt text (axis titles 10, ticks and legend 8, axes 0.8 pt,
  lines 2 pt, 300 dpi); `mode="presentation"` is 10.6 in wide with 15 pt text (labels 17, titles 18, ticks 13, legend 14, axes 1.2 pt, 200 dpi). Height is
  `rows * panel_height + extra_height` (foraging's own values), and the title, subtitle, legend and footer are placed from the font sizes (`plots._margins`).
  Seaborn's `ticks` theme, no gridlines, shared x axes across panels (shared y too in the Interlude figure; the reward and advantage panels have their own, since sessions differ in maximum reward). Battery figures are saved as `<tag>_<population>_{reward,advantage,interlude}.png`. Unlike evidence_integration, figures are PNG, not SVG.
- **Figure colour conventions** (`plots.SERIES`, `plots.STYLES`, `plots.MAX_DISTINCT`; rationale and the recipe that generated the palette in
  `docs/DECISIONS.md`, "Figure colours"): at most **5 agents per figure** (a warning above that; the palette holds 8 as a hard limit), each agent keeps one colour **and**
  one linestyle in every panel and figure; a new plot type must take its colours from `plots.SERIES` in order (lines also `STYLES`; scatter
  adds a marker per agent) and never hard-code colours. Colour is never the only channel for line or scatter plots. Check a new figure under simulated
  colour-blindness (deuteranopia, protanopia, tritanopia) before relying on it, and do not change the palette without re-measuring the worst pair.

**The assessment battery** (`scripts/battery.py`; "battery" because "test suite" already means pytest). One definition of how agents are compared:
S1 to S4 at the durations of the default `long` battery (120, 120, 180, 180 s, passed as `session_duration` overrides because the assets carry a temporary 15 s; `--battery standard` is the shorter 90, 120, 120, 150 s one that older records used), each
followed by its random Interlude (50 trials, **one pick per trial** (the Interlude choice is greedy for every actor, so a pick has no noise of its own; one pick keeps the cost of a battery low)), with a copy of the
agent scored at 0, 0.1, 0.2, 0.35, 0.5, 0.75 and 1.0 of each session; 10 seeds by default; each agent starts fresh in every session.
```bash
./venv/bin/python scripts/battery.py list
./venv/bin/python scripts/battery.py run --population main --tag <name> [--agents a,b,...] [--seeds 0-9] [--db PATH]   # records <name>/<session> runs
```
It is just `record_run` (kind interlude) per agent per session, sessions as the outer loop so each Interlude is generated once per (session, seed)
and shared by all agents. Populations (`POPULATIONS`: `main` = `nearest`, `oracle`, `learner`, the standard agents; the GP critic (`gp_mean`) and the exploration policies are in `learners`, `explore-noise`, `explore-bonus` and `explore-posterior` (GP critic), `delta-noise` and `delta-bonus` (the same actors on the delta-rule critic) and the one-parameter `scan-*` populations (each includes `gp_mean` as its reference); `learner-parameters`, `choice-noise` and `knowledge` are
the investigations; names are labels, identity is the spec hash) live in `battery.py`, not `agents.py`, so editing them does not move the agents-code hash.
**Standard agents:** the actor is the rate utility within 15 s of walking and the map comes from the view cone (`FullMemory`); `whole_map=True` gives the
full-information variant, and the registry's `greedy_*` entries stay full-information benchmarks. **Scores and plots are deliberately not part of the run**: they are
computed from the database afterwards: `battery.py scores --tag T --population P` prints, per session and agent, the paired reward lead over `nearest`
(in reward points, with its standard error), its split into **quality** (picks better bushes) and **efficiency** (takes more fruits) with fruits and reward per fruit,
the final Interlude accuracy, and the learning-curve area (`auc`, chance-corrected) and time to 0.8 accuracy (`t80`, fraction of the session). There is no
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
- *Code hashes* are of file bytes (`ENGINE_FILES`: sim, costs, perception, world, interlude; `AGENT_FILES`: agents, specs), so even a
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

### Simplifier agent
`.claude/agents/simplifier.md` reviews code for needless complexity: it strips comments from a scratch copy, has a cold reader describe
what the code does, and treats whatever is hard to follow as a finding. Run on its own, it applies small behavior-preserving fixes itself (verified by
`recompile` / `run_tests.py`) and proposes anything larger. Invoke it after a feature works and before the person commits, and for an
occasional module sweep, not during exploration. It does not hunt bugs (the Red-team session does). It also runs a compactness pass (the five
largest simplifications) and a readability pass (how easy a newcomer or a naive agent would find the code). It does not weigh the hash
cost of editing `ENGINE_FILES` / `AGENT_FILES` (even a comment edit moves the code hashes): the caller batches those and says so.

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
- Do not vary fruit count per bush, normalize rewards, or add red/green fruit.
- Do not change the `ForagingData/` output location.
