# Foraging

A Unity 3D foraging task for psychology research on **feature-based reward
learning** in naturalistic environments. Participants navigate a procedurally
generated landscape and harvest bushes for fruit; each tree's reward is a
researcher-defined function of continuous attributes (canopy shape and
fruit color; the ground and its moisture are decoration). The research question is how
participants learn that function from experience, and how that depends on its complexity.

It is a research tool first and a game second: the design favors perceptual
clarity of the attributes and unambiguous reward feedback over polish.

- **Scientific goals, task design, session configs, open questions:**
  [`docs/SCIENCE.md`](docs/SCIENCE.md)
- **Why things are the way they are (incl. rejected alternatives):**
  [`docs/DECISIONS.md`](docs/DECISIONS.md)
- **Code conventions and workflow rules:** [`CLAUDE.md`](CLAUDE.md)

## The task

The experiment `FOR` (foraging in tiles) is a fixed-length day (sunrise → sunset) in a valley of hexagonal
plateaus, each with a tight cluster of bushes. Moving costs time; harvesting a bush costs time and yields a reward. The goal
is to maximize total reward before sunset. The loop is navigate → observe → decide → harvest, and when you leave a patch
the world fades to grey for a moment and you rank a few bushes by how much you think they pay (no outcomes shown; correct
pairs earn a hidden bonus). The reward function and the layout vary from session to session.

## Running

- Unity **6000.3.12f1** (URP). Open the project, load
  `Assets/Scenes/SampleScene.unity`, press Play.
- The experiment and its sessions are assets in `Assets/ScriptableObjects/Experiments/FOR/`, made from the design table
  `scripts/design/FOR.py` by `scripts/build_experiment.py FOR`. All task parameters are `SessionConfig` fields.
  Some changes (terrain, reward function, tile layout, the ranking pool) need the generator scripts re-run;
  see "What to regenerate" in `CLAUDE.md`.
- Instruction text is read from `Assets/StreamingAssets/Experiments/FOR/`.
- Controls (first person): mouse looks around, W/S walk forward/back, hold Space
  to harvest while the (faint) crosshair is on a bush, Enter to continue between screens, Esc to quit. Eye height, field of view,
  and mouse sensitivity are `SessionConfig` fields.
- Python tools (world and ranking-pool generators, a strategy simulator, tests) live in `scripts/`; run the tests
  with `./venv/bin/python scripts/run_tests.py`.

## Data

Each session writes `trajectory.csv`, `events.csv` and `session.json`, and `ranking_sets.csv` (one row per ranking set),
to `ForagingData/<run id>/<session>/` in the project root (world files are archived once in `ForagingData/_worlds/`).
`scripts/replay.py` reloads a folder and replays it.
This folder is gitignored (not backed up by git). It currently contains only
debugging output; once real data collection starts, back it up separately.

## Repository layout

`Assets/Scripts/` (Player, Trees, World, Session, UI, Data), `Assets/ScriptableObjects/`
(session configs), `docs/` (living documentation). The annotated file tree is
in `CLAUDE.md`.
