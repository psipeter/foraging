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
sequence of sessions (`S1`–`S3`), each with its own world seed and reward
function.

## Running

- Unity **6000.3.12f1** (URP). Open the project, load
  `Assets/Scenes/SampleScene.unity`, press Play.
- Sessions are the `SessionConfig` assets in
  `Assets/ScriptableObjects/SessionConfig/`, assigned to the `GameManager`
  in the scene. All task parameters are edited there, in the Inspector.
- Instruction text is read from `Assets/StreamingAssets/instructions.txt`.
- Controls: Space to harvest / continue, Esc to quit. Movement depends on the
  config's camera mode — *Exploration* (used by S1–S3): W moves forward, mouse
  turns; *Isometric*: WASD moves in world directions.

## Data

Each session writes `movement.csv`, `harvests.csv`, and
`session_metadata.json` to `ForagingData/<sessionId>/` in the project root.
This folder is gitignored (not backed up by git). It currently contains only
debugging output; once real data collection starts, back it up separately.

## Repository layout

`Assets/Scripts/` (Player, Trees, World, Session, UI, Data), `Assets/ScriptableObjects/`
(session configs), `docs/` (living documentation). The annotated file tree is
in `CLAUDE.md`.
