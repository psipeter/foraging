# docs/DECISIONS.md — non-diff-shaped project decisions

This file records decisions that git history can't hold: rejected
alternatives, design rationale, and conclusions reached before code existed
to attach a commit to. Bug fixes and diffable changes belong in commit
messages instead (`git log --grep <term>`, `git log --follow <file>`).

Entries are seeded from the project's earlier README/.cursorrules and the
commit history. Where the original *why* was never written down, the entry
says so rather than inventing one — fill those in (**TODO(PI)**) when
remembered. Newest entries at the bottom of each section's group; add new
ones at the end.

---

## Research-tool-first design priority

**Decision:** design choices favor ecological validity, perceptual clarity
of bush attributes, and unambiguous reward feedback over aesthetic polish
or gameplay complexity. No combat, inventory, or crafting; the loop is
navigate → observe → decide → harvest.

**Why:** the dependent variable (which trees get harvested, in what order)
is only interpretable if participants can actually perceive the attributes
and understand the reward. Polish that obscures or confounds a channel
costs more than it buys.

---

## Attribute channels: shape / fruit color / moisture, with prior management

**Decision:** three continuous attributes on three distinct visual channels —
canopy aspect ratio (tree level), fruit hue on an abstract blue→orange axis
(fruit level), and ground color + elevation (environment level). Fruit count
is held constant across all trees.

**Why:** channels should be perceptually independent and carry weak
ecological priors. Constant fruit count removes a count-based prior (more
fruit = more reward). Blue→orange avoids red/green ripeness associations.
Moisture is the weakest-controlled channel (weak-to-moderate prior).

