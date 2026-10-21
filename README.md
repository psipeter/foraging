# Foraging

A Unity 3D foraging task for psychology research on **feature-based reward
learning** in naturalistic environments. Participants navigate a procedurally
generated landscape and harvest trees for fruit; each tree's reward is a
researcher-defined function of three continuous attributes (canopy shape,
fruit color, ground moisture). The research question is how participants
learn that function from experience.

It is a research tool first and a game second: the design favors perceptual
clarity of the attributes and unambiguous reward feedback over polish.

- **Scientific goals, task design, session configs, open questions:**
  [`docs/SCIENCE.md`](docs/SCIENCE.md)
- **Why things are the way they are (incl. rejected alternatives):**
  [`docs/DECISIONS.md`](docs/DECISIONS.md)
- **Code conventions and workflow rules:** [`CLAUDE.md`](CLAUDE.md)

## The task

Each session is a fixed-length day (sunrise → sunset). Moving costs time;
harvesting a tree costs time and yields a reward. The goal is to maximize
total reward before sunset. There is no combat, inventory, or crafting —
the loop is navigate → observe → decide → harvest. A participant plays a
practice session (`P`) and four sessions (`S1`–`S4`), each with its own world seed and
reward function; the reward function gets more complex across sessions. After each session
comes an **Interlude**: a short forced-choice block in the same world where the participant
picks which of two bushes pays more (no outcomes shown; correct choices earn a hidden bonus).

## Running

- Unity **6000.3.12f1** (URP). Open the project, load
  `Assets/Scenes/SampleScene.unity`, press Play.
- Sessions and Interludes are the `SessionConfig` assets in
  `Assets/ScriptableObjects/SessionConfig/` (`P`, `S1`–`S4`, `P_Interlude`, `S1_Interlude`–`S4_Interlude`),
  listed in order on the `GameManager` in the scene. All task parameters are edited there, in the Inspector.
  Some changes (terrain, reward function, Interlude trial count or geometry) need the generator scripts re-run;
  see "What to regenerate" in `CLAUDE.md`.
- Instruction text is read from `Assets/StreamingAssets/instructions*.txt`, one file per session or Interlude.
- Controls (first person): mouse looks around, W/S walk forward/back, hold Space
  to harvest (walking is locked while harvesting), Enter to continue between screens, Esc to quit. Eye height, field of view,
  and mouse sensitivity are `SessionConfig` fields.
- Python tools (world and Interlude generators, a strategy simulator, tests) live in `scripts/`; run the tests
  with `./venv/bin/python scripts/run_tests.py`.

## Data

Each session (and each Interlude) writes `movement.csv`, `harvests.csv`, and
`session_metadata.json` to `ForagingData/<sessionId>/` in the project root; an Interlude also writes
`interlude.csv` (one row per choice).
This folder is gitignored (not backed up by git). It currently contains only
debugging output; once real data collection starts, back it up separately.

## Repository layout

`Assets/Scripts/` (Player, Trees, World, Session, UI, Data), `Assets/ScriptableObjects/`
(session configs), `docs/` (living documentation). The annotated file tree is
in `CLAUDE.md`.
