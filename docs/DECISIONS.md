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

## Border: four solid walls, not scattered border objects (superseded by mountains, below)

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

## Camera: exploration (follow, forward-only) used for S1–S3 (superseded by first person, below)

**Decision:** the original fixed ~45° isometric follow camera (chosen so
canopy shape in profile and fruit color on the dome were visible at once)
was supplemented by an exploration mode — mouse turns, W moves forward only —
and S1–S3 all use exploration. Isometric was then selectable per config via
`cameraMode` (since removed; see the first-person entry).

**Why:** the move to exploration and forward-only movement (`51fa98b`,
`bf96a6f`) is not explained in the commits; it fits the project's
naturalistic-environment goals (continuous navigation; see SCIENCE.md's
rationale).

---

## Camera: first person only; avatar, animations, and Isometric mode removed

**Decision:** the player sees the world from eye height; mouse looks (yaw +
pitch), W/S move forward/back, no strafing. The Remy avatar, its animations
and animator controller, the Isometric camera mode, the `CameraMode` enum, and
camera smoothing were deleted (all recoverable from git; Remy history:
`f89879f`, `f97390b`, `8b669e3`). Harvest has no body animation any more;
feedback is the fruits vanishing plus the score popups.

**Design choices and why:**
- *No `Time.deltaTime` on mouse deltas.* A mouse delta is already a per-frame
  displacement; scaling it by `deltaTime` makes turn rate depend on frame
  rate. The old code did this. Look is gated on `timeScale > 0` and not-frozen
  instead (the old `deltaTime` factor had implicitly blocked look while paused).
- *Sensitivity = degrees per count × multiplier* (`lookDegreesPerCount` ×
  `lookSensitivity`), independent of FOV, so a future settings slider only edits
  the multiplier and turn speed in cm/360 terms is well defined.
- *Yaw/pitch live on the camera, not the player root.* The Rigidbody is
  interpolated and would overwrite root rotation each frame; applying yaw via
  `MoveRotation` would add up to one physics step of look latency. Movement
  direction is derived from the camera yaw. `movement.csv`'s `player_heading` is
  now the camera yaw (same meaning as before: facing direction about Y).
- *Look input behind `ILookInput`.* For VR the headset pose should own the camera
  and scripts should only move the rig root; a VR implementation returns zero look
  and the rest (movement from head yaw, harvest trigger on the root) is unchanged.
  Not built yet. VR also supplies its own projection, so `cameraFieldOfView` is
  flat-screen only.
- *FOV is a scientific parameter.* Unity's `fieldOfView` is vertical (75° vertical
  ≈ 105° horizontal at 16:9); vertical stays fixed across aspect ratios.
  Wide-FOV edge stretch could distort the apparent canopy aspect ratio (the shape
  channel) toward the screen edge, and FOV interacts with monitor size/distance, so
  it is logged in the metadata and should be held fixed across participants.
- *Terrain-following height threshold 0.05 → 0.001.* From far above the 5 cm
  snaps were invisible; at eye level they would read as stair-step jitter.
- *Rejected:* head bob (a comfort problem for some people, and uncontrolled visual
  motion near the fruit-color channel); a reticle (proximity-triggered harvest has
  nothing to aim at); gaze-gated harvest (would add an aiming component to the task).
- *Not yet done:* in-game sensitivity slider (config value only), VR provider.

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

---

## Harvest range: gap grows with canopy radius, smaller than the old constant

**Decision:** the harvest/highlight trigger radius is `R + gap(R)` with
`gap(R) = harvestRangeGapBase + harvestRangeGapPerRadius * R` (SessionConfig;
S1-S3: 0.4 + 0.15 R, i.e. 0.48 for R = 0.5 up to 0.85 for R = 3). This replaces
the constant `highlightRadiusPadding` of 1.5. Setting base 1.5 and per-radius 0
reproduces the old behavior.

**Why:** with the exploration camera (pitch 30 deg, ~34 deg view ray at the
avatar), distance straight ahead is foreshortened to ~0.55x on screen, so a 1.5
gap looked like near-contact while still being out of range, and a constant gap
is 3x the radius of a thin tree but half that of a wide one. A smaller gap that
scales mildly with radius makes "visibly next to the tree" and "in range" agree
better. Not yet verified with participants-style play; the avatar capsule radius
was not measured.

**Caveat:** range sets the travel/approach time cost of each harvest, so this is
a task-difficulty change, not purely cosmetic. Revisit if S1-S3 become too easy
or hard.

---

## Border walls: flat top just above the highest possible eye level (superseded by mountains, below)

**Decision:** wall top = `terrainMaxElevation + borderWallHeight` (S1–S3: 20 + 7 = 27),
a flat height independent of seed; previously 8 boundary samples + 30, which varied
by seed. The walls are a thin band just above the horizon instead of a tall backdrop.