**Not recorded:** why these three attributes in particular, and why moisture
is tied to terrain rather than assigned per tree (it makes the channel
spatially structured — see SCIENCE.md's open questions).

---

## Unlit fruits, double-sided lit canopy

**Decision:** fruits use a fully unlit shader (`FruitUnlit`); the canopy uses
a double-sided URP/Lit material. Neither is to be switched.

**Why:** fruit color is the signal for the color attribute, so it must read
identically at dawn, noon, and dusk. The canopy and terrain are lit so the
day/night cycle looks natural. Canopy double-sidedness: **not recorded**
(presumably because the procedural canopy is viewed from inside/at grazing
angles — TODO(PI)). Fruit color preservation under lighting was later
tuned via `fruitColorPreservation` in SessionConfig (`15ebf28`).

---

## Reward function: weighted basis functions, no normalization; integer, noisy per-fruit rewards

**Decision:** `R = Σ wᵢ·fᵢ(attributeᵢ)` with no normalization; each fruit's
reward is `max(0, round(N(R, rewardStd)))`, sampled independently, summed
over the harvest. The function is defined entirely in `SessionConfig`.

**Why:** reward normalization was explicitly rejected as a *research*
decision (the original README: "not an oversight"). Integer, per-fruit noisy
draws were introduced in `e42a8f9` ("Redesign reward system"). The earlier design
and the reasons for integer/noisy per-fruit rewards are not recorded.

**Full investigation:** `e42a8f9`.

---

## Trees: half-buried spheres, not hemispheres

**Decision:** canopies are spheres half-buried in the terrain, with fruits
placed above ground. The earlier procedurally generated hemisphere mesh
(dome-up, flat base) was deleted.

**Why:** not recorded beyond the commit (`c466be2` "Turn trees into spheres,
half bury them in the ground", then `a656ddf` "Delete hemisphere mesh").
Likely related to clean intersection with uneven terrain — TODO(PI).

---

## Tree highlight: canopy emission pulse replaces the terrain-projected disc

**Decision:** when the player is in harvest range, the canopy pulses its
emission color. The earlier pulsing semi-transparent disc projected onto the
terrain (`TreeHighlight`, `RingUnlit.shader`) is retired.

**Why:** not recorded beyond the commit (`e82d660`); a follow-up (`bf96a6f`)
fixed canopy emission in standalone builds. `RingUnlit.shader` remains in
`Assets/Shaders/` but is unreferenced.

---

## Border: four solid walls, not scattered border objects

**Decision:** the world edge is four solid walls anchored below the terrain
to above max elevation, replacing the earlier `BorderObject`/`BorderGenerator`
perimeter of objects.

**Why:** not recorded beyond the commit (`6b1db1a`) — presumably an
unambiguous, impassable boundary. TODO(PI).

---

## Player: non-kinematic Rigidbody, raycast terrain following, layer-based collision

**Decision:** the player is a non-kinematic Rigidbody with a zero-friction
physics material. The Terrain layer does not collide with the Player (the
terrain is followed by a downward raycast each `FixedUpdate`, not gravity);
Tree↔Player collides.

**Why:** the layer split prevents the player from sliding/sticking on terrain
slopes while still blocking on trees (`7b7cc58`).

---

## Camera: exploration (follow, forward-only) used for S1–S3; isometric retained in code

**Decision:** the original fixed ~45° isometric follow camera (chosen so
canopy shape in profile and fruit color on the dome were visible at once)
was supplemented by an exploration mode — mouse turns, W moves forward only —
and S1–S3 all use exploration. Isometric remains selectable per config via
`cameraMode`.

**Why:** the move to exploration and forward-only movement (`51fa98b`,
`bf96a6f`) is not explained in the commits; it fits the project's
naturalistic-environment goals (continuous navigation; see SCIENCE.md's
rationale).

---

## Character model: Remy (replaces X-Bot)

**Decision:** the avatar uses the Remy model with idle/walk/pick animations
(`f89879f`, replacing the X-Bot, which replaced a plain capsule in
`f97390b`). The harvest animation is synced to total harvest duration
(`8b669e3`).

**Why:** a proper player model also resolves the earlier known limitation
that the capsule visually overlapped wide canopies. Remy-vs-X-Bot rationale
not recorded.

---

## Session flow: multiple sessions per participant via scene reload

**Decision:** a participant plays an ordered list of `SessionConfig`s
(`GameManager`), with a scene reload between sessions, instructions shown
from `StreamingAssets/instructions.txt` (session 1 only), and a score screen
advanced with Space (`959dc09`, `c740ea8`, `cb598d2`). The earlier idea of a
shared base `DefaultSession` with config inheritance (`dfe041c`) and the
five-config set (`Config_1_Linear` … `Config_5_AllNonlinear`) are gone from the
repo; S1–S3 each stand alone.

**Why:** the progression S1→S3 (one feature → three features → mixed
nonlinear) appears to be a complexity ladder; the rationale for dropping the
base-config inheritance and for reducing five configs to three is **not
recorded** — TODO(PI).

---

## Data output: `ForagingData/` in the project root, three files per session

**Decision:** logs go to `<project root>/ForagingData/<sessionId>/` (gitignored):
`movement.csv`, `harvests.csv`, `session_metadata.json`. The path must not
change (set in `e42a8f9`).

**Why:** keeps participant data out of git (rationale for the specific
location otherwise not recorded). Caveat: gitignored means not backed up by
git — back up separately.

---

## Tooling: Cursor-prompt workflow replaced by direct Claude Code

**Decision:** the project previously ran Claude in chat to *write Cursor
prompts* (never direct edits), with Cursor applying them, guided by
`.cursorrules` and a README written for that workflow. That infrastructure
was retired when the project moved to Claude Code; its durable content was
ported into `CLAUDE.md`, `README.md`, and these docs.

**Why:** Claude Code edits and reads the repo directly, so the prompt-relay
and paste-to-new-chat handoff conventions are obsolete. The previous
`.cursorrules` and README remain in git history (`git log -- .cursorrules`).

---

## Git: single `main` branch

**Decision:** the old README described `main`/`dev`/`feature/*`; in practice
only `main` exists. The convention is: the person commits and pushes;
commit before a large Claude task.

**Why:** the branching scheme was aspirational and never used; docs now
match practice.

---

## Editor automation: official Unity CLI + Pipeline package, not mcp-unity

**Decision:** Claude drives the open Unity Editor through the Unity CLI
(`unity command ...`) and the `com.unity.pipeline` package. The community
`mcp-unity` bridge was trialed on branch `experiment/mcp-unity`, then removed
before merge.

**Why:** the CLI covers everything wanted from a bridge — recompile and
console, scene/asset reads and edits (including nested ScriptableObject
fields), Play mode, screenshots, running project C# via `eval`, plus
`test`/`build`/`run` — in a terminal, with no MCP wiring, and works on Linux
with a Personal license, both with the Editor open and headless (`unity test`
and `unity build` spawn a batch-mode Editor; verified, ~15 s and ~40 s, compile
errors abort with exit 6). Caveats: the CLI
is beta and the Pipeline package experimental (`0.8.0-exp.1`); revert via git
if either breaks.

**Alternatives evaluated:** `mcp-unity` (CoderGamester, MIT) — viable, but
redundant once the CLI worked, and it adds a Node server plus a generated
`ProjectSettings/McpUnitySettings.json`. Unity's official MCP server
(`com.unity.ai.assistant`) needs Unity Cloud and an AI-tools beta
subscription (cost unconfirmed). Hand-editing scene YAML was rejected: ~100
cross-referenced objects, risk of corrupting IDs.
