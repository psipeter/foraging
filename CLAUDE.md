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
saving).

---

## Repository structure

```
Assets/
  Scripts/
    Player/    PlayerController (non-kinematic Rigidbody, raycast terrain
               following, trigger harvest detection), CameraController,
               CameraMode (enum: Isometric, Exploration)
    Trees/     Tree (applies attributes, generates fruits/colliders,
               canopy-emission highlight), TreeAttributes (shape/color/
               moisture, floats 0-1), FruitMaterialManager (static unlit
               fruit material cache)
    World/     TerrainManager (Perlin elevation mesh + vertex-color
               moisture), TreeGenerator (seeded placement), BorderWalls
    Session/   SessionConfig (ScriptableObject — ALL parameters),
               GameManager, HarvestManager, SunController, QuitHandler,
               RewardFunction / RewardComponent / BasisFunctionType
    UI/        HarvestUI, SessionTimerUI, InstructionsPanel
    Data/      DataLogger
  ScriptableObjects/SessionConfig/   S1, S2, S3 (the experiment's sessions)
  StreamingAssets/instructions.txt   instructions text (read at runtime)
  Scenes/SampleScene.unity           the single scene
  Shaders/   VertexColor, VertexColorUnlit (terrain), FruitUnlit, RingUnlit
  Materials/ Prefabs/ Models/ (Remy) Animations/ Resources/Textures
docs/        SCIENCE.md, DECISIONS.md
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
- Procedural content derives from `WorldSeed` for reproducibility. Fruits
  are runtime-instantiated, never prefab children.
- The reward function is modular and defined entirely in `SessionConfig`
  (per-attribute basis function + weight/peak/width), never hardcoded.
- Layers: `Default` (misc), `Terrain` (ground), `Tree`, `Player`. Collision
  matrix: Player↔Terrain off, Player↔Tree on. Terrain following is a
  downward raycast each `FixedUpdate`, not gravity.
- Custom shaders must be in Project Settings → Graphics → Always Included
  Shaders, or `Shader.Find()` returns null in standalone builds.

### Reward system (do not "fix")
`R_bush = w1·f1(shape) + w2·f2(color) + w3·f3(moisture)`, **no
normalization**. Per-fruit reward = `max(0, round(Gaussian(R_bush,
rewardStd)))`, sampled independently per fruit; harvest total is the sum.
Basis functions: Linear, InvertedLinear, GaussianPeak, InvertedGaussian,
Constant.

### Data logging
`DataLogger` writes one folder per session under `<project root>/ForagingData/<sessionId>/`:
`movement.csv` (0.1 s samples: pose, camera, visible trees + distances),
`harvests.csv` (per harvest: tree, attributes, true reward, per-fruit
rewards, running total), `session_metadata.json` (config, reward function,
camera, full tree registry). **The path and the column semantics are
fixed — changing either breaks downstream analysis and comparability with
already-collected data.** Add columns only at the end, and say so.

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
  removed them; `TerrainManager.Start` still has one — remove if touched).

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
- Do not reintroduce the terrain-projected highlight disc — replaced by
  canopy emission pulsing (see `docs/DECISIONS.md`); `RingUnlit.shader`
  is now unreferenced.
- Do not reintroduce hemisphere meshes or border objects — trees are
  half-buried spheres and the border is four solid walls.
- Do not vary fruit count per bush, normalize rewards, or add red/green fruit.
- Do not change the `ForagingData/` output location.
