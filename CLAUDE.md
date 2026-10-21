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
- Targets PC (Linux/Windows standalone). Linux dev machine.
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
   un-calibrated turning oscillates and burns the 60 s session. Session time
   ticks in real time, so keep per-step latency low.
5. Verify with `events.csv` (`fruit` rows) or `harvests.csv` against screenshots, and run `scripts/replay.py <folder>`.
6. Clean up: kill the player and `Xvfb :99` by PID (`pkill -f` with a pattern
   that appears in your own command line kills your shell).

Facts learned: harvest starts within ~3.7 units of a tree's center (wide
canopies block the player earlier); Enter on the last session's end screen
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
    Data/      DataLogger (trajectory, events, harvests, manifest; see "Data logging")
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
docs/        SCIENCE.md, DECISIONS.md
scripts/     Python (run with ./venv/bin/python; venv/ and worlds/ are gitignored):
             interlude.py (Interlude stimulus design + bush placement on the session's terrain), world.py (reads SessionConfig .asset YAML; generates worlds from one seed — mirrors the
             C# placement/attribute/reward rules; exports .npz), sim.py (fast session engine + run_n /
             compare), agents.py (all agents + registry), replay.py (loads a logged session, replays its harvests, resamples for agents), test_*.py (pytest; run them with `scripts/run_tests.py`, which
             runs only the test files the changed files can affect, or `--all` before committing)
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
  moisture terracing, mountains, reward weights/std, fruit count) re-run
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
`DataLogger` writes one folder per session under `<project root>/ForagingData/<sessionId>/`, so that a participant's
actions can be replayed exactly in their world (and shown to agents):
`trajectory.csv` (one row per rendered frame: `t, x, z, yaw, pitch, keys`; the same state `HarvestManager` reads that
frame), `events.csv` (`t, real, type, tree_id, k, reward, running_total, note`: pause/resume, harvest press/release/
pause/resume, every fruit, teleports, Interlude trials, focus changes, session start/end), `harvests.csv` (one row per
harvest bout: a summary of the events plus the bush's attributes) and `manifest.json` (the full `SessionConfig`
serialized, the world file's name and sha256, build commit, display, frame statistics, `participantId` placeholder).
An Interlude writes the same plus `interlude.csv` (one row per forced-choice trial; see `docs/SCIENCE.md`).
World files are archived once by hash in `ForagingData/_worlds/`. `scripts/replay.py` loads a folder, re-derives the
harvests from the trajectory (mirroring `HarvestManager`) and checks them against the log: **change `HarvestManager`'s
range/bearing/timer rules and `replay.py` together.** The clock `t` is unpaused session seconds (stands still under an
instruction screen). **The path and the column semantics are fixed once real data exists — changing them breaks
downstream analysis and comparability.** Add columns only at the end, and say so. `Assets/Editor/BuildInfoWriter.cs`
writes the gitignored `StreamingAssets/build_info.json` (git commit, dirty flag) that the manifest reads.

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
- **Session world** (terrain, seed, spacing, jitter, mountains, reward weights/std,
  fruit count, moisture terracing): `./venv/bin/python scripts/world.py <sessions> --unity`.
  Unity warns at startup when a session world is stale.
- **Interlude** (its session's terrain, seed or reward function; or
  `interludeTrialCount`, `interludeBushDistance`, `interludeBushBearing`): copy the
  changed values onto the `*_Interlude` asset, then
  `./venv/bin/python scripts/interlude.py <names>_Interlude`. Unity does **not** warn
  when an Interlude file is stale.
- **No regeneration needed:** `targetFrameRate`, `sessionDuration`, `fruitHarvestDuration`, `playerMoveSpeed`,
  `interludeTrialSeconds`, `interludeHarvestFruits`, `interludeBonusPerCorrect`,
  audio volumes, instruction text.

### Testing
`./venv/bin/python scripts/run_tests.py` runs only the Python test files the changed
files can affect (`--all` before committing; `--dry-run` shows the decision). The
tests call the real generators in memory and write nothing into the project. There
are no Unity-side tests.

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