**Why:** with a first-person eye 5.1 above terrain (max terrain 20), eye level
reaches ~25, so a top below that would let the player see over the wall from a
hilltop; 27 never does, yet from valleys the far wall subtends only a few degrees.
Anchoring to `terrainMaxElevation` keeps the look identical across seeds.
`borderWallHeight` should be about `eyeHeight` plus a small margin.

## Time of day: sessions start part-way through the day

**Decision:** `dayStartFraction` (S1–S3: 0.3) offsets the sun/sky clock so a session
runs from mid-morning (sun about 73°) to sunset rather than dawn to sunset; the
timer and logged times are unchanged. Set 0 for the old behavior.

**Why:** the dawn start spent the first part of each session in low, warm, dim
light; later start gives brighter, more neutral light for judging fruit hue. Whether
to also shift the sky tint palette or skew toward afternoon (>0.5) is open.

---

## Border: mountains in the terrain geometry replace the walls

**Decision:** the map edge is a band of unclimbable mountains built into the heightmap
(`TerrainManager`), replacing `BorderWalls` (deleted along with `borderWallHeight/Color`).
Rocky gray with snow above a snow line, no trees on them. Per-seed ridged-noise skyline,
so each direction has distinct peaks.

**Why:** natural barriers are the standard way games hide map edges, with an invisible
barrier only as a backstop; flat-topped walls were a visible artificial seam at the
horizon. Because mountains are distal cues, the skyline is also a global orientation
cue for the task (research on boundaries/distal cues in virtual navigation), so
*distinct peaks per direction* was chosen deliberately over a uniform ring. Rectangular
boundaries helped spatial memory in one study; our valley's inner boundary is
irregular, which is a possible confound to keep in mind.

**How it works (and why):**
- *Elevation = valley + mountain.* Valley elevation stays coupled to moisture
  (`(1 - moisture) × terrainMaxElevation`); the mountain term is added on top and is
  exactly 0 in the valley, so the moisture channel and tree attributes are unchanged.
- *Ramp* `u` = 0 across the valley, 1 at the map edge, from Chebyshev edge distance over
  `mountainBandWidth` (60) with the band's inner boundary jittered (+/-15) by noise. Jitter
  rescales the band only, so the crest at the mesh edge is never lowered. Height is
  `mountainHeight × u^1.5 × (0.55 + 0.45·ridged)`, giving crests of 38–70 above valley
  base (the lowest edge crest on seed 1 was 55 absolute, vs. at most about 30 eye height), so
  the mesh edge is never visible.
- *Blocking:* terrain is not physical for the player (raycast height snap), so
  `PlayerController` refuses movement where `u >= mountainBlockThreshold` (0.15, about a 38° slope),
  per axis so the player slides along the foot, plus a hard clamp 1 unit inside the world edge.
  The block is derived from the same function as the visuals, so there are no invisible walls.
- *Trees* are kept out of the band plus `treeEdgeMargin` (8). `treeCount` went 300 → 147 to hold
  tree density constant (the valley is about 49% of the old area), since density sets travel cost.
- *Rendering:* the terrain shader (`VertexColor.shader`) ignores mesh vertex colors and
  blends textures by moisture, so rock/snow are per-vertex weights in `uv3` plus
  `_RockColor/_SnowColor` set from config on a material instance. Mesh resolution 128 → 257
  (32-bit indices).
- *Fog:* fog is linear 80–120 and the mountains start about 140 away, so at full strength
  they would be pure fog gray. The shader applies `mountainFogStrength` (0.3) of the normal fog on mountains,
  so the skyline stays visible; trees and valley are unchanged, so bush visibility range is unchanged.

**Open / watch:** low sun vs. mountain shading (at sunset the valley-facing slopes and
nearby valley can darken; crest angular height from the valley center is about 20°, `minSunElevation`
is 25°); `UpdateTerrainLighting` re-uploads the (now 66k-vertex) mesh colors every frame even
though the shader ignores them (about 210 fps measured, so left alone).

---

## Fog: off by default, toggled per session (`fogEnabled`)

**Decision:** `SessionConfig.fogEnabled` (default false; S1–S3 off) sets `RenderSettings.fog`
at session start (`GameManager`). The scene's linear fog (80–120, gray) is unchanged and
applies only when the toggle is on; `mountainFogStrength` only matters then.

**Why / watch:** with fog on, bushes beyond about 120 units were invisible, which acted as
a visibility limit on the foraging task; with it off, bushes are visible across the whole
valley, so exploration/search behavior may differ from fog-on data. Debugging output
collected before this change is not comparable. The fog was also the only thing hiding
the far mountains' base, so the skyline is now sharp.

