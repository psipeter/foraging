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

## Harvest range: gap grows with canopy radius, smaller than the old constant (superseded by first-person harvesting, below)

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

---

## Harvesting in first person: graded directional glow, distance + bearing threshold, hold Space

**Decision:** replaced the proximity trigger and press-once harvest with distance + bearing
targeting in `HarvestManager`: gradual glow ahead of you (steady, graded by edge distance and
bearing), a distinct availability state (pulse + "Hold SPACE" hint) within `gap` = 7 of the
canopy edge and 35 degrees of bearing, harvest by holding Space (one fruit per
`fruitHarvestDuration`, nearest-to-camera first), walking locked while holding, look free, harvest
paused when the bush leaves the cone. `Tree` lost its trigger sphere. TODO(PI): the earlier session's
discussion of the threshold was not available when this was built; the numbers below came from
the user's request and the geometry.

**Why:** from a 5.1 eye height with 75 degrees vertical FOV the near foot of a bush is only on screen
beyond 5.1 / tan(37.5 degrees) = 6.6 units; the old gap (about 1.7) clipped bushes and their +X
popups. `harvestRangeGapBase` 7, `PerRadius` 0 (range is a constant edge distance, since the
visibility argument does not depend on bush size). Bearing uses yaw only so looking down does not
drop bushes from "in front of you", and subtracts the bush's angular radius so large near bushes count.

**Movement/look regime while harvesting:** walking locked (no walking out of range, no
hands-free chaining between bushes); look untouched by default and the harvest pauses outside the
cone, which keeps the VR path open (a script cannot steer a head) and avoids silently changing
each participant's effective sensitivity. Rejected as the default: a leash that slows yaw to zero as you
look away. It exists as `harvestLookResistance` (0 = off), flat-screen only; if used, its value must be
treated as an experimental manipulation (logged in metadata `harvest.lookResistance`).

**Rewards:** +X popups at a fixed slot near screen center (neutral white; not tied to the fruit's
position, so never off screen); the score updates per fruit, not per completed harvest (there is no
"complete" moment any more). The random popup spread was removed, which also stops the UI from consuming
the shared `UnityEngine.Random` stream that the reward noise uses. The per-harvest "Total" popup is gone.

**Data (appended columns only):** `harvests.csv` is now one row per harvest bout (press to release or
exhaustion): `total_received` is the bout's reward, `running_total` the session total after it, and
`fruit_rewards` the bout's fruits only; appended `fruits_collected`, `fruits_remaining`,
`tree_exhausted`. `movement.csv` appended `harvesting`, `focus_tree_id`. Metadata gained a `harvest` block.
Earlier debugging output has one row per whole harvest and is not directly comparable.

**Watch:** harvesting stops costing the exclusive "freeze" time it used to only in the sense that the
player can still look around; the time cost is the held time itself. `DataLogger.maxVisibilityDistance`
(80) still caps `visible_tree_ids` even though fog is off and bushes are visible farther.

---

## Highlight look: rim light replaces the whole-canopy emission wash (switchable)

**Decision:** `SessionConfig.highlightStyle` selects the look. Default `RimLight`: an additive fresnel
overlay (`CanopyRim.shader`, on a 1.03x copy of the canopy sphere, material `CanopyRim.mat` referenced
from `TreeGenerator` so the shader ships in builds) draws a soft wide edge glow that grows with approach, and a thin
crisp edge line (higher fresnel exponent) added only on the selected bush; both ease in and out. `EmissionWash`
(the canopy turning pale, pulsing when selected) is kept for comparison.

**Why:** the wash turned the whole canopy a flat pale beige, hiding the moss texture and shading, and the
pulse looked out of place. The rim leaves the canopy interior alone, so the shape channel (silhouette and aspect ratio) stays readable.
Approach and selection use different kinds of cue, not just brightness: a graded soft glow vs. a crisp line.
Constraints held: no change to canopy aspect ratio or fruit hue/brightness (fruits untouched), no reward information, pale cream
(not a hue near the orange end of the fruit axis), luminance-based so it works without hue discrimination, world-space so it ports to VR.
The canopy's own double-sided Lit material is unchanged (overlay is a separate renderer).

**Rejected / not built:** crisp inverted-hull outline as the selection cue (not requested; the thin rim line
covers selection for now), drifting motes, progress ring, fruit glints/shimmer (touch the fruit channel),
dimming non-selected bushes (biases which bush is chosen), light shaft, ground ring (terrain-projected cues were retired).
Intensities and exponents are `SessionConfig` fields (`rim*`), live-tunable in Play mode.

---

## Harvest progress ring, selected rim color, exhausted bushes stay as "spent" landmarks

**Decision:** (1) the selected bush's rim blends to `rimSelectedColor` (slightly warmer pale gold); (2) a
camera-facing clock-style ring above every in-range bush shows the remaining fraction (bright arc erased
clockwise from 12 o'clock over a faint track), `HarvestRing.shader`/`.mat`; (3) an exhausted bush STAYS in
place, still blocking, and eases (`spentTransitionDuration`) into a spent look: uniform scale `spentScale`
(0.7; uniform so the canopy aspect ratio, the shape channel, is preserved) and a drab canopy tint `spentTint`
multiplied onto the base color; the blocking collider shrinks to match.

**Bush fate: stay vs. vanish (considered and decided).** First built as shrink-and-disappear (same linear
shrink as a collected fruit). Rejected: vanishing makes the remaining bushes an external record of what is
left, removing the memory demand for visited locations from the task, and sparsens landmarks over the session.
Staying is also closer to real plants, keeps spatial landmarks, and leaves navigation constraints unchanged.
The spent look exists because fruits are small and an emptied bush otherwise looks like a fresh one from afar.
Alternatives not built: sink into the terrain, eased/delayed shrink, dissolve (needs a canopy shader change),
wither (changes aspect ratio mid-animation), leaf-puff. Depleted bushes never glow or show a ring (skipped by
`HarvestManager`).

**Why:** fruits on the far side of a bush are not visible, so the ring is the continuous "still harvesting" signal and a record of
what is left on return; it is also a second, non-hue indicator of being in range. The ring is world-space at a constant
apparent size (`harvestRingSizeDeg`) so it reads at 7 and 20 units and ports to VR.

**Details / consequences:**
- The progress through the fruit in hand is stored on the bush (`Tree.PartialProgress`) so releasing Space mid-fruit
  and resuming continues the same fruit and the ring does not jump back up. This slightly changes harvest timing: held
  time is never wasted.
- `visible_tree_ids` in `movement.csv` still includes exhausted bushes (they remain visible); `harvests.csv`
  `tree_exhausted` marks when a bush was emptied.
- Rim color shift is a hue-adjacent change: `rimSelectedColor` should stay pale and near-neutral, not toward the
  orange end of the fruit hue axis.
- Ring shown for every in-range bush (distance + bearing), not just the selected one; selected is only marked by the rim.


## Bush placement: jittered hex lattice (replaces random + minimum distance)

**Decision:** Bushes sit on a hexagonal lattice (`treeSpacing` = nearest-neighbour distance) with a seeded rotation and
offset, each displaced uniformly within a disc of radius `placementJitter * spacing / 2` (default 0.5). Density is set by
spacing; `treeCount` and the hardcoded 5-unit minimum distance were removed, and the count now follows from the valley area.

**Why:** with random placement, clusters of nearby bushes make "harvest whatever is nearest" competitive with walking to
good bushes, which erodes the learning component, and cluster presence varied by seed. A hex lattice gives six equidistant
neighbours (most uniform coverage); jitter removes the artificial look. Simulated (147 pts, 264x264 valley): random NN
distance mean 11, CV 0.57; hex jitter 0.3 / 0.5 / 0.7 -> mean 20 / 18 / 16, CV 0.09 / 0.17 / 0.26, closest pair 16 / 11.5 / 7.
Disc jitter guarantees a minimum separation of `spacing * (1 - jitter)` with no rejection sampling, so it replaces the
separate minimum-distance constant. Jitter above ~0.7 lets near-pairs (clusters) return.

**Rejected:** Poisson-disk (blue noise) - more natural but irregular spacing statistics and no direct density control;
strict square grid - visible alignment and unequal neighbour distances (4 near, 4 far); keeping random placement as a
selectable mode (not needed; jitter 1.0 approximates it).

**Consequences:** all worlds changed relative to earlier debugging runs (no collected data existed). `session_metadata.json`
`treeCount` is now the number actually placed; `treeSpacing` and `placementJitter` were added after it.

## Python world generation and strategy simulator (scripts/)

**Decision:** `scripts/world.py` generates worlds in Python from `SessionConfig` .asset parameters and one world seed;
`scripts/sim.py` simulates sessions on them without 3D or real-time walking. Unity does not yet load these worlds (stage 3:
a loader replacing TreeGenerator/TerrainManager generation); until then the Python world and the Unity world for the same
seed are statistically equivalent, not identical. (Stage 3 is now done: see the loader entry below.)

**Why:** a seed -> world function that runs without the Editor, in a language the researcher reads, lets many seeds and
parameter settings (spacing, speed, session length, reward weights) be evaluated quickly. A bit-exact port of Unity's
`Random`/`Mathf.PerlinNoise` was rejected as fragile; making Python the source of truth avoids two diverging copies.

**Details / consequences:**
- One seed drives everything through fixed named child streams (moisture noise, boundary noise, placement, attributes,
  per-fruit reward noise). Per-fruit rewards are pre-drawn per (bush, fruit index) - a scientific change from the
  unseeded `HarvestManager.GaussianNoise`: independent per fruit as before, but reproducible and identical across agents.
- Noise: classic gradient noise with `PERLIN_GAIN` 1.23, calibrated so the moisture field's std over the valley matches
  Unity's (0.166 over 8 seeds in Play mode vs 0.135 uncalibrated). Placement statistics match Unity (NN mean 18.4,
  CV 0.13, nearest to start 36).
- Engine assumptions (verified in code): no regrowth (`isHarvested` is one-way), horizontal speed unaffected by slope.
  Ignored for now: collisions with canopies, facing time, partial-fruit progress, walkable-boundary detours. Agents decide
  only at fruit boundaries; a fruit unfinished when the clock runs out is not collected.
- Distance to a bush is measured to the edge of its harvest range (`canopy radius + harvestRangeGapBase + perRadius*R`)
  and the simulated player's position is tracked, so each stop leaves it at the range edge, not the bush center.
- Not yet generated in Python (rendering only, needed for stage 3): mountain elevation/ridges/snow weights, terrain mesh.

## Unity loads Python-generated worlds (stage 3)

**Decision:** `TerrainManager` and `TreeGenerator` no longer generate anything. `GameManager.Awake` loads
`StreamingAssets/Worlds/<session>_seed<worldSeed>.world` (`WorldData`) and gives it to both. The C# Perlin/ridge/rock/snow
code, tree-site mask and lattice placement were deleted, not kept as a fallback (two generators would silently produce
different worlds). A missing file logs an error with the export command; `GameManager` also logs a warning per
generation parameter whose SessionConfig value differs from the one the file was generated with.

**Format (v1):** `FWLD`, version, header length, JSON header (bushes as flat arrays, per-fruit rewards, parameter echo),
then float32 grids (moisture, elevation, rock, snow, mountain ramp) at the mesh resolution, flattened `i*res + j` (version 1; version 2, 2026-11-10, quantizes them and gzips the block: see "World files: quantized and compressed grids").
Terrain is the same linear-interpolated mesh as before, now with vertices read from the grids instead of computed;
`SampleElevation/Moisture/Mountain` are bilinear samples of the same grids. ~1.3 MB per world, committed with the
project so the exact worlds participants play are on record.

**Consequences:**
- A bush's attributes and moisture come from the file (the continuous field at its position), not from sampling the
  mesh grid; they agree to within 0.001.
- `HarvestManager` pays the pre-drawn reward for the k-th fruit taken from a bush (falls back to a fresh draw only if a
  bush has no stored rewards). Leaving and returning continues at fruit index k, so rewards cannot be re-rolled.
- Worlds for the same seed differ from earlier Unity-generated ones (different noise implementation); no real data
  existed. `session_metadata.json` gained `worldFile` (before `treeCount`).
- Changing any world-shaping SessionConfig value requires re-exporting; this is the cost of a single source of truth.

## Cleanup: single highlight style, ground-ring shader and template leftovers removed

**Decision:** the rim-light highlight is the only highlight. Removed `EmissionWash` (`Tree.UpdateEmissionWash`, the
`HighlightStyle` enum, `SessionConfig.highlightStyle`, the four emission Inspector fields on `Tree`), `RingUnlit.shader`
(the terrain-projected ring, also dropped from Always Included Shaders), the Unity template `TutorialInfo/` and
`Readme.asset`, and two unreferenced volume profiles. Unused code from the move to a first-person view and Python-owned
worlds was also removed (write-only terrain normal on `Tree`, `SampleNormal`/`SampleMoisture`, `HarvestDuration`,
`SessionProgress`).

**Kept deliberately:** built-in Unity packages/modules (removal risks breakage; compile-time gains are small), the
`Mobile_*` pipeline assets (still referenced by `QualitySettings`), and `VertexColorUnlit.shader` (unreferenced but
still in Always Included Shaders). `S1`-`S3.asset` still contain a stale `highlightStyle` key until Unity next rewrites them.

## Reward feedback: gamified popups, score/timer plates, synthesized audio

**Decision:** harvesting gets stronger feedback while the numeric reward stays the primary signal. Popups (pop-in with
overshoot, outline, pale gold), count-up score with flash, plates behind score/timer, a per-fruit particle burst, and a synthesized pick blip with pitch following reward plus an exhaustion chime.
All tunables are `SessionConfig` fields under "Feedback (HUD and audio)".

**Why/constraints:** feedback must not confound the attribute channels. Colors are pale/neutral (no red/green, nothing in
the blue-to-orange fruit hue family); the burst reuses the fruit's own material, so it adds no new hue. Size and pitch
scaling with reward is optional (`rewardSizeScaling`, `pitchSemitoneRange`): it adds a graded cue to the number and may speed
learning, so it is a parameter to choose per study, not a fixed style.

**Details:** HUD plates and the timer bar are built at runtime (`HudWidgets`) so the scene needs no authored objects. Sounds are
synthesized at startup (`FeedbackAudio`, no audio assets); add cues by extending its `Cue` enum. The player's own clock-driven
animations use scaled time, the score count-up uses unscaled time. Per-fruit sound is triggered by `HarvestManager.OnFruitCollected`,
the chime by the new `OnBushExhausted` event. Skipped on purpose: a timer bar and low-time warning color/pulse, in-world camera/FOV kicks, bout-total banners,
streaks/combos.

---

## Session progression: P, S1–S5, one new concept per step (planned)

**Decision:** the planned sequence is practice → S1 (one linear feature, two
distractors) → S2 (one Gaussian peak) → S3 (two linear features) → S4 (all three
features non-zero, additive, monotonic, at least one inverted) → S5 (an
interacting pair plus one additive feature; details TODO). Sessions lengthen
(≈90 s → 240 s) so that learning takes ~35–50% of the stops. Full table and
numbers: `docs/SCIENCE.md`, "Planned session progression".

**Why:** the 60 s sessions give ~7 stops, too few to learn and then exploit.
Each visited bush is ≈ one clean data point (`rewardStd` 0.3 over 10 fruits), so
session length is set by the number of stops needed, and each session adds a
single concept so a change in learning speed can be attributed to it.

**Rejected / alternatives considered:**
- *S4 as a peak + linear mix, S5 as full complexity.* Not a real stepping stone:
  S4 already combined a new function shape with multi-feature integration. S4 is
  now the first all-three-relevant session and deliberately simple.
- *Two-linear before Gaussian (S2/S3 swapped).* Plausible, but it puts the
  all-linear S4 right after a nonlinear session and splits the build in feature
  count. Gaussian first also tests carry-over of the linear prior from S1.
  Counterbalancing S2/S3 across participants remains an open option.
- *S5 as a fully arbitrary 3D function with interactions.* Probably unlearnable
  in ~25 stops, and a null result could not distinguish "participants failed" from
  "task too hard". Provisional plan is one interacting pair plus one additive
  feature, to be fixed after S4 pilots.
- *Mid-session reward reversal* (non-stationarity) was discussed and not
  adopted; it would need a new reward-switch mechanism.

---

## P–S4 implemented: practice flag, per-session instruction files, feature rotation

**Decision:** the progression above is built as assets `P`, `S1`–`S4` (values in
`docs/SCIENCE.md`). Practice is a `SessionConfig.isPractice` flag (not a special
scene): it changes only the end-screen wording and the "Session x/N" numbering
(N counts non-practice sessions). The instructions shown before a session are a
per-session file (`instructionsFile`, with `{session}`/`{total}` placeholders), and
a session can keep a faint controls reminder on screen (`controlsReminder`,
`controlsReminderOpacity`) and show a one-time pausing message after the first harvest
(`firstHarvestMessage`); P uses both. `session_metadata.json` gained `sessionName`
and `isPractice` at the end (the world file name already encoded the session).

**Why:** the relevant feature rotates (P shape, S1 color, S2 shape peak, S3
color+moisture, S4 all three) so participants cannot carry a feature-specific
rule between sessions; the S2 peak is off-centre (0.65) so it is not just "avoid
extremes". Instruction text lives in files and the config, not code, so it can be
changed per session without recompiling.

**Known concern, not fixed:** with summed weights the blind `nearest` agent
reaches 76% (S3) and 81% (S4) of the `plan_beam` ceiling, so the payoff for
learning the mapping is smallest where learning is hardest. Left as is until
pilots show whether it matters.

---

## Faster play (speed 7.5, 0.25 s per fruit) and a much larger map (`worldHalfExtent` 350)

**Decision:** player speed 5 → 7.5, `fruitHarvestDuration` 0.5 → 0.25 s, and `worldHalfExtent`
200 → 350 (with `terrainMeshResolution` 257 → 449 so vertex density is unchanged), in all of
P, S1–S4. The valley goes from ~264 to ~580 units across and the tree count from ~140 to ~690.

**Why:** the faster pace felt better in play, but with the original ~264-unit valley it was too
easy to walk to one side, hit the mountains, and have to turn back through exhausted bushes;
longer sessions make that worse. A full-harvest stop is now ~5 s, so the longest session covers
roughly 450–570 units of travel; the larger valley lets a participant keep moving through
unharvested ground and keeps the harvested fraction small.

**Notes:** terrain noise is defined per world unit, so the moisture/elevation gradients (and
their spatial autocorrelation) keep the same scale on the bigger map. The mountain band width is
unchanged, so the valley area grew faster (~6×) than the half-extent squared. Performance with
~690 bushes (6,900 runtime fruits) is untested; 350 is a compromise (400 gives ~960 bushes) and is one
config value to change. Agent baselines were not re-run after this change (stale; see SCIENCE).
Session durations have not been retuned to the new stop rate.

---

## Terraced moisture in S3/S4; near-flat terrain in P/S1/S2

**Decision:** in the sessions where moisture is rewarded (S3, S4) the moisture field is terraced: rank-normalised over the
valley, snapped to 4 levels with gentle ramps (`moistureTerraceSharpness` 0.3) and a ±0.1 undulation on plateau tops,
at wavelength ~165 units (`terrainNoiseFrequency` 0.6) and `terrainMaxElevation` 20. In P/S1/S2, where moisture earns nothing, the
valley has little relief (`terrainMaxElevation` initially 3, later raised to 6, then 12, to bring relief back; snow line preserved with `snowLineFraction` 0.693, then 0.65, then 0.564). The terracing lives in
`scripts/world.py` (defaults off) with three new `SessionConfig` fields that are also in the stale-world check.

**Why:** terrain is irrelevant to reward early on, so relief there is just noise for navigation and view; once moisture matters,
large plateaus and valleys holding many bushes make it a learnable regional feature rather than a continuum of small hills.

**Rejected / considered:**
- *Only lowering the noise frequency or raising elevation:* still a smooth continuum, no distinct regions.
- *Steeper ramps (sharpness 0.8–0.5):* previews gave 70° near-cliffs (p99 55°) and the eye height jumped ~6 units in a few
  steps; 0.3 matches the old terrain's steepness (p99 31° vs 27°). Elevation 14 was also previewed and is the fallback.
- *Fully flat plateaus (no residual):* kept a small residual so plateau tops are not perfectly uniform.
- *Clipping the residual at 0/1:* produced spikes of bushes at moisture 0 and 1; levels are inset by the residual amplitude instead.
- *Applying it to S3 only:* both S3 and S4 reward moisture, so both use the same terrain style, changing only reward complexity.

**Consequences / not yet settled:** moisture std over bushes roughly doubles (0.16 → 0.30), the layout is strongly regional
(see SCIENCE "Terrain by session"), and the moisture→height coupling may be adjusted after play-testing (TODO in SCIENCE).
Agent baselines are not re-run (stale).

---

## S3: moisture (terrain) is the highest-weighted feature

**Decision:** S3's weights are swapped to colour 1.5, moisture 3 (was colour 3, moisture 1.5), so the terraced terrain is the dominant
feature in the session that introduces it. S4 is unchanged (colour 3, moisture 1.5, shape inverted 2).

**Why:** to make learning the terrain feature clearer when it first matters; the plateaus then account for about twice the reward
variance of colour in S3 (spread 0.89 vs 0.43). S3's world was regenerated (per-fruit rewards depend on the weights); agent baselines
are stale and were not re-run.

---

## Ambient audio: synthesized in code, strictly uninformative

**Decision:** footsteps, a wind bed and occasional birds are generated at startup in `AmbientAudio` (same approach as `FeedbackAudio`),
identical across sessions, with volumes/timing in `SessionConfig`.

**Why:** a research tool should not carry licensing or provenance questions for its stimuli, and the project already synthesizes its
cues. Ambient sound is passive atmosphere, so it must not become an extra channel about reward or location.

**Rules and rejected alternatives:**
- *No dependence on terrain, moisture, elevation, nearby bushes or time of day* (e.g. footstep timbre per ground type, wind that
  strengthens in valleys, birds that call near bushes would all leak information); constant timbre and random bird timing/pan.
- *Not using `UnityEngine.Random`:* the reward noise is drawn from that global stream, so the audio uses its own `System.Random`.
- *All-synthesized ambience:* tried first. The birds were fine, but the synthesized footsteps sounded like drums and the wind like waves.
  Footsteps now use recorded CC0 grass steps (Kenney "Impact Sounds"; chosen over Fantozzi's CC0 footsteps on OpenGameArt, 12 clips of
  grass/sand/stone, because the pack was checked to ship five grass files with a CC0 licence file). Not used: "footsteps on different
  surfaces" (CC-BY, needs attribution) and paid marketplace packs.
- *Wind bed:* synthesized, then dropped: no CC0 library wind found was a plain gentle breeze (the OpenGameArt CC0 candidates are dungeon-cave
  wind), the synthesized version still sounded awkward, and in a valley where nothing visibly moves wind has no visible cause. A constant
  background that needs no visual referent was wanted instead. Considered and rejected: distant water (nothing visible), a low drone/pad
  (reads as music or machinery).
- *Cricket bed (night):* tried first as the replacement (CC0 "Crickets Ambient Noise – loopable", Wolfgang_ on OpenGameArt, 10 s loop); judged better as a
  daytime sound because sessions run through the sunlit part of the day. Removed from the project.
- *Cicada bed (chosen):* BigSoundBank "Cicadas" (ID 3002, Clarisse, CC0). Chosen over BigSoundBank's single-cicada recordings (s2397/s2399,
  mono, 75–78 s) because a chorus is diffuse and steady, over the field cricket (s1020, one voice), and over "Countryside" (s0097: wind noise in
  the mic and birds). Others not used: sinny's cricket loop (CC-BY-SA), Tim Mortimer's chirp loop (CC-BY), paid libraries. BigSoundBank blocks
  scripted downloads with a bot challenge, so the file was downloaded by hand; only a 579 KB Ogg loop is committed, not the 14 MB WAV.
- *Loop repetition:* the loop is 45.5 s, and two copies at different pitch and offset play together so the pattern does not realign audibly.
  Dense 4-12 kHz insect sound can be fatiguing over long sessions: keep `bedVolume` very low or 0.
- *Steps tied to a timer instead of distance:* distance-based steps stop when walking is blocked by mountains or locked for harvesting.

---

## Interlude: a forced-choice block after each session, in the session's own world (choice mode first)

**Decision:** after every session (including practice) a short forced-choice block reads out the learned reward mapping on controlled
stimuli: two bushes, choose the one that pays more, by turning toward it, walking to it and harvesting it. Each Interlude runs in the probed
session's own world (same terrain, mountains, sun) with only the two trial bushes present. Details, stimulus mix and scoring are in
docs/SCIENCE.md ("Interlude"). It is an ordinary session kind (`SessionConfig.isInterlude`) driven by `InterludeManager`; stimuli and bush
placements come from `scripts/interlude.py`.

**Why:** in the main task performance mixes value learning with exploration and planning, and a participant may know a good rule without
having sampled enough bushes to show it. Fixed, equidistant, single-decision trials remove planning and give many controlled comparisons,
and keeping the world as it was keeps the stimuli as similar to the main sessions as possible.

**Terrain: reuse the session's, place the bushes on it (no Interlude-specific terrain logic).** A bush's moisture and elevation are those of the
terrain where it stands, so the generator searches the session's real terrain (500k random spawn/heading placements) for positions whose moisture
relation fits each trial (same / one plateau level apart / two or more levels apart), then chooses shape and colour freely. The Interlude config
reuses the session's world file by reference (its `worldSeed` equals the session's) and Unity swaps in a small bush table (3-9 KB).
- *Rejected: a purpose-built stage world (one cell per trial, flat plateaus under each bush).* That was built first. It gave full control of moisture,
  but it needed new terrain code (pad plateaus and ramps in Python), looked unlike the sessions (no mountains, a bare plain), and duplicated terrain
  in ~270 KB files; Interludes were meant to look like the session.
- *Rejected: terrain edited at runtime, a purpose-made terrain from the generator (sharper ramps, shorter wavelength), a second world seed.*
  The first needs new C# terrain code; the second makes the terrain differ from the session and adds a ~4 MB file per Interlude; a new seed would
  avoid spatial memory of the session's layout but costs the same storage. The same terrain was chosen; the harvested bushes are gone and the
  pairs straddle elevation boundaries, so familiarity with regions should matter little (a possible confound to keep in mind).
- *Rejected: bushes with a moisture value that disagrees with the ground.* It would break the channel participants learn.
- *Rejected: showing the two bushes one after the other.* It would turn the choice into a memory task.
- *Consequence:* moisture differences are limited by the terrain. Plateau levels change one step at a time, so with bushes 28 apart a two-level difference
  (about 0.5, about 10 units of height) is available at about 0.5% of placements and the extremes (0.8) essentially never; the moisture contrast
  uses the largest available difference and trade-off pairs use one or two levels.
- *Wider bush separation (bushes about 28 apart; was 21 apart):* chosen to make two-level pairs available (0.5% of placements versus 0.04-0.2%). It lengthens
  the walk to about 2 s (the time limit and per-fruit speed are the knobs if this is too slow); offset 17 would raise availability again at the cost of a
  longer turn and bushes near the edge of the view.

**Other design choices:**
- *Session kind in the same scene, not a second scene:* the sun, terrain, bushes, harvesting, instruction/end screens, logging and flow
  already work per session; only the trial logic is new.
- *Lateral offset ≥ harvest range + largest canopy radius:* with a smaller offset a wide canopy comes into range just by walking straight,
  so the harvest selection (smallest bearing) would default to the widest bush and bias choice by shape.
- *Choice by harvesting the whole bush at the main task's per-fruit speed and animation:* same controls and a built-in cost to changing one's
  mind; the choice is the first bush whose last fruit is taken (`interludeHarvestFruits` can be lowered). A shorter earlier version (4 fruits, about
  1 s) was dropped when the Interludes were made to match the sessions; if the 7 s limit is too tight the per-fruit speed can be raised in the
  Interlude assets. Left/right keys were the alternative.
- *Sound in an Interlude:* the exhaustion chime stays on, but each fruit makes a different, neutral pick sound (very short, soft, low, falling pitch)
  instead of the main blip. The main blip's pitch rises with the reward, so even a fixed-pitch version would pair the harvest with the
  low-versus-high-reward cue (an earlier version did exactly that, and was replaced). Popups and the score are hidden. HarvestManager fires its events
  in every session kind and each consumer (HarvestUI, FeedbackAudio, InstructionsPanel) decides what an Interlude shows; suppressing the events at the
  source (the first version) also silenced the sounds. A practice Interlude inherited the practice session's first-harvest message because it is a copy of
  that asset, so the message is blanked in the Interlude assets and also ignored in code.
- *10 s limit with a timeout (was 7 s):* trials never stall; a timeout earns nothing and is logged as choice none. The instruction text reads the number of seconds from `interludeTrialSeconds`.
- *Stimulus types:* of those discussed, contrasts, graded pairs and extrapolation (extreme-valued trade-offs) were kept; matched-reward pairs
  and peak-straddling pairs were dropped for now for time. Extrapolation is a trade-off pair when several features matter, and at most one
  pair when only one does (it would just repeat the contrasts). Contrasts always include one irrelevant feature as an ignored-feature check.
- *Hidden bonus:* +5 per correct choice (ties count, timeouts and practice do not), shown only on the final screen to give feedback on
  performance without teaching. 3 trials in the practice Interlude and 10 in the others keeps the extra time to a few minutes.
- *Prediction mode, analysis and a simulated learner* are deferred.

**Known concerns:** the trial count, the 5-point bonus and the timing (about 2 s walk + 2.5 s harvest in a 7 s window) are untuned; the on-screen
"7 seconds" is not tied to the config; the practice Interlude's terrain is nearly flat; a trial's spawn can be on a plateau ramp.

---

## Interlude length and speed: 20 trials, walking at 15 (2026-11-02)

**Decision (PI):** the S1-S4 Interludes have 20 trials (was 5) and `playerMoveSpeed` 15 (the sessions' 7.5 doubled), as the harvest was already made 4x faster than in sessions; the practice Interlude stays at 3 trials and 7.5. The bush distance stays 22.6: shortening it would leave too little room for the S3/S4 pairs to differ in elevation. **Why:** 5 trials give accuracy a resolution of 0.2 per participant; 20 trials cost about 1 s less walking each. **Not done:** `interludeBonusPerCorrect` (5) was not rescaled, so a perfect Interlude now pays 100 instead of 25 points; decide before payment is fixed. Interlude files regenerated.

## Interlude gap modes: trials spread over reward gap and feature gap (2026-11-02)

**Decision (PI):** new `interludeMode` values `RewardGap`, `FeatureGap`, `Hybrid` choose the 20 trials so that the gap between the two bushes (true reward difference,
perceptual feature distance, or both) is spread evenly from a minimum to the largest the world offers, instead of independent random pairs. S1-S4 are Hybrid.
The stimuli are fixed per session by the world seed, the same for every participant.

**Why:** random pairs are mostly large gaps, so a 20-trial block would be mostly easy; if two bushes are not perceptually distinguishable the choice is hard whatever has been learned, so the
feature gap is a difficulty axis of its own.

**Rejected:** (1) *Decorrelating the two gaps in Hybrid* (tried: a penalty on their correlation brought r from about 1 to 0.3-0.7 at a cost in evenness): not needed, since the reward mapping must be learned either way; removed to keep the code small.
(2) *Keeping the hand-built elevation floor* with the gap modes: it conflicts with the low feature-gap bins (a pair that is nearly identical cannot differ in elevation by 3 units), and spreading the gaps already spreads elevation on average. It remains for Random mode.
(3) *Per-trial rejection sampling into bins*: needs a feasibility model for the hybrid's joint cells (large reward gap with a small feature gap is impossible); choosing from a candidate pool by hill climbing handles both with one code path.
(4) *Equal channel weights* in the feature gap are a placeholder: there are no measured discrimination thresholds for shape, colour and moisture; set `FEATURE_WEIGHTS` when there are.
`interludeBonusPerCorrect` was not rescaled for 20 trials (see the entry above).

**Interlude order is fixed (PI, same day):** the Interlude bushes are part of the environment, so every participant sees the same trials in the same order. The per-participant shuffle in `InterludeManager` is gone; the shuffle that guards against order effects is now in the generator, which keeps the best of 3000 seeded orders (no long runs of one correct side, no alternation, no trend in either gap). Order effects are then constant across participants rather than averaged out: they cannot be separated from the stimuli by analysis, which is the price of a controlled environment.

## S5: two Gaussian bumps over shape x colour plus linear moisture (2026-11-02)

**Decision (PI, from the options below):** `RewardFunction` gains a `bumps` list; a bump is a circular Gaussian over (shape, colour) with centre, width and height, summed with the per-feature terms (S5 uses none of shape and colour's own terms). S5: two bumps (heights 2.8 and 1.8, width 0.2, at least 0.6 apart) and a linear moisture term of weight 1.2; 180 s.

**Why:** the sessions before it are additive, so a feature-by-feature learner suffices. Two bumps need the joint (shape, colour) structure, and the lower bump is a local optimum, so S5 also tests exploration against exploitation. Shape x colour carries the structure because moisture is harder to judge visually; it stays as a plain additive term.

**Rejected:** a product of two features plus an additive third (easiest, an additive learner gets partial credit), a centred product (XOR; no feature alone predicts reward: probably unlearnable in a session), a single 2-D bump (no trap), moisture-gated context (ties difficulty to the terrain layout and is hard to explain).

**Done the same day:** S5 and S5_Interlude are in the `GameManager` list (12 entries; about 7 more minutes of play). **Not done:** server registration (every world file changed, so all must be registered again, and the release is `--sessions 12`), the simulated battery, and any check that the widths suit people.

## Feedback box on the final screen; scoreboard left as a TODO (2026-11-02)

**Decision (PI):** the browser's final screen has an optional free-text feedback box (one row per run in `public.feedback`, a second submit replaces the first, 5000 characters at most, accepted also after the run is finished). The completion code is shown first and the box never gates payment; a Prolific participant returns by a button, not the old 6 s timer, because typing takes longer. A scoreboard (opt-in, ranked, anonymised) is written down in `docs/ONLINE_DATA_PLAN.md` as an optional TODO, not built.

**Rejected:** putting the text in the `append` stream (it needs the run still in progress; the box comes after `run-finish`), a text field per Interlude or session (interrupts the task), keeping the auto-redirect (it would take the page away while someone types).

## Per-fruit harvest time: 0.2 s in sessions, 0.05 s in Interludes

**Decision:** `fruitHarvestDuration` is 0.2 s in P and S1-S4 (was 0.25 s) and 0.05 s in the Interludes. A whole bush now takes 2 s in a session and 0.5 s in an
Interlude, and the harvest progress ring, which is computed from this value each frame, follows without code changes. The fruit-pop and burst animations keep their
own durations (0.15 s, 0.35 s), so at 0.05 s per fruit several overlap.

**Why:** a faster harvest makes sessions and Interludes less slow, and the Interlude's 7 s window was tight with a 2.5 s harvest (about 2 s walk + 2.5 s harvest).
The agent baselines in docs/SCIENCE.md were already stale and were not re-run.

**Equidistance check (Interlude), and the fix:** the two bush centres were exactly equidistant from the spawn point (difference 0.0000; `placementJitter` is only used
when the main world's lattice is generated), but the harvest rules use the canopy edge and canopy radius depends on shape, so the edge distances differed by about 0.7-1.4
units on average (up to 2.2, up to 0.3 s of walking), the wide canopy looked closer and the tall narrow one further, and elevation changed the 3D distance by up to about
4 units. The geometry is now radius-aware: each bush is placed so its canopy edge is `interludeBushDistance` (22.6) from the spawn point and its inner edge is
`interludeBushBearing` (31.5 degrees) off the heading on opposite sides, so the heading bisects the pair and the turn and the walk to start harvesting either bush are
identical by the game's own range and cone rules. The config field `interludeBushOffset` was replaced by `interludeBushBearing`. Rejected: keeping symmetric centres (the
original); shifting only the player (it changes both distances equally). Residual asymmetries that cannot be removed: apparent size, 3D distance on slopes, and a small
change in the moisture at each bush's final position, which the design re-checks (the 'same moisture' relation must still hold at the final positions).

---

## Interlude: terrain must not hide the bushes; 10 s trials; 15 s sessions for testing

**Decision:** (1) `interludeTrialSeconds` is 10 s (was 7 s); the instruction text takes the number from the config (`{trial_seconds}`). (2) The placement search now
rejects any spawn/bush pair where the terrain hides the bush: the ground may not rise and then fall (by more than 0.5 units) on the way from the spawn point to either
bush (`has_hump`, an interior elevation peak above both ends), and the eye line must clear the ground to a point 1 unit above the bush's base (was 3 units). A steady climb or descent,
or a dip, is allowed. In the generated files the worst rise-then-fall is 0.4 units and the smallest eye-line clearance 0.65. (3) TEMPORARY: `sessionDuration` is 15 s on P and S1-S4 so the whole
flow can be tested quickly (design values 60/90/120/120/150; see docs/SCIENCE.md), and the Interlude session caps are 150 s (60 s for the practice one) so ten 10 s trials fit.

**Why:** a hill between the player and a bush hides part of it and makes the two bushes look unequal, on top of the radius effect fixed earlier.

---

## Reward popups: fixed cycle of free slots in a central row

**Decision:** with 0.2 s per fruit about 4 "+X" popups are alive at once, so they now cycle through `popupSlotCount` (5) horizontal slots `popupSlotSpacing` (120 px) apart,
centred on `popupOffset` (order centre, right, left, farther right, farther left). Slots in use are tracked and skipped, so non-overlap does not depend on cadence;
if every slot is busy the next one in the cycle is reused. Tunables are `HarvestUI` Inspector fields (like `popupOffset`), not SessionConfig.

**Why / rejected:** position must carry no information, so the choice is a deterministic cycle, never reward- or bush-dependent. Rejected: random positions (can overlap, and
adds noise); reward-dependent height or side (a new information channel); vertical stacking (leaves the central view and collides with the rise); placing popups at the bush's
screen position (unreadable when the bush is at the edge, the reason for the fixed slot). Assumes slot spacing exceeds the widest popup; raise it if reward scaling grows the text.


## Interlude: per-Interlude score screen (correct x/n and bonus), no per-trial feedback

Decision (user): after each non-practice Interlude the end panel shows "x / n correct" and "Bonus: +y" for that Interlude;
the final screen adds the totals. Timeouts and running totals are not shown. Rejected: final-screen-only (the earlier lean,
for zero feedback between sessions). **Superseded 2026-10-31:** see "Interlude points on the final screen" at the end of this file. The leak risk is judged small because every session has a different reward function and
only counts are shown, not which trials were right. The practice Interlude shows no score (it earns nothing).


## Interlude instruction text: terse, no controls or time limit in the text

**Decision:** the Interlude instructions are short lines in the style of the main sessions' text. The practice Interlude (`instructions_interlude_P.txt`) says only: (first wording; replaced in the 2026-10-31 wording pass) two trees will
appear; choose the one you think pays more, based on what you learned in the last session; no points are shown here, but good choices earn a bonus. The later Interludes
(`instructions_interlude.txt`, numbered with `{interlude}`/`{total}`) say the same minus the practice framing. The controls and the time limit are deliberately not in the text.

**Why:** the controls are the main task's, and the on-screen countdown (upper left) and progress counter (upper right) carry the timing; a longer text was the previous
draft and the user cut it. The number of seconds, if a variant mentions it, comes from `interludeTrialSeconds` through `{trial_seconds}` (so it cannot drift from the config).
The text never describes the reward structure, and mentions the bonus only in general terms.

---

## Python tests: cached Interlude generation and changed-file selection

**Decision:** the full Python suite took 127 s, 123 s of it in the Interlude tests, because each of ~15 tests regenerated the five Interludes (a 500k-placement search, a few seconds each).
The tests now generate each Interlude once per run (a module-level cache), the determinism test uses a smaller search (120k placements, since the property does not depend on its size),
and the export test reuses a cached result (`write_sidecar` was split out of `export`). One redundant test was removed (offsets growing with radius, covered by the equal-edge-and-bearing test).
The suite takes ~22 s. `scripts/run_tests.py` goes further: it compares the working tree with a git ref and runs only the test files the changed files can affect (C#, docs, the scene and
generated world/JSON files affect none; `interlude.py` or an `*_Interlude.asset` affect the Interlude tests; `world.py` or a session asset affect all three), with `--all` before committing.

**Why / not done:** the tests import and call the real generators (`interlude.py`, `world.py`) in memory and write nothing into the project; the generators themselves are manual steps run
when the design or configs change. The tests do not check that the committed generated files are current (see the open question in docs/SCIENCE.md). Rejected: a `slow` marker as the
primary mechanism (the changed-file selection and caching cover it), and Unity-side tests (there are none; see CLAUDE.md).

**Update (suite 213 tests, ~15 s):** a `slow` marker was added after all, as a secondary mechanism on top of the changed-file selection: `run_tests.py --fast` skips the 13 slow cases (committed world and Interlude freshness checks, the brute-force planner test, `test_deterministic`, and the real-world/real-Interlude runs), giving ~7 s. These are the only guards against forgetting to regenerate a stale file, so `--fast` is for iteration and the plain/`--all` run stays the pre-commit check. The three planner-optimality loops were also cut (25 -> 8/10 trials, 4 -> 2 seeds); each checks a different property, so none was deleted.


---

## Sun and sky: the same arc every session; the sky is driven on a runtime material copy

**Decision:** every session plays the same sun/sky arc, from mid-morning (`dayStartFraction` 0.3, sun about 73 degrees) to dusk (low sun, warm sky, dim light at the end), mapped onto the
session's length, so a shorter session simply plays the arc faster and the lighting changes faster (with the temporary 15 s sessions the whole arc takes 15 s). Interludes hold the sun still
(`freezeSun`, at their own `dayStartFraction`) because lighting changes between trials would add noise to visual judgments of canopy shape and ground colour. `SunController` now drives the sky on a
runtime copy of `SkyboxMaterial` (`RenderSettings.skybox` is pointed at it and restored on destroy) instead of writing to the shared asset.

**Why:** in the Editor, edits made to a shared material during Play are saved into the asset, so `SkyboxMaterial.mat` showed a diff after every play (its `_SkyTint` and `_AtmosphereThickness`
ended at whatever the last frame was). It was the only runtime writer to a shared asset: bush canopies, rims, rings and the terrain use per-object material instances, and `RenderSettings`
values are scene state that Unity discards when Play ends. The sky tint and thickness are still computed from the `SessionConfig` palette (`skyColorDawn`, `skyColorNoon`, `sunIntensityDawn/Noon`,
the sun path parameters), so the schedule stays configurable.

**Rejected / not done:** extending the arc into darkness (a night end would reduce the visibility of the moisture and shape channels and conflicts with the earlier decision to start later in the day for
brighter, more neutral light; superseded by the next entry, which ends at 10 degrees); a fixed wall-clock sun speed independent of session length (sessions would end at different times of day);
one day across the whole experiment (P in the morning to S4 at night). The SkyboxMaterial asset itself is left at its last committed values; it no longer changes.


---

## Sun trajectory: a real solar arc from mid-morning to 10 degrees at dusk

**Decision:** the sun now follows a standard solar path instead of `elevation = sin(t*pi) * sunArcHeight` with a 25 degree floor. New `SessionConfig` fields: `sunLatitude` (40), `sunDeclination` (+12),
`sunEndElevation` (10), `sunAzimuthOffset` (0). `dayStartFraction` still places the start (0.3 = mid-morning, 45 degrees); elevation and azimuth come from the usual formulas, with the day mapped onto hour angle so the sun
is at the horizon at sunrise/sunset, peaks about 62 degrees, rises in the east-south-east and sets in the west-north-west, moving fastest near the horizon. The session runs from the start hour angle to
the one at which the elevation equals `sunEndElevation`, mapped onto the session's length. `sunArcHeight` was removed; `minSunElevation` stays as an optional floor, now 0 (off). Interludes still freeze the sun
(at their `dayStartFraction`, 0.5 = noon, sun from the south). The sky palette, light intensity and ambient light keep their old formulas (dawn-to-noon blend of `sin(pi * t)`) and, after a correction, their old clock: `t` runs from `dayStartFraction` to 1 over
the session independently of where the sun is (a first version tied `t` to the new sun's hour angle, 0.3 to 0.93, which changed the colour and intensity timeline; the user preferred the old look, so
direction and light are decoupled). Shadow and ambient behaviour were deliberately **not** changed. Consequence: sky colour, intensity and ambient are identical to the old arc at every point, but the sun is lower
(45 degrees at the start, 10 at the end instead of 73 and 25), so the direct light on level ground is lower: about 20% less overall at the start and near the end (total 1.32 vs 1.65 at the start, 0.43 vs 0.56 at the end,
arbitrary units). If the overall brightness should match the old arc, raise `sunIntensityNoon`/`sunIntensityDawn`; if the end should be darker, the levers are `sunEndElevation`, `sunIntensityDawn` and the
(hardcoded x0.7) ambient factor, which barely changes through the day (ambient is about 75% of the light at dusk).

**Why:** the old arc passed directly overhead (90 degrees, a tropical-only path), started at 73 degrees, and sat pinned at 25 degrees for the last 12% of every session while its direction swept sideways, so it never
approached the horizon or the mountains. Seen from the valley the skyline is 3-22 degrees (median 9, measured on the real terrain), so ending at 10 degrees is just above the ridge from most places.

**Not decided / risks:** the 25 degree floor existed to hide shadow-bias artifacts at low sun and terrain does not self-shadow, so the last part of each session may show artifacts; whether the dusk scene is still readable
for ground colour and canopy shape is for the playtest to judge (options if not: raise `minSunElevation`, fade shadows and intensity near the horizon, keep an ambient floor, or end higher). Rejected earlier: extending the
path into darkness, a fixed wall-clock sun speed, one day across the whole experiment.


---

## Lighting: physics for hue, curves of elevation for brightness, an exposure ramp (SolarHybrid)

**Decision:** a new `SessionConfig.sunLightingModel` (`LegacyClock` | `SolarHybrid`, default SolarHybrid) controls how the sun's colour, intensity, sky and ambient follow the day; the sun's *direction* (the real solar path) is the same in both.
SolarHybrid: (1) **hue from physics**: the sun's colour is its transmittance through the atmosphere, `exp(-tau * airmass)` per channel (Kasten-Young air mass, `sunExtinction` = zenith optical depth (0.10, 0.16, 0.30)),
normalised so only chroma changes and blended with the old warm white by `sunHueStrength` (0.8) as a guard on hue readability; the Unity procedural sky is left to do its own Rayleigh scattering from the sun's direction (neutral
`skyTintNeutral`, constant `skyAtmosphereThickness`) instead of our hand-made orange-to-blue blend; (2) **brightness from curves of the sun's elevation** in `SessionConfig`: `sunIntensityByElevation`, `ambientIntensityByElevation`
(the scene's ambient source is Skybox, and the ambient probe is now rebuilt from the sky every 0.5 s with `DynamicGI.UpdateEnvironment`), `skyExposureByElevation`; (3) **an exposure ramp**: `postExposureByElevation` drives the URP
Color Adjustments post-exposure (stops) on a runtime copy of the Global Volume profile (never the asset), 0 at noon down to -0.6 EV at 10 degrees. Defaults are uncalibrated starting values (curves are piecewise-linear and editable in the Inspector).

**Research findings that shaped it:** engines use the sun as one driver of a chain, not the only one: older ones (Frostbite before 2016, many Unreal projects) authored per-time-of-day keyframes for sun colour, sky, fog and ambient and blended them
(laborious to keep consistent); newer ones derive sun colour and sky from an atmosphere model and capture the sky for ambient light, with artist scales on top (Frostbite/Hillaire, Unreal Sky Atmosphere + Sky Light); brightness is handled with
exposure/eye adaptation and colour with grading LUTs blended by time (BeamNG, CryEngine, Factorio docs). Unity's procedural skybox shader computes sunset reddening from the main light's direction (the light's colour only tints the sun disc), so overriding
its tint and thickness per frame (the old blend) double-counted the sunset colour. Sources are in the conversation record; the Frostbite and Hillaire PDFs were only read through search summaries.

**Discovered while building it (affects earlier analysis):** the scene's ambient source is Skybox, so the old script's `RenderSettings.ambientLight` writes (flat colour) had no effect, and the ambient probe was a fixed bluish value that nothing refreshed. The terrain shader
(`VertexColor.shader`) lights with `0.15 + 0.85 * shadow * N.L` using only the sun's direction (no colour, no intensity) plus `unity_AmbientSky`, which is black in Skybox mode; the fruit shader uses an ambient floor of 0.35 and specular with the light colour; only the canopy
(URP Lit) responds to the sun's colour and intensity. So the earlier "ambient is 75% of the light at dusk" estimates described the script's intent, not the rendered scene, and the hue and intensity curves act on the canopy, sky and ambient probe only. The terrain stays white-lit (good for ground-hue
readability), and its dusk darkness comes from `N.L` (the sun's direction) and the exposure ramp.

**Caveats:** post-exposure also darkens the fruit (a data channel): hue is unchanged but luminance drops, so keep the end value modest. Not done, left as options: making the terrain shader use the sun's colour and intensity (a visual-channel change), fading direct light behind the ridge,
and an authored colour-grading LUT per time of day. (The `LegacyClock` model was later removed; see the cleanup entry at the end of this section.)


---

## Lighting performance: ambient rebuilds in steps, terrain tint uploaded only on change

**Symptom:** a frame-rate drop after the SolarHybrid lighting model. **Suspects found by reading the code (not measured):** (1) `DynamicGI.UpdateEnvironment()` (re-renders the sky into the environment cubemap, with a GPU readback) was called every 0.5 s and
`RenderSettings.ambientMode`/`ambientIntensity` were assigned every frame, which can mark the environment dirty; (2) `TerrainManager.UpdateTerrainLighting` re-uploaded the mesh's vertex colours every frame (reading `mesh.colors` allocates a copy; the mesh is now 201,601
vertices, 3x the size when it was last measured at ~210 fps), although the terrain shader ignores vertex colours. **Changes:** the ambient probe is rebuilt only when `ambientUpdateInterval` (1.5 s) has passed and the sun has moved `ambientUpdateMinDegrees` (2) (and once at the
start; interval 0 = only once; frozen-sun Interludes rebuild once), the ambient mode is set only when it differs, post-exposure is written only when it changes, the terrain tint upload is skipped unless the ambient colour changed by more than 0.002, and a profiler sample
(`SunController.ApplyHybridLighting`) marks the per-frame work. If frames are still low: set `ambientUpdateInterval` to 0, compare with `LegacyClock`, and look at the profiler. The step in ambient intensity between rebuilds is at most about 0.05, which should not be visible.

---

## Lighting cleanup: the LegacyClock model and the terrain vertex tint were removed

Once the SolarHybrid lighting was confirmed good (and the frame rate recovered), the old path was deleted rather than kept for A/B: the `SunLightingModel` enum and `sunLightingModel` field, the dawn/noon palette (`sunIntensityDawn/Noon`, `skyColorDawn/Noon`), `SunController.UpdateSunColorAndIntensity/UpdateSkyAndAmbient/CurrentAmbientColor`, and `TerrainManager.UpdateTerrainLighting` with its wiring (the terrain shader never used vertex colours, so it only cost time).
`SunController.ApplyHybridLighting`/`EvaluateHybrid` were renamed `ApplyLighting`/`EvaluateLighting`. All four lighting assets (SkyboxMaterial, the scene's Global Volume profile, DefaultVolumeProfile, SampleSceneProfile) are still referenced, so none were deleted. `minSunElevation` is kept as an optional floor on the light's elevation (default 0). The earlier entries above stay as history; to recover the old palette use git.

---

## Sun start and end are both elevations

`dayStartFraction` (fraction of the daylight elapsed) was replaced by `sunStartElevation` (30), so the start and the end (`sunEndElevation`) use the same calculation: the hour angle at which the sun reaches that elevation, morning side for the start and afternoon side for the end. Earlier entries mentioning `dayStartFraction` are history. Interludes freeze the sun at solar noon (hour angle 0), independent of both.



---

## Logging redesigned for exact replay: per-frame trajectory, event log, manifest (replaces `movement.csv` / `session_metadata.json`)

**Decision:** `DataLogger` now writes `trajectory.csv` (every rendered frame: `t, x, z, yaw, pitch, keys`), `events.csv` (sparse discrete
events, including every fruit with its index `k`), `harvests.csv` (derived bout summary) and `manifest.json` (full `SessionConfig` via
`JsonUtility.ToJson`, world file sha256, build commit, display and frame statistics, a null `participantId`). No version label: nothing
had been collected in the old schema, so it was replaced outright (`movement.csv`'s `harvesting`/`focus_tree_id` and the per-tree
registry in the metadata are gone; the registry lives in the world file, which is archived by hash in `ForagingData/_worlds/`).

**Why per frame, and state rather than inputs.** `HarvestManager` decides range, bearing cone and fruit timing every rendered frame from
`transform.position` and the camera yaw. A 10 Hz trace cannot reproduce when the cone was entered or left, hence the fruit times.
Logging the state `HarvestManager` reads, in `Update` after it (the logger runs at order 20), makes the outcome a deterministic function
of (trajectory, world), checked by `scripts/replay.py`. Replaying inputs through Unity's physics (sliding along mountains, variable
`dt`) would not be deterministic. The cost is about 750 KB for 150 s at the 120 fps cap (about 375 KB at 60 fps, the size of the old 10 Hz file with its visibility lists).

**Rejected:** (a) keeping `visible_tree_ids/distances`: derived (pose + terrain occlusion), bulky, recomputable offline; (b) a fixed
20-30 Hz log: simpler for agents but cannot reproduce harvest gating exactly (agents resample with `replay.steps` instead); (c) copying the
4 MB world into every session folder (hash + one archive instead); (d) Parquet (CSV is readable and a session is under 1 MB); (e) a
hand-enumerated config block in the metadata (it had silently omitted look sensitivity, sun and harvest-timing parameters; the serialized
asset cannot omit anything).

**Details future-us might "fix":** `t` is a double accumulated from `Time.deltaTime` by the logger itself (it stands still while an
instruction screen sets `timeScale` 0), not `SunController`'s clock, so events and rows share one clock exactly; `harvest_release` events
for bouts the Interlude cancels or the session end closes are not explained by the keys, so the replay takes them from the log and marks
them `forced` (only a release at a `trial_end`'s time or on the session's last frames; any other logged release must be reproduced by the key
rules, or `verify` flags it); a frame gets a trajectory row iff `Time.deltaTime > 0` (not by the current `timeScale`, which an instruction
screen flips mid-frame), `HarvestManager` does nothing on a zero-time frame, and `CameraController` runs at order -5 so the yaw
`HarvestManager` reads is the frame's own; events on a session's last frame may differ by one frame from the replay (it depends on whether the sun clock or the harvest
update ran first), so `verify` ignores that frame. Removing `maxVisibilityDistance`, `movementSampleInterval` and `terrainOcclusionMask`
from `DataLogger` leaves stale serialized values in the scene until it is next saved.


---

## Frame rate capped at 120 (`SessionConfig.targetFrameRate`), vsync off

`GameManager.Awake` sets `QualitySettings.vSyncCount = 0` and `Application.targetFrameRate` from the config (default 120, matching common VR refresh
rates). Reason: the per-frame trajectory log scales with frame rate (an uncapped Interlude ran at ~530 fps, ~24 KB/s). Rejected: vsync alone
(follows each participant's monitor, so 144/240 Hz machines would log more and pacing would differ between participants; Unity also ignores
`targetFrameRate` while vsync is on). Cost: possible tearing on 60 Hz monitors. Game logic uses `deltaTime`, so behaviour does not depend on the rate.


---

## Interludes cut to 5 trials; the time limit removed from the instructions

`interludeTrialCount` is 5 on S1-S4_Interlude (practice stays 3; was 10), and `instructions_interlude.txt` no longer says "You have {trial_seconds} seconds for each choice"
(the on-screen countdown shows it; the placeholder is still supported). Consequence of the shorter block (`trial_mix`): S1-S2 get 2 contrasts (relevant feature + ignored-feature
check), 2 graded, 1 extrapolation; S3-S4 get 2 contrasts, 1 graded, 2 extrapolation. S3 loses its ignored-shape check and S4 (three relevant features) has no moisture contrast, so
moisture is probed only through the extrapolation trade-offs. The mix function was deliberately not changed; revisit it if direct moisture or ignored-feature coverage is wanted back.


---

## Start clearing 31 -> 8; Interlude trials aim the camera at the pair vertically

`startClearingRadius` is 8 on P, S1-S4 and their Interludes (the Interlude assets must match, `scripts/interlude.py` checks it; worlds and Interlude files regenerated). With `treeSpacing` 23 the nearest lattice ring sits
17-23 from the spawn, and 31 removed that whole ring (nearest bush ~36 away); 8 = 31 - 23, one spacing less, brings the ring back (nearest bush 17-23 away, ~1-2 s from harvest range). Any value up to ~17 gives identical worlds, so 8 is
not a tuned number, only "no clearing beyond the spawn point". All worlds changed (bush counts and the attribute/reward draws shift because the lattice has more sites); nothing had been collected on the old ones.

Interlude trials used pitch 0, which showed a lot of sky. `InterludeManager.PitchTowardsPair` sets the pitch at each teleport so the average of the two bushes' `Tree.GetVisibleCenter()` (canopy base + a quarter of its height, the middle of
the visible half-buried ellipsoid) is on the centre line. Rejected: aiming at bush bases (`GetWorldCenter`, the ground-level canopy centre) which would put the visible bushes in the upper half of the view; aiming at the crowns. The yaw is still from the trial file.


---

## Visibility is reconstructed offline (`scripts/visibility.py`), not logged; Interlude freshness test

**Decision:** which bushes the participant could see is derived from trajectory + world + camera, not stored. A bush is visible when any of 11 points on the camera-facing upper surface of its canopy (a half-buried ellipsoid: radius = canopy radius, vertical radius = half the
shape-dependent canopy height) is inside the frustum and a 3-unit-step heightfield march over the world's elevation grid clears the terrain. Output is sparse per step (id, azimuth, elevation, distance, angular size, `visible_fraction`), so resolvability thresholds
(`min_angular_deg`, `max_distance`) are the analyst's choice, not baked into the data. Terrain-only occlusion: bushes do not hide each other (a limitation).

**Why not log it (as the old `movement.csv` did):** it is a deterministic function of what is already logged, and the old rule was poor. It tested a 2-unit box at the bush's *centre*, which sits at ground level (the canopy is half-buried), against a physics ray that ends on the ground
surface. Validated against the old logs (20 debug sessions whose world matches exactly): the game's lists include only ~55% of in-frustum bushes whose terrain line is clear and ~38% of grazing ones, i.e. the ground-level endpoint made the flag nearly a coin flip. The reconstruction
uses points on the canopy surface instead. Validation of the machinery itself against those logs: the world's elevation grid reproduces the registry's bush heights to 0.000, the camera is `terrain + eyeHeight` (median 5.100), 99% of the game's visible bushes pass the frustum test, and bushes my march
blocks by more than 1 unit are in the game's list only 0.6-1.3% of the time (2-5 units: 6.7% of 165). There is no exact ground truth for occlusion; the new logs deliberately do not carry visibility, so this cannot be re-checked against the game.

**Interlude freshness:** `test_committed_interlude_file_is_fresh` regenerates each Interlude and compares it to the committed `.interlude.json` (numbers to 1e-6). Rejected: a parameter echo plus a Unity startup warning (more code for a check the tests already give, since the
person regenerates by script anyway); the session `.world` files keep Unity's existing startup check.


---

## Agents are actor x critic x memory with the percept in the engine (v1 framework)

**Decision:** an agent is `ComposedAgent(actor, critic, memory, percept)` (`scripts/agents.py`), run by `sim.run_episode`.
- **Memory** is the constraint on the other two: it holds dense per-bush records (position, radius, attributes, spent, fruits taken) and a reward *list* per bush (one entry per fruit). The actor may use only that map; the critic learns only from `memory.experiences()`, which is derived from the reward lists, so a forgetful memory limits what is learned without any extra plumbing. `FullKnowledge` is preloaded with the whole map (no rewards), `FullMemory` accumulates what it sees and gets.
- **Critic** = value representation + learning rule: `value(attributes, ids) -> (mean, sd)`, `update(memory)`, `freeze()`. A function of attributes, not bush id, so it can score Interlude bushes; the oracle also accepts world ids (needed because toy test worlds carry values that do not follow from their attributes).
- **Actor** = the policy: `act(view) -> Harvest | Explore | Look | Stop`, `keep_harvesting` (leave/peek), and `choose_between` (Interlude). Value and rate utilities are computed from the critic (`View.values`), so an actor cannot read the true rewards; the choice rule (hard-max or softmax) is part of the actor and returns probabilities so likelihoods can be fit to human choices later. Planning and re-planning live in the planner actor: it plans at the first decision and again only when the map in memory or the critic's version changes, so a full-knowledge oracle plans once.
- **Percept** is not a component: it is the sensor the engine applies (`ConePercept(angle, distance)`, observed every 5 units of walking and after every look; see the next entry for where it lives). Walking, exploring and looking are actions of the actor with time costs (their costs live in `scripts/costs.py`; see "Motor costs" below). Rejected: percept as a component (the user's call: perception is what the body gets, and the policy decides where to look and walk).

**Interludes for simulated agents** come from `interlude.generate_interlude(..., seed=)` (new `seed` and override arguments): the very generator and trials the game uses, for the same world seed. A reduced simulation-only search was rejected so that what an agent is scored on is what a human sees; if more trials are needed to separate agents, change the human Interludes too. The critic is frozen, the pair is put in a fresh memory (both bushes are in view by construction), and the actor's own utility and choice rule pick `n_samples` times (sampled, not probability-weighted); ties are broken at random in the Interlude (the session keeps the original lowest-index tie rule so results are unchanged). The per-trial result is correct / incorrect against the trial's correct side ("either" always counts), scored overall and by trial type, plus the expected hidden bonus.

**Not modelled / limits:** the cone ignores terrain occlusion (use `visibility.py` to model it later) and vertical extent; attributes are seen exactly; memory never forgets; the planner treats partly harvested bushes as gone when it re-plans; the Interlude evaluation assumes both bushes are in view and ignores its 10 s limit. The old `choose_target` agent protocol and `State` helpers were removed; `NearestAgent`, `GreedyAgent` and `PlannerAgent` are now factory functions that build composed agents, and the planner's attributes (`plan`, `plan_value`, `exact`, `nodes`) are read through the agent.

**Verification of the refactor:** before changing anything, the pre-refactor engine's totals, visit sequences and walk/harvest/idle times were captured for `nearest`, `greedy_rate_15`, `greedy_value_10`, `greedy_rate_5` and `plan_beam` on 6 S1 and 4 S3 worlds (90 s sessions); the composed agents reproduce all 50 runs exactly (not stored in the repo; the 15 tests in `test_sim.py`, including the brute-force planner checks, keep guarding the arithmetic).


---

## Perception belongs to the environment (`scripts/perception.py`), not to the agent

**Decision:** the sensor model (`Observation`, `NullPercept`, `ConePercept`, `percept_from_params`, `percept_for`) lives in `scripts/perception.py` and is resolved by the engine in this order: `agent.percept` (an explicit per-agent override), the run's `percept=` argument (`run_episode`, `run_n`, `compare`, `evaluate_n`, `sim.py --percept ANGLE,DISTANCE`), then the world's own default (`world.percept` if set, else a cone as wide as the session camera's horizontal field of view with no distance limit: 107.5 deg for the game's 75 deg vertical FOV at 16:9, from `camera_field_of_view`).

**Why:** perception models the participant's body and screen (field of view, how far attributes can be resolved, occlusion), which are the same for every agent in a session; agents then differ only in memory, critic and actor, so comparisons are fair by construction and there is one place to tune the constraints as they are calibrated against participants' logged visible sets (`visibility.py`). Resolvability numbers are simulation knobs, not game config, so they are not SessionConfig fields. The per-agent override and per-run argument stay for sensitivity sweeps and deliberately different observers. Rejected: a percept attribute required on every agent (what v1 had: `None` meant "sees nothing", which silently made limited-memory agents blind).

**Detail:** during a harvest walk the engine looks every 5 units from the walk's start but ends at exactly `start + direction * walk`, so oracle agents' results do not depend on the sensor (they are bit-identical to the pre-refactor engine with the default cone, a narrow cone or none; a test and a 40-run comparison against the captured pre-refactor results guard this).


---

## Agent boundaries tightened: a narrow `Body`, explicit grants of world knowledge, the Interlude through the agent

**Decision:** three interface changes so that "the agent only knows what it was told or has seen" is enforced by the interfaces, not by habit.
- **`Body`.** The engine hands an actor a snapshot (`State.body()`: position copy, heading, time left, total reward), not its `State` (which carries the world, the true spent flags and `fruits_taken`). `act(body)`, `keep_harvesting(body, ...)`, `View.body`.
- **Explicit grants.** `begin(task)` replaces `begin(world)` for memory and critic; `Task` gains `n_bushes` (a capacity, no positions). Components that start with the world's own knowledge (`FullKnowledge`, `OracleCritic`) are flagged `omniscient = True` and are the only ones `ComposedAgent` calls `grant(WorldKnowledge)` on (bush table, true values, reward function). The agent keeps no `world` attribute, and base classes store none. A learning critic or limited memory is never handed it. Zero-argument agent factories still work because the grant happens at `begin_session`. The `ids` argument of `Critic.value` stays: a bush id is what a participant also has (it can tell the bushes it has seen apart); the leak was the oracle reading `world.value` implicitly, and that is now a visible grant.
- **Interlude through the agent.** `ComposedAgent.begin_interlude(knowledge)` freezes the critic (carried over), starts a fresh memory for the Interlude's own bushes (the session's bush ids mean nothing there; the session memory is left as it was) and grants omniscient components the Interlude's table. At each trial the evaluator shows the agent both bushes as an observation, at the spawn pose, whatever its sensor, then calls `agent.choose_between(body, ids, rng)`. This removes the `memory.world_ids` flag, `_PairWorld` and the fake state.

**Why both bushes are always shown (the PI's call):** the trials are built so both are in view, and the Interlude is meant to test what was learned, not perception. Rejected: applying the percept in the Interlude with an unseen-bush rule (a narrow-cone agent would fail trials a participant could not).

**Unchanged on purpose:** `keep_harvesting` stays a callback during a `Harvest` (a second actor-to-engine channel besides the returned action); an agent-level percept override stays an explicit exception to "the sensor belongs to the environment". `begin_interlude` ends the session for that agent (an oracle's granted table is replaced).

**Verification:** the 40 fast-agent runs and a `plan_beam` world from the pre-refactor capture are bit-identical, and the Interlude scores (oracle and `nearest`, including per-type accuracies) are unchanged. New tests cover the `Body` snapshot, that only flagged components are granted knowledge, that components begin with a `Task` and the agent keeps no world, that every agent sees the pair whatever its sensor, the fresh Interlude memory leaving the session's untouched, the carried-over frozen critic, and an oracle granted the Interlude's table.


---

## Interlude commitment: the first bush harvested is the choice, and the other bush is hidden

**Problem:** the Interlude registered a choice only when a bush reached its full fruit count, so a participant could harvest part of one bush, release Space and switch to the other, which muddies the forced-choice measure.

**Decision:** unless `interludeSwitchPolicy` is Allow, starting a harvest (`HarvestManager.OnHarvestBoutStarted`) commits that bush as the choice and takes the other away; the default policy is **Hide** (the other bush shrinks away over `hideSeconds` = 0.4 s and is deactivated). The participant still holds Space until the chosen bush is finished, and the trial ends then (or on the time limit; a committed trial that times out still counts as that choice, a trial with no commitment still counts as none). `isHarvested` is set on the other bush at once, which `HarvestManager` already skips (no target, highlight or ring), so it cannot be switched to during the fade; no `RefreshTrees` is needed mid-bout.

**Rejected:** Allow-and-log (does not prevent switching; kept as a policy for comparison); Exhaust (reuses the spent look, but in the sessions "spent" means "you emptied it", so an unharvested bush looking spent could read as "that one was empty" and colour later trials; available as a policy); Lock (a visible but dead bush with no explanation, so Space seems to do nothing; available as a policy); committing on the first fruit (the PI chose the start of harvesting); an extra sentence in the Interlude instructions (the PI chose not to announce the rule). The policy is a `SessionConfig` field (order Allow 0, Lock 1, Exhaust 2, Hide 3, stored as a number in the manifest) so it can be compared in a pilot without code changes; it needs no regeneration.

**Data and tooling:** `choice_lock` event (note: `committed`, `locked`, `policy`); `interlude.csv` gains a trailing `locked_at` column. `scripts/replay.py` makes the locked bush unharvestable from the frame after the press that caused the lock (the lock is logged on the press frame), and `scripts/visibility.py` removes the locked bush `HIDE_SECONDS` after the event under Hide (it stays visible under Exhaust and Lock). `HIDE_SECONDS` mirrors the `InterludeManager.hideSeconds` default; change them together. The simulator is unaffected (agents pick between the pair directly).


---

## Motor costs: turning and key presses cost time, and every action must cost some

**Problem:** the simulator charged walking and fruit time only (plus a placeholder cost for `Look`). Turning with the mouse to face a bush and pressing W and Space are not free for a participant, so the agents were optimistic and a loop of zero-cost actions (`Look(0)`, `Explore` into a wall) could hang a whole run.

**Decision:** `scripts/costs.py` holds one set of constants and one function, `approach`, that the engine, `View.travel_times` and `PlannerActor` all call, so what an agent expects an action to cost is what is charged. A walk or a harvest costs turn + key presses + walking: turning to face the bush (`0.17 s + angle / 480 deg/s`, free under a 5 degree deadband when walking; in range it needs only enough turn to bring the bush into the harvest cone), a W press (0.2 s) before a walk, a Space press (0.3 s) before the fruits. `Look` costs the same turn formula. Fitted to the developer's debug logs (91 turns, 58 presses); the W press is a guess; none is participant data, so **recalibrate from real logs**. The decision time between actions (the median wait from releasing Space to pressing W was 0.65 s) is the agent's, not a motor cost, and is not modelled.
- Every action costs time: `Look(0)`, `Explore` of zero or negative distance and a bush id that does not exist are `ValueError`s; an action that still consumed nothing (zeroed constants) is a `RuntimeError`, so a session always advances. An `Explore` blocked at once still costs its turn and W press.
- The engine refuses `Harvest(j)` for a bush the agent's memory has never seen (before, a blind actor could walk to and harvest any id and its critic trained on a placeholder row).
- A wall and the clock cutting the same walking chunk no longer lose the unwalked time; the fruit loop tolerates the 1e-13 drift of repeated subtraction (300 fruits fit a 60 s session of 0.2 s fruits, as the planner predicts).
- `PlannerActor` tracks heading, leaves out bushes the critic values at zero or less (the bound assumed positive values and "exact" was not optimal otherwise), and its plan value again equals what the engine pays.
- `UtilityActor`'s fallback (nothing within `max_walk_time`) goes through the choice rule over `-time`, not a hard argmin, so likelihoods of choices stay defined.
- In an Interlude a non-omniscient critic is given `ids=None` (the session's ids are another table's); `Critic.update` bumps `version` after each refit of a critic that learns (overrides `_fit`), so subclasses cannot forget.

**Rejected:** a flat per-action decision time (not physical, and it would charge the same for a 1 degree and a 180 degree turn); counting a key press only when W was not already down (chained `Explore`s would be free to continue, and the engine would have to track key state); modelling turn speed per angle band (91 episodes support a line, not bands).

**Consequences:** the simulated totals and the Interlude scores change for every agent, so the baselines are stale; the tests run with the motor costs off by default (`scripts/conftest.py`, marker `motor_costs` turns them on) so that their timing is stated in walking and fruit seconds.


---

## The first learner: a delta rule on swappable features, with a swappable prior

**Decision:** `DeltaRuleCritic(features, prior, alpha)` in `scripts/agents.py`. Within a bush the state does not change and nothing is bootstrapped, so TD(0) is the Rescorla-Wagner delta rule: `value(x) = prior + w . phi(x)`, and after each bush `w += alpha * (bush mean reward - value(x_bush)) * phi(x_bush)`.
- **Learns per bush, not per fruit** (PI: a per-fruit timescale is too short for plausible human updating; leave/peek decisions are the fruit-timescale part and belong to the actor, reading `memory.rewards`). `Critic.update_on` ("fruit" by default, so existing critics are unchanged; "bush" here) decides when `ComposedAgent` calls `update`; the engine calls `agent.end_visit(j)` when a harvest bout ends (empty, left, or clock out). The critic learns from `Memory.bush_stats()` (fruits taken, mean, within-bush variance of each bush; only the mean is used for now, the variance is there for later).
- **Features are a swappable object** (`Features`: attributes -> unit-length vector, so `phi . phi'` is a kernel). `RBFFeatures` first: Gaussian bumps per attribute (additive, default) or on the joint grid. SSP features are the planned next implementation; the additive form matches the reward function's structure (a sum of per-attribute terms) and avoids learning 3-D conjunctions from ~10 bushes.
- **The prior is a swappable object** (`Prior`). `NeutralPrior(initial=1.0)`: a small positive number before any bush is done (any positive value gives the same rate-utility ranking), then the mean of the bush means. The features learn deviations from it; where they say nothing the agent falls back to it. So the first bush teaches only the baseline. An optimistic prior would be an exploration mechanism: not built.
- **No uncertainty or novelty in the critic** (`sd = 0`). Novelty, uncertainty bonuses and exploration belong to the actor (PI), computed from memory; the `(mean, sd)` interface is unchanged.

**Known behaviour, not a bug:** with one visit per bush, unit-norm additive features overlap strongly (two bushes that differ in one attribute still have kernel ~0.67), so one pass of the delta rule is order dependent, under-scaled for alpha < 1 and can overshoot at alpha = 1 (with two bushes the poor one can end up above the baseline). It is the floor of the learner ladder on purpose. A one-off check on 8 worlds with the session durations overridden (S1 at 90 s, S4 at 150 s; not a baseline) gave delta_rate_10 333 / 1146 against nearest 261 / 981 and greedy_rate_10 (oracle) 406 / 1290, with the learned values correlating 0.95 / 0.92 with the true ones over all bushes. The agent has no exploring actor yet, so it only visits bushes its sensor has shown it.

**Rejected:** per-bush-id tables (cannot transfer to the Interlude's new bushes); a raw linear critic as the baseline (cannot represent peaked rewards; only worth keeping as a wrong-bias control); a novelty proxy in the delta-rule critic (it measures familiarity, not uncertainty, and exploration is the actor's).


---

## Results database: hash identity, labels at report time

**Decision:** simulated-agent runs go in a SQLite file, `results/results.sqlite` (repo root, flat, gitignored, separate from `ForagingData/`), keyed by fingerprints: a hash of each agent's resolved spec, of the environment (session, resolved session parameters, overrides, percept, kind, motor costs), and of the engine code (plus a separate hash of `agents.py`, the git commit and a dirty flag). Per-seed episode rows make paired comparisons possible and make "look up before running" cheap, so stale results are recognized by hash instead of being re-run or trusted. The conventions and best practices are in CLAUDE.md ("Results database").

**Names:** the PI's reports are written by Claude, so human-readable names carry no weight. Identity is the spec hash; a label is generated at report time from only the fields that differ among the agents in a table; experiments are referred to by a free-text `tag`. This lets the naming convention change later without a migration.

**Rejected naming schemes (brainstormed):** fixed slots (`greedy-rate.delta.rbf.neutral.fullmem`: sweeps give identical names), key-value tokens (long, order drifts), family name plus differences from a default (short, but a name's meaning changes when the default does), a short human-chosen name plus hash (carries no information), policy+learner pairs (hide prior and memory), and slots plus numeric suffix (`...~a0.2`; the best stored-name option, dropped because generated labels are always the minimal distinguishing description).

**Hash of the resolved spec** (defaults written out) rather than of the non-default parameters only: stricter, so adding a parameter to a component rehashes every agent that uses it, handled by a re-hash migration from the stored spec JSON. The alternative (hash only non-defaults) keeps old hashes when a parameter is added but lets a changed default silently change behavior under the same id.

**Not stored (PI's call):** action traces (add a separate table later if behavior analysis needs them), committed summary exports (a session can re-derive them from the file), human data (a separate scheme), and derived metrics (the performance metric is a TODO(PI), so raw scores are stored and the metric is computed at query time).

**Step 1 built (agent specs, no database yet):** `scripts/specs.py` (`Component`, `spec_hash`, `build`, `flatten`, `labels`), with every memory, critic, features, prior, choice rule, actor and percept in `agents.py` / `perception.py` deriving from `Component`; `ComposedAgent.spec()` / `spec_hash()` and `agents.build_agent(spec)`. The constructor arguments are captured automatically (the outermost call, defaults resolved), so a new component needs no spec code; only a class that substitutes a default for `None` (`DeltaRuleCritic`, `UtilityActor`) overrides `params()`. The registry's old names (`nearest`, `greedy_rate_15`...) are unchanged: they are factories, and their specs are derived. Numbers are canonicalized by value (`10` = `10.0` = a numpy float) so the same agent never gets two hashes; a component holding a function or an array has no spec (a `UtilityActor` must name its utility), and the `type` key is reserved. The hash of `nearest` is pinned in `test_specs.py`, so adding a parameter to a component fails loudly until the pin is updated on purpose.

**Step 2 built (fingerprints, `scripts/fingerprint.py`):** the environment hash covers only the SessionConfig fields the simulator reads (`SIM_FIELDS`, 39 of the 110), not the whole asset: hashing everything would give a new "environment" every time the PI tweaks a volume or colour in the Inspector, which is normal churn. The list is not curated by hand: a (slow) test traces which fields a run reads (sessions P, S1, S3, S4, an exploring walk, an Interlude evaluation) through a recording namespace and fails when the code reads a field that is not listed, or a listed one that nothing reads. The world seed is excluded (seeds are the rows of the results), and so is the agent. The environment dict also carries the overrides (readable), the run's percept override, kind (session or Interlude) with `n_samples`, the Interlude asset's own hash, and the motor-cost constants. Code is two hashes, engine (`sim`, `costs`, `perception`, `world`, `interlude`) and agents (`agents`, `specs`), so editing an agent does not make every engine result look stale; both are of file bytes, so a comment edit is a false alarm rather than a missed change. Rejected: a version number kept by hand (forgotten), hashing the whole Python import graph (a test file or a helper unrelated to the engine would count), and recording only the git commit (the tree is usually dirty).

**Step 3 built (`scripts/results.py`, `sim.py --record --tag`):** SQLite at `results/results.sqlite` (gitignored). An episode is unique on (agent, environment, code version, seed); `record_run` looks the seeds up and computes only the missing ones. Choices that are not obvious from the schema:
- **Code versions are keyed by the two hashes only**, not by commit: identical hashes are identical code, so a later run on a clean commit upgrades a dirty record's commit and flag (never the reverse), and results are not recomputed because the commit moved.
- **`run_episodes` links a run to every episode it used, computed or reused**, so a tag finds exactly what that call saw; `episodes.computed_by` says which run paid for it. Rejected: one tag per episode (a re-analysis under a new tag would then have to recompute or lose its seeds).
- **An Interlude episode is the session plus the Interlude** (the Interlude needs the agent's session), stored in one row; `n_samples` is part of the environment, so 5 and 200 samples are different records. Per-trial-type accuracy is in `episode_types` (a table, so a new trial type needs no new column).
- **A cut-short run keeps its episodes** (linked, `seeds` rewritten to what was done, `[interrupted: ...]` in the note) instead of rolling everything back, since a 100-seed sweep stopped at seed 90 is worth keeping; `delete_run` is the only removal and is for runs that never should have been recorded.
- Editing `sim.py` for anything, even the command line, changes the engine hash and so starts new records: the false alarm is the safe error, and a result worth keeping across such an edit is re-derived by running it again.
- `agent_params.value` has no declared column type, so numbers stay numbers (`value >= 0.5` works) and booleans are stored as 0/1.

**Step 4 built (`scripts/analysis.py`, `specs.labels` revised):** the helpers refuse to compare what is not comparable instead of quietly pooling it. `select` demands one environment and one code version per (agent, seed) and raises with what to narrow by; the default is the current engine hash, and a stale or dirty selection carries notes that a report repeats. Paired differences use only the seeds both agents have. `component_effect` matches agents on every spec parameter outside the factor's path and averages the paired differences of each matched group, with the standard error across groups; an unmatched agent (it differs in two things) is not compared, which is the point: a table of unlike agents cannot say which component helped. A factor's level is its whole sub-spec (so `critic.features` compares RBF with SSP whatever their own parameters). Labels (`specs.labels`) now omit the parameters of a component whose `type` differs (the type says it) unless two agents of the same type disagree on them, because listing every differing field made a table of unlike agents unreadable. The metric is chosen at query time; only `gap_closed` is provided, flagged as a convenience, since the performance metric is a TODO(PI).

---

## Interlude random mode (humans and simulation), 50-trial agent Interludes

**Problem:** the designed Interlude (contrast / graded / extrapolation, 5 trials) saturates: in S1 the oracle and the delta-rule learner both score about 1.0 on contrasts and extrapolation, and `nearest` scores above chance on contrasts because the ignored-feature check counts either answer. It cannot tell a good learned value function from a better one.

**Decision (PI):** a `random` mode of the same generator: independent uniform shape and colour for the two bushes, moisture from the terrain at the placement as always (the placement is a random valid site; no moisture-relation search, so the pool is 40 000 placements instead of 500 000 and a world takes about 1 s instead of several), pairs closer than the tie tolerance redrawn (always a correct side), sides balanced, geometry unchanged. Scoring is accuracy only for now; regret, a per-trial table and a normalized measure are deferred to a possible later mode. The stimulus is available to humans too: `SessionConfig.interludeMode` (enum `Designed` 0, `Random` 1, logged in the manifest) is read by `scripts/interlude.py`, not by the game, which only plays the generated file (so the sidecar format is unchanged; random files carry `"mode": "random"`, designed files are byte-identical to before). Only the five Interlude assets got the field (Designed); Python treats an asset without it as designed, and the explicit `mode=` argument (`sim.py --interlude-mode`) overrides the asset.

**Trial count:** 50 for agents via the existing `interlude_trial_count` session override, which is part of the environment hash. This is a deliberate exception to the earlier rule that sim-only Interlude variants are rejected (a person would not sit through 50 trials of about 10 s): the generator, geometry and scoring are the same, only the count differs, and the override is recorded with every result. Human assets keep small counts.

**Plumbing:** `interlude_mode` is a field in `SIM_FIELDS` and, for an Interlude run, an explicit key of the environment (`environment(..., interlude_mode=)`, `record_run(..., interlude_mode=)`, `sim.py --interlude-mode`), so designed and random runs never share a record. The Interlude cache in `sim.get_interlude` now ignores `session_duration` (it cannot change an Interlude), so sessions of different lengths share one Interlude per seed. First timing: 5 seeds x 3 agents with 50 random trials took 8 s in total; in that small sample `nearest` scored 0.46 (chance), the learner 0.92 and the oracle 1.00.

**Per-fruit events for agents (schema v2, `episode_fruits`):** the engine's `Result.fruits` lists `(t, bush, k, reward, running_total)` for every fruit an agent takes, and `record_run` stores them (about 200 rows per 90 s episode), shaped like the human `fruit` rows in `events.csv` (`t`, `tree_id`, `k`, `reward`, `running_total`) so one analysis can read both. `t` is the session time at the moment the fruit is taken, after its harvest interval (the loop subtracts the interval, then pays the reward). Reward rate, cumulative reward and smoothing (binning or low-pass) are computed from these at query time, so no bin width is fixed in the database. Rejected: stored time bins (fix a resolution), and re-simulating on demand (the result would not be keyed to the code and environment it came from). Not stored: positions, headings or any other action (the "no traces for now" call stands; a visit sequence is recoverable from the bush column). Episodes recorded before this schema (engine hash `a616...` and earlier) have no fruits and are stale by hash anyway; opening a v1 file copies it to `<db>.bak-v1` and adds the table.

**Update: the five Interlude assets are set to Random (for human testing):** `interludeMode: 1` on P/S1-S4 `_Interlude`, human trial counts unchanged (3 practice, 5 otherwise), and the committed `*.interlude.json` regenerated (`scripts/interlude.py P_Interlude S1_Interlude ...`). To go back, set the field to Designed and regenerate. Consequences: `sim.py --interlude` without `--interlude-mode` now follows the asset (random); the designed-stimulus tests force `mode="designed"` and the freshness test regenerates with the asset's own mode. Earlier simulation records are unaffected because each Interlude environment records its mode explicitly.

**Reward-rate curves (`analysis.reward_rate_curve`, `plots.plot_reward_rate`):** computed at query time from `episode_fruits`, so the smoothing is a choice of the analysis, not of the record. Two smoothers, both PI-endorsed defaults: fixed bins (rate = reward in the bin over the bin's length, so a shorter last bin is not undercounted) and a zero-phase Gaussian low-pass of the fruit impulse train on a 0.1 s grid, normalized by the filter's response to a constant so the rate does not sag at the session's edges. Rejected: a causal (exponential) filter as the default, because it lags every feature of the curve by about its time constant and the time axis is the point of the plot. The interval is a t-interval of the mean across seeds, unpaired between agents (a paired figure belongs to `table`). Figures use the dataviz palette's first slots in fixed order with the legend plus end markers (aqua is below 3:1 on the light surface, so the legend is the required relief), the footer states the engine hash, environment, dirty flag and tag, and the file goes in `results/` (gitignored).

First 10-seed trial (tag `rate-trial`, S1 at 90 s, dirty tree, engine `9e9e8eac88b6`, not for citation): the oracle greedy agent is flat at about 4.5 reward/s, `nearest` flat at about 3, and the delta-rule learner starts near `nearest` (about 2.5 to 3) and climbs to about 4 by 35 to 40 s, i.e. the expected learner signature. Ten seeds leave wide bands, and the `nearest` curve oscillates with a period of about 15 to 20 s that a 100-seed run will show whether it is real.

**Checkpoint Interludes (learning curve from one session per seed; schema v3):** `run_episode(..., checkpoints=[t, ...])` keeps a deep copy of the agent as it was at each session time, to be scored on the Interlude as if the session had ended there. The copy is taken just before the first thing that changes the agent after time `t` (a reward, or the end of a visit: `_Checkpoints.before_update`), because that is the only way its learned state can change; a time with no later update (the agent stopped, or it is the session's end) gets the final state. Verified against the real thing: the snapshot at `t` has the same critic weights as an agent that ran a session whose length is `t`. This is the PI-endorsed shortcut and it is valid only because a non-planner's behavior up to `t` does not depend on the session's length, so `Actor.deadline_dependent` (True for `PlannerActor`) makes `run_episode` refuse checkpoints; **when a planning or otherwise deadline-aware learner is built, this shortcut is to be abandoned for it and sessions of different lengths run instead** (the cache already ignores `session_duration` so they share an Interlude). The checkpoint times are part of the environment hash (a different set is a different environment), the scores go in `episode_checkpoints(episode_id, t, interlude_trials, interlude_accuracy, interlude_bonus)`, and by-trial-type accuracies are not kept per checkpoint (accuracy only, as decided for the random mode). Rejected: snapshots taken at the next action boundary (a bout of up to ~3 s of learning would leak into the earlier checkpoint) and one session per duration as the only option (10 to 100 times the compute).

First 10-seed trial (tag `learning-trial`, S1 at 90 s, random Interlude with 50 trials and 20 samples per trial, checkpoints 0 to 90 s, dirty tree, not for citation): `nearest` 0.48 at every checkpoint (chance), the oracle 1.00, the delta-rule learner 0.48 at 0 s, 0.54 at 10 s, 0.80 at 20 s, 0.87 at 45 s and 0.92 at 90 s: a clean learning curve that saturates below the oracle.

**Cumulative reward replaces the reward rate as the default trajectory plot (PI):** in the 10-seed trial the rate curves are flat for the oracle and `nearest` and wiggle with the layout of the bushes (the `nearest` oscillation of about 15 to 20 s), which hides the learner's rise; cumulative reward integrates that out and ends at the episode's total, so every curve can be checked against the table. `cumulative_curve` therefore became the default of `analysis.py curve` (`--quantity rate` keeps the rate curve), with an optional paired advantage over a baseline agent (`--baseline`), which turns "the learner's slope increases" into a curve that is flat at zero until it starts beating the baseline and then rises. In the trial the learner tracks `nearest` for about 20 s, then pulls away (advantage about 60 at 90 s, against about 130 for the oracle). The `rate-trial` records were re-recorded after the engine hash moved (the checkpoint change); results identical. Ten seeds, dirty tree: not for citation.

**Reward-rate curves removed (PI):** `analysis.rate_curve` / `reward_rate_curve` (binned and Gaussian low-pass smoothing, `curve --quantity rate`) and the rate branch of the plot are deleted. The curves are too hard to read: the oracle and `nearest` are flat, the learner's rise is a few tenths of a reward per second inside wide bands, and any smoothing choice changes how the wiggle looks without making the learning easier to see. Cumulative reward and the paired advantage over a baseline (`cumulative_curve`) carry the same information and read directly; the Interlude learning curve (`checkpoint_curve`) carries the learning itself. `plots.plot_reward_rate` became `plots.plot_cumulative_reward` and `RateCurves` became `CumulativeCurves`. The earlier entry above describes what was built and why it was dropped. The 100-seed result stands: the learner's cumulative lead over `nearest` is about zero until roughly 28 s and then grows.


---

## Adversarial review: red-team against simplifier, an arbiter for disagreements, mutation testing as the evidence

**Problem:** the red-team review done by hand over several sessions found real defects (a replay that failed on every practice session, an engine that let blind agents harvest, planner results that were not optimal) and many gaps in the tests, but it was a one-off. The simplifier agent pushes the other way (less code). Run alone, each drifts: the red-team toward guards for cases that never occur, the simplifier toward removing the check that mattered.

**Decision:** `/adversarial-review` (the protocol is in `.claude/skills/adversarial-review/SKILL.md`, the arbiter's yardstick in `docs/REVIEW_POLICY.md`) runs the `red-team` and a dry-run `simplifier` in parallel on one diff, lets each answer the other's conflicting items once, and sends what is still disputed to an `arbiter`. Scientific design, the hash or meaning of stored results, and disagreements about goals are escalated to the person. The orchestration lives in a skill because subagents cannot spawn subagents. Nothing is applied until the person agrees.

**Evidence over opinion:** the red-team may report only findings it can demonstrate, and runs `scripts/mutation_check.py`, which mutates the changed lines (flip a comparison, swap + and -, off-by-one a constant, negate a condition, flip a boolean) in a scratch copy of the project and runs the tests that depend on the file; the survivors are leads for it to judge. On the first real run it flagged untested rules in the new motor-cost code (the sign of the turn, the 5 degree deadband), which the hand review had not.

**Rejected:** a hand-written mutant catalog (the patterns rot as soon as the code changes, as the first manual harness did); sending every item to the arbiter (cost, and most items are not in conflict); letting the arbiter decide scientific-design questions (CLAUDE.md reserves them for the person); letting the simplifier apply its small tier during a joint review (the point is that both sides argue before anything changes); a single reviewer with both hats (it argues with itself and always agrees).

**Cost:** two long reviews in parallel plus a short rebuttal each; the arbiter only on conflicts. For a small diff run one agent alone.


---

## An in-range harvest no longer turns the simulated view for free

**Problem (found by the first `/adversarial-review`):** `costs.approach` charged an in-range harvest only the turn needed to bring the bush inside the harvest cone (nothing when it was already inside), but `sim._harvest` still set the heading to the bush's full bearing, and `PlannerActor` copied that. Up to the canopy's angular radius plus `harvestMaxAngle` of turning was therefore free, and the next action measured its turn from a heading the player never took (a harvest at bearing 30 degrees followed by `Explore(0)` charged a 30 degree turn back that never happened). In the game harvesting does not rotate the camera.

**Decision:** `approach` returns the heading after the action: the bush's bearing when there is a walk (movement follows the view), otherwise the old heading turned only by the amount charged (unchanged when the bush was already in the cone). The engine and the planner both use it. Tests: `test_a_harvest_in_range_turns_the_view_only_as_far_as_it_is_charged`, and the planner's start heading and 20-trial plan-value tests.

**Consequences:** engine (`sim.py`, `costs.py`) and agents (`agents.py`) code hashes move, so earlier stored runs are stale by hash; simulated totals change slightly wherever a harvest was followed by a turn. Baselines in `docs/SCIENCE.md` are to be marked stale and re-run only when asked.


---

## Review of the engine-agent boundary (unit A): what changed and what was left

Found by `/adversarial-review --component` on the engine-agent boundary and time model; the reports and the reasoning are in the session's scratchpad, the outcomes here.

**Learning-curve checkpoints inside a visit:** a session that really ends mid-visit still calls `end_visit`, so a per-bush critic (`DeltaRuleCritic`, behind `delta_rate_10`) learns from that bush; the checkpoint copy was taken before that and lagged by up to one bush (10 of 36 checkpoints differed from a real shorter session on S1 at 90 s, Interlude accuracy about 0.4 points lower on average). `_Checkpoints.before_update` now applies `end_visit` to the copy when a visit with fruits is under way. Stored `episode_checkpoints` and the learning curve in SCIENCE.md predate this and are stale by hash.

**Observation after every turn (PI):** the view is now observed after the turn before a walk (an `Explore`, or a `Harvest` that walks) and after the turn of an in-range harvest, as after a `Look`: a human sees the new view at once. Before, a bush that was in the new view but dropped out of the cone within the first 5 units of the walk was never seen. Learner totals move on some seeds (paired difference about -3.5 +- 4.4 on 30 S1 seeds, not significant); oracle agents are unaffected.

**Bush ids are shuffled in the world file (PI):** the lattice enumerates sites in space order, so an id said where a bush was (corr(id, x) = 0.93; consecutive ids 44 units apart against 299 for random pairs), and every memory is sized to the bush count. `generate_world` now shuffles the finished bush table with its own stream (8, appended: the others are unchanged), so each bush keeps its attributes and rewards and only its id changes. The world files were regenerated; all stored results are stale. The Interlude files are unaffected (they use their own bush tables). The memory size still equals the world's bush count (an agent can read how many bushes exist); only the ids' meaning was removed.

**Deferred (PI):** after walking to a bush, floating-point rounding leaves the agent a hair outside its range in about 40% of cases, so harvesting the same bush again (after leaving early) is charged a W press the game would not need. No registry actor leaves a bush early, so no stored number is affected; the fix is one line in `costs.approach` (treat a sub-1e-9 walk as none) when the first such actor is written.

**Simplifications done in the same batch** (they move the hashes whatever is done, so they went in together): unused `State.world`/`State.history`, the empty `end_session` hook, `ComposedAgent.rng`, the no-sensor branch and the redundant position and depleted assignments in `_harvest`, `evaluate_n` (one test used it), the `getattr` guards in `run_episode` (only `ComposedAgent` runs), and the harvest cone's default angle now defined once (`costs.max_angle`). Kept on purpose: `_Walkable` stays lazy (building the terrain at session start would cost every episode, even those that never explore), the `world.percept` override level, and the CLI's non-`--record` comparison.

## The assessment battery (`scripts/battery.py`)

**Decision (PI):** one fixed battery for comparing agents: S1-S4 at their design durations, each with its Interlude, checkpoints at fractions of the session (0, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0) so a learning curve has a common time axis, each agent fresh in every session (no carry-over: the sessions' reward functions differ on purpose; a curriculum variant that carries the critic is a separate battery for later), 10 seeds by default (noisy, scaled up when needed), no ceiling reference defined (scoring picks references from whichever agents ran).

**One pick per Interlude trial (`n_samples` 1):** the earlier default of 20 or 200 repeated picks estimates an agent's choice probabilities; a person gives one answer per trial, and the PI wants the spread over 50 trials to be comparable to human data, so the battery draws one. (Tie-breaking and softmax noise are then part of the measured variance, as they would be for a person.)

**Scores and plots are not defined by the battery.** Everything they need is stored (per-episode totals and times, Interlude accuracy at every checkpoint, per-fruit events), so reward gap closed, final accuracy, area under the learning curve, time or stops to a criterion and the cross-session mean and minimum can be written and changed afterwards without re-running. Two things cannot be recovered without a re-run, because they are measured while the agent is alive: the checkpoint times (their resolution) and the value-function fidelity (the critic's values against the true values on the Interlude's bushes); the PI chose to keep accuracy only and the seven checkpoints for now.

**Parallelism considered and deferred.** Measured per (session, seed): world 0.05 s, Interlude generation about 1.05 s (shared by every agent), session 0.01-0.03 s, seven checkpoint evaluations 0.3-0.45 s at 20 samples (about 0.03 s at one), on a 16-core machine. With one pick per trial the first full population (24 agents x 4 sessions x 10 seeds) is a few minutes serially, so no pool is built yet. If scale demands it: a process pool over (session, seed) tasks (each worker builds the world and Interlude once, runs every agent, returns rows; the parent is the only SQLite writer and checks what is recorded before dispatching), one numpy thread per worker, a test that parallel rows equal serial rows (all randomness derives from the world seed), and optionally an on-disk Interlude cache. Rejected: threads (GIL), one process per agent (repeats the Interlude generation).

**Figure layout: one panel per session, seaborn lines, the lowest agent as the advantage baseline (PI):** every figure is now a grid of panels (2 x 2 for S1-S4) drawn with `seaborn.lineplot` from the per-seed curves (mean and 95% bootstrap interval, `hue` = agent name; `plots.long_form` builds the DataFrame). The interval is therefore seaborn's bootstrap over seeds rather than the t-interval the numeric API (`cumulative_curve`, `checkpoint_curve`) still reports; with 10 seeds the two differ slightly and the bootstrap is a little narrower. The "advantage" baseline is no longer chosen by name: it is the lowest-performing agent of each session (lowest mean total reward), so panels can have different baselines and each panel names its own. A figure holds at most 8 agents (the palette); the 24-agent main population is plotted as five groups (`battery.GROUPS`), each including `nearest`, so colours mean the same thing within a figure and a group answers one question. Rejected: one panel with every agent (unreadable), colours assigned per panel (the same agent would change colour between sessions).

**Interlude pairs: travel times within 10 ms are a tie (`agents.INTERLUDE_TIME_TIE`):** the two bushes of an Interlude trial are built equal in the terms the harvest rules use (canopy-edge distance and inner-edge bearing), but turning to the *centre* of a wider canopy takes about 4 ms longer, and an agent whose utility includes travel time (`nearest`, and any rate-utility agent whose values tie, such as an untrained learner at checkpoint 0) picked the quicker bush every time, i.e. the narrower canopy. Where shape is rewarded the floor agent was therefore not at chance: in the first battery smoke run its Interlude accuracy was 0.71 (S2, shape peak) and 0.27 (S4, shape inverted), against 0.50 where shape is irrelevant, and the narrower canopy was the quicker in 50 of 50 (S2) and 49 of 50 (S4) trials. `View.equalize_times(candidates, tolerance)` now gives an Interlude pair that differ by less than the tolerance one common (mean) travel time, applied in `UtilityActor.choose_between`; values still decide when they differ, and a difference of 40 ms is still a real difference. After the fix `nearest` scores 0.49, 0.48, 0.48, 0.46 on S1 to S4 (before: 0.48, 0.71, 0.51, 0.31; 10 seeds each). Editing `agents.py` changes the agents-code hash, so the whole first battery was re-recorded as `battery-main-10-fixed`; the biased records stay under `battery-main-10` for comparison (do not mix the two tags in one selection).

## One actor default: rate utility within 15 s (PI)

**Evidence (battery `battery-main-10-fixed`, 10 seeds, S1-S4, oracle and learner, windows 6, 15 and 30 s):** the `rate` utility (expected reward remaining over the seconds to harvest it) was at least as good as `value` (expected reward remaining, ignoring distance) in all 24 comparisons. Best case for `value` was the tightest window: oracle 360 / 512 / 693 / 1108 against `rate` 400 / 571 / 818 / 1280 on S1-S4, and learner 291 / 377 / 524 / 997 against 323 / 431 / 598 / 1102 (10 to 15% lower). With 15 s or more, `value` walks across the map for the best-looking bush and falls below the blind `nearest` (learner 155 against 270 on S1 at 15 s, 88 at 30 s). The window hardly mattered to `rate` (identical for the learner at 6, 15 and 30 s; the oracle lost 1 to 2% at 6 s). Time has to enter the policy, and the ratio does it without a tuned threshold. The Interlude score does not depend on the utility (a pair's travel times are tied), so this is a reward question only.

**Decision:** the standard actor is `UtilityActor()` = `rate`, `max_walk_time` 15 s (ring 5 of bushes, in the middle of what was tested), and the window is no longer a factor. Defaults changed in `agents.py`: `UtilityActor`, `GreedyAgent` and `DeltaRuleAgent` default to rate and 15 s (they were value and no window, a trap); `NearestAgent` passes `max_walk_time=None` explicitly so the floor and its hash are unchanged; the registry gains `oracle` (`GreedyAgent()`) and `learner` (`DeltaRuleAgent()`). The main battery population shrinks from 24 to 14 agents (the 12-agent window x utility grid and the value learner are gone; the other parameters, cone against whole map, and choice noise stay), named `oracle`, `learner`, `oracle_cone`, `learner_fullmap`, `learner_alpha*`, `learner_len*`, `learner_joint`, `*_softmax*`.

**Kept, not removed:** the `value` utility and `max_walk_time` options stay in the code (they are used by the old registry entries and are documented negative controls), because a value-only agent with a tight window is a plausible model of participants who ignore distance, which human data may need to test. Removing them (about 60 lines, two parameters, eight tests, every agent hash) is deferred until the human data are in and the exploring actors are designed (a window might matter to an agent choosing among bushes it has not seen). An untried point: a window below 6 s or around 8 to 10 s could bring `value` closer to `rate`; a 50-seed check on the oracle would settle it if that matters.

**Records:** the earlier 24-agent battery stays in the database under the tags `battery-main-10` (before the Interlude tie rule) and `battery-main-10-fixed`; agents whose spec did not change (rate, 15 s) are the same agents under the new names, so a re-run only recomputes because the agents-code hash moved.

**Update (PI): the view cone is the default observer, and the parameter sweeps wait.** The knowledge check in the same battery (oracle and learner, cone against whole map) showed the cone as good as the whole map: oracle 400 / 571 / 818 / 1280 against 403 / 568 / 798 / 1261 on S1-S4, learner within noise (323 / 431 / 598 / 1102 against 330 / 440 / 557 / 1129). The default view cone has no distance limit, so what the agent can see trades off against how far it is willing to walk (the 15 s window) rather than being a separate constraint. All standard agents therefore see through the cone: `NearestAgent` and `GreedyAgent` take `whole_map=False` (the map comes from the sensor, `FullMemory`); `whole_map=True` keeps the full-information variant, and the registry's `greedy_*` entries and the planners remain full-information benchmarks. The standard `nearest` is now the cone version (a new spec hash; the old full-information `nearest` stays in the database under its own hash). The learning-rate, RBF-width, feature-form and choice-noise variants are not part of the main population: PI wants them investigated once the defaults are set, so they are separate populations (`learner-parameters`, `choice-noise`; `knowledge` keeps the cone-against-whole-map check). The main population is `nearest`, `oracle` and `learner` (3 agents), and each population is one figure group.

**The floor stays: cone `nearest` against whole-map `nearest` was noise (30 seeds).** In the 10-seed battery the cone-based `nearest` looked much stronger than the whole-map one on S3 and S4 (636 against 493, 1096 against 990), which would have meant the learner no longer beat the floor. With 30 seeds (0-29) the paired difference (cone minus whole map) is -1 +- 7 (S1), -12 +- 8 (S2), +22 +- 35 (S3) and +16 +- 28 (S4): seeds 0-9 happened to favor the cone (+144 and +107, per-seed sd about 190 and 155) and seeds 10-29 favored the whole map (-39, -29). The two agents choose different bushes (only 42% of the first ten visits coincide) but have the same statistics: visits, walk, turn and press time, hop length (about 20.5 units) and the true reward and moisture of the bushes visited are identical to within noise. So the standard floor is the cone `nearest` and nothing needs changing. A random-bush-within-15-s floor was also tried: it walks three times as far per hop (76 units) and scores 113 / 150 / 215 / 398 on S1-S4, so it measures whether moving efficiently matters, not whether value knowledge does; `nearest` is the right floor for "does learning pay" because it spends time as efficiently as the informed agents do.

**Consequence for the battery:** per-seed spread of total reward is large in S3 and S4 (sd 150 to 200 for `nearest`), so 10 seeds only resolve differences above about 100 reward; S3 and S4 need 50 to 100 seeds before the learner against `nearest` can be called. With 30 seeds the learner leads `nearest` by +44, +65, +9 and +68 on S1-S4 (335 / 421 / 592 / 1137 against 291 / 356 / 583 / 1069); `nearest` reaches 74% (S3) and 86% (S4) of the oracle (793 and 1243). In S3 the learner visits bushes of mean moisture 0.50 (as `nearest`) against 0.78 for the oracle even though its Interlude accuracy is 0.84: a lead for exploring actors and for the 15 s window in the terraced sessions (not yet checked: the learner's critic could be inspected).

## Figure colours: a colour-blind-safe glasbey palette, a linestyle per agent, at most 5 agents per figure (PI)

**Rejected: the dataviz palette and the library defaults.** Measured as the smallest perceptual distance (CAM02-UCS) between any two of the first
five colours under simulated deuteranopia, protanopia and tritanopia (severity 100, the worst case), the old `SERIES` and most library defaults
(seaborn `deep`, matplotlib `tab10`, Tableau 10, Plotly, ggplot2) have a pair that nearly merges (distances of 1 to 4 for some vision type).
Okabe-Ito and Tol bright are better (about 7 to 12) but looked samey to the PI. **Chosen:** `glasbey.create_palette(5, colorblind_safe=True,
cvd_type="deuteranomaly", cvd_severity=100, lightness_bounds=(30, 80), chroma_bounds=(30, 90), grid_size=48)`, extended to 8 with
`glasbey.extend_palette` so the first colours never change (worst pair about 14 for the five). A palette optimised purely for the worst pair
scored about 35 but was rejected on appearance (a scientific-visual choice, the PI's).

**Linestyle as a second channel.** Colour alone separates about five lines for colour-blind readers, so each agent also gets matplotlib's named
linestyles (solid, dashed, dash-dot, dotted, plus a dash-dot-dot); slots 6 to 8 have extra dash patterns. Seaborn's own dash cycle was rejected
(patterns too close to tell apart), as were plotly's long dashes (they break crowded lines into fragments).

**Limit.** `plots.MAX_DISTINCT = 5` warns above five agents per figure (the evidence for a cut-off is indirect: Conover's 5 to 8 colour-coding
ceiling and the category-count effects in Tseng et al. 2023; none is specific to line charts). The palette still holds 8, the hard error. The
`learner-parameters` and `choice-noise` populations have 7 agents and so warn; splitting them is left to the PI.

## Figure size and fonts follow evidence_integration (PI)

`plots.MODES` copies the sizes of the PI's evidence_integration project (`utils/plot_style.py`, `scripts/make_figures.py`): a paper figure is 6.5 in
wide (a letter page's `\textwidth`) with 9 pt text, a presentation figure 10.6 in wide with 15 pt text, so the same figure reads the same next to
that project's. Heights are foraging's own (`panel_height`, `extra_height`), since a 2 x 2 grid is not a single panel. **Not adopted:** SVG output
(foraging keeps PNG), `constrained_layout` (the title, subtitle, legend and footer are placed in inches from the font sizes and `tight_layout` fits
the panels between them; `suptitle` is not used because `tight_layout` reserves room for it), and its `font.size` defaults of the seaborn notebook
context (replaced by the mode's sizes).

## Learner parameter scans: learning rate, RBF width, number of centers (100 seeds, S1-S4, dirty tree, tags `scan-alpha`, `scan-length`, `scan-centers`)

One parameter at a time around the standard learner (alpha 0.5, RBF length 0.3, 8 centers, rate utility within 15 s, view cone); `nearest` and `oracle` are the floor and ceiling. Reward lead over `nearest` (paired mean, se about 3 to 13), Interlude accuracy at the end of the session in brackets, S1 / S2 / S3 / S4:
- **alpha** 0.1: +16 / +27 / +17 / +38; 0.3: +39 / +61 / +26 / +65; 0.5: +50 / +71 / +25 / +82; 0.8: +59 / +65 / +35 / +89. Reward rises with alpha (except S2, which peaks at 0.5; S3 differences are inside the noise), but **the Interlude accuracy and the learning-curve area hardly move above 0.3** (S1 area 0.62 / 0.64 / 0.63 / 0.63): the Interlude measures the ranking of values, and the reward needs their magnitudes, because the rate utility divides the value by time. Under-scaled values (small alpha, broad kernels) let travel time dominate, and the agent drifts toward `nearest`.
- **RBF length** 0.1: +47 / +106 / +59 / +75 (accuracy 0.84 / 0.88 / 0.81 / 0.90); 0.3: +50 / +71 / +25 / +82 (0.91 / 0.78 / 0.87 / 0.94); 0.5: +28 / +38 / +19 / +56; 0.7: +13 / +20 / +11 / +22 (accuracy 0.94 / 0.74 / 0.88 / 0.94). Narrow is best where the reward is a peak (S2) or steps (the S3 terraces), middling in S1 and S4, but narrow is slower to learn (S1 area 0.49 against 0.63; time to 0.8 accuracy 0.61 of the session against 0.29), and broad kernels reach the highest accuracy in S1 and S4 yet give the smallest reward lead. No single width is best in all four sessions.
- **Number of centers** 4 / 8 / 12 / 16: identical within noise (S1 +52 / +50 / +48 / +48, S2 +70 to +73, S3 +25, S4 +80 to +82). At length 0.3 the kernel is already smoother than even 4 centers, so the parameter does not matter there; it may matter for narrow kernels (length 0.1 is below the 8-center spacing of 0.14), untested.
- **S3 stays weak under every setting**: the best learner there (length 0.1) closes 0.26 of the nearest-to-oracle gap, the standard one 0.11. Learning parameters do not fix it, which points at exploration and the window, as suspected.
- Not scanned (PI): feature form, number of passes, choice noise. Follow-ups suggested: a joint scan of alpha {0.5, 0.8, 1.2} and length {0.1, 0.15, 0.2, 0.3}, with centers 8 against 16 at the narrow lengths; the number of centers can otherwise be fixed.

## What a score is for: leads and diagnostics, no normalised ratios (PI)

**Question asked:** if the plots already carry the floor and ceiling lines, does a scalar score tell us anything new, or help optimisation and reasoning about mechanisms? **Answer:** a normalised ratio does not. Dividing every agent's lead by one per-session constant never changes which agent or parameter wins within a session; it matters only when averaging across sessions, and then the choice of aggregator (mean, pooled, minimum) is a value judgment. The per-world version is unusable where the oracle barely beats `nearest` (in about 15% of S3 and S4 worlds the gap is under 50 reward points, sometimes negative, and the per-seed ratio ranges from -1.5 to +2.2), and the oracle is not an upper bound (it is the true-value critic under the standard actor, not an optimal policy). What did help was: (1) the paired lead over `nearest` with its standard error, which plots cannot show (S3: +25 +- 12 looks like a tie in two overlapping bands); (2) two measures per agent, which exposed that reward rises with alpha while Interlude accuracy is flat (ranking against magnitude); (3) diagnostics that say why.

**Decision:** `analysis.gap_closed` and the `gap` column of `battery.scores` are removed. The scores are the paired lead in reward points (per session, with the four-session vector and its minimum for robustness), its exact split into **quality** and **efficiency** (reward = fruits x reward per fruit, so lead = F_floor (q - q_floor) + (F - F_floor) q: better bush choice against more fruits taken), the final Interlude accuracy, and the speed of learning (area under the chance-corrected accuracy curve over normalised time, and time to 0.8 accuracy). Normalised ratios may come back only for two uses: placing a participant in their single world (lead divided by the session's expected oracle lead, a constant) and acceptance thresholds on task design.

**Policy changes and the references (kept for later):** `nearest` is today both the fixed floor and the blind version of the standard actor (with equal values the rate utility ranks by travel time). For a new policy pi (exploration bonus, other window, softmax) the matched references are pi with a constant critic and pi with true values, so a critic's contribution is separable from the policy's; scores must name their reference agents. In the Interlude an exploration bonus should be off (the critic is frozen, nothing can be learned there) while choice noise stays, and the oracle with the same choice rule is the accuracy ceiling. Value fidelity (the critic's values against the truth) and per-trial results were considered and not stored: the decomposition above needs only what the database holds.

## Why the S3 learner knows the ranking and still earns little: the online delta rule under-scales values (40 worlds, standard learner)

**Observation:** the standard learner has Interlude accuracy 0.87 on S3 but a reward lead of only +25 +- 12 (about 11% of the oracle's lead), and its quality gain (+30) is a tenth of the oracle's (+270).

**Not the sampling.** The learner's visited bushes are spread evenly over the four moisture levels (25 / 24 / 27 / 23% dry to wet; `nearest` 24 / 26 / 25 / 25%), while the oracle concentrates on the wet level (65%). So the critic is trained on all four plateaus; exploration of moisture values is not what is missing.

**It is the size of what the critic learned.** Predicted change in value over the attribute range (others at 0.5), true value in brackets: moisture +0.24 (2.70), colour +0.56 (1.35), shape +0.02 (0). The ranking is right, the magnitudes are 9% (moisture) and 41% (colour) of the truth. Interlude accuracy is invariant to a common scale on the values (0.88 on pairs with equal moisture, 0.84 on pairs more than 0.2 apart in moisture), but the actor is not: the rate utility divides value by seconds, so values compressed ten-fold are dominated by travel time and the agent behaves like `nearest` (same moisture shares as `nearest`). This is also why reward rose with alpha in the scan while accuracy did not.

**The data are enough; the learning rule is the limit.** A batch ridge fit of the same features on the same bushes (about 25 in S3) recovers moisture +1.60 and colour +1.05 (S1: colour 2.10 against the online 0.86 and the true 2.70; S4: moisture 0.92 / colour 2.14 against the online 0.12 / 1.22, true 1.35 / 2.70). One pass of unit-norm LMS on spatially ordered samples under-fits by a factor of 2 to 10, worst for moisture (regional, so consecutive samples are correlated and overlapping kernels interfere).

**Consequence:** improving the critic comes first (passes over the experience per update, a batch ridge or Bayesian linear critic, per-attribute feature scaling), before changing the task or the exploration. Whether exploitation of the wet terraces is then limited by the 15 s window or by exploration is open (the oracle reaches the wet level under the same window and cone). Interlude accuracy alone hides calibration: a calibration slope (critic values against true values on the Interlude's bushes: 1 calibrated, 0 uninformative) would show it directly; it is not stored (needs a schema change and a re-run), which is now worth reconsidering.

**Test of "the terraces limit learning": S3 with the terracing removed (100 seeds for rewards, 40 worlds for critic slopes; tags `s3-continuous`, `s3-continuous-fine`; overrides only, no assets changed).** `moisture_terrace_levels=0` keeps the S3 reward function, elevation scale (20) and the long wavelength of its moisture field but makes the values continuous; the second variant also uses the S1/S2 noise frequency (`terrain_noise_frequency` 2.0, wavelength about 50 units). Paired reward lead over `nearest` (quality part), final Interlude accuracy, and the learner's moisture slope as a share of the true change over the range (batch ridge on the same data in brackets):

| | oracle lead | learner lead | learner accuracy | learner moisture slope |
|---|---|---|---|---|
| terraced (S3) | +231 (+270 quality) | +25 +- 12 | 0.87 | 9% (59%) |
| terracing off | +130 | +13 +- 7 | 0.91 | 2% (48%) |
| terracing off, fine field | +83 | +25 +- 4 | 0.91 | 15% (59%) |

- **The hypothesis is not supported:** removing the terraces does not improve the online learner's moisture learning (2% in the coarse continuous field, 15% in the fine one, against 9% terraced), and its reward lead does not grow (+13, +25 against +25). Colour is learned at 42 to 44% in all three. The batch ridge recovers 48 to 59% of moisture and 77 to 80% of colour from the same bushes in every variant, so the data are not the limit; the one-pass delta rule under-scales in all of them.
- **What the terraces do change is the headroom.** The oracle's lead falls from +231 (terraced) to +130 (continuous, coarse) to +83 (continuous, fine): large uniform wet plateaus are what make S3 rich, and reaching them is the job. The learner closes about 10% of the oracle's lead in the two coarse fields and about 30% (25 of 83) in the fine one, like S1 and S4: where good bushes are near, its under-scaled values cost less. So the coarse moisture field is hard for the learner because the reward is in migrating across the map, not because it sees four levels.
- In the continuous coarse field the learner's visited moisture is narrow (middle quartiles 47% / 44%, sd 0.11), against an even spread over the four terraces (sd 0.19): terraces actually give the critic more moisture variation to learn from.
- **Suggested next test (not run):** a `gain` on the critic's learned deviation from its baseline (value = baseline + gain x w.phi). If the reward lead rises with the gain while the ranking is unchanged, calibration is the bottleneck, which would show it causally without changing how the critic learns.

## Gain scan: calibration is a bottleneck in S3, but the best gain differs by session (100 seeds, tag `scan-gain`)

`DeltaRuleCritic(gain=g)` reads out value = baseline + g x (learned deviation); learning is unchanged (same error, same weights for the same data; a test checks this and that the ranking of bushes is unchanged). Reward lead over `nearest` (quality part, efficiency part), S1 / S2 / S3 / S4; final Interlude accuracy is flat in g (0.91 to 0.86, 0.78 to 0.74, 0.87 to 0.85, 0.94 to 0.93; the small drift is because a different gain visits different bushes):

| gain | S1 | S2 | S3 | S4 | mean | min |
|---|---|---|---|---|---|---|
| 1 | +50 (+57, -7) | +71 (+88, -17) | +25 (+30, -5) | +82 (+104, -22) | 57 | 25 |
| 2 | +64 (+84, -20) | +62 (+107, -44) | +70 (+94, -24) | +102 (+160, -58) | 75 | 62 |
| 4 | +62 (+106, -45) | -0.5 (+107, -107) | +97 (+159, -62) | +90 (+229, -139) | 62 | -0.5 |
| 8 | +44 (+120, -76) | -48 (+103, -151) | +128 (+222, -93) | +64 (+299, -235) | 47 | -48 |
| oracle | +110 | +209 | +231 | +178 | | |

- **S3 confirms the calibration hypothesis causally:** with the same learning, the lead rises monotonically with the gain (25, 70, 97, 128; quality 30 to 222 against the oracle's 270) and has not saturated at 8. Under-scaled values, not wrong ones, were what held the S3 learner back.
- **More gain is not better everywhere:** the quality part grows with the gain in S1, S3 and S4 (and the oracle's quality is +176 / +319 / +270 / +300), but the efficiency part falls faster (the agent walks farther for better-looking bushes and takes fewer fruits). The best gain is about 2 for S1 and S4, at least 8 for S3, and 1 for S2, where the quality stops improving at 107 (the learned peak is mis-shaped, accuracy 0.78) while the walking cost keeps growing: amplified errors. By mean lead across sessions gain 2 is best (75 against 57) and also has the best minimum (62 against 25).
- **Interpretation:** a gain above 1 acts as a smaller weight on travel time against reward in the rate utility (a willingness-to-walk parameter), which the oracle gets right for free because its values are calibrated; the learner needs the right scale per session. The principled fix is better scale learning (not applied: PI does not want the learner changed drastically yet); the gain is a diagnostic and a possible actor-side parameter.

**Window test: 15 s against 60 s for the learner (gain 1, 100 seeds, tag `scan-window`).** The results are identical to the digit on S1, S3 and S4 (lead +49.6, +25.3, +81.7 for both windows): the window never binds, because the learner's compressed values never make a bush more than 15 s away worth its travel time under the rate utility (the same finding as the 6/15/30 s grid before). Only S2 differs: +71 +- 6 at 15 s against +56 +- 7 at 60 s (quality equal, efficiency -16 against -30: the mis-shaped peaked function pulls it to far bushes). So at gain 1 a larger window can only hurt. The window may start to matter once values are calibrated (gain above 1), where over-travel is the failure (S4 gain 8: quality +299, efficiency -235); a window by gain 2 x 2 is the follow-up.

**Scratch check (not recorded; 60 worlds per session, session only): a fixed baseline instead of the running mean (PI's hypothesis).** The current `NeutralPrior` is a constant (1.0) only until the first bush is harvested and then the running mean of the bush means, so the learned weights fit residuals around a moving level. With a fixed baseline for ever (a scratch `ConstantPrior`), reward lead over `nearest` S1 / S2 / S3 / S4: running mean +51 / +71 / +25 / +80; constant 0: +20 / +66 / +22 / +19; constant 1: +67 / +93 / +67 / +103; constant 2: +66 / +79 / +59 / +109 (se 4 to 23). So a fixed baseline of 1 or 2 beats the running mean in all four sessions, while 0 is no better. The attribute slopes it learns hardly change (S3 moisture 0.25 -> 0.46 to 0.50 of a true 2.70; colour 0.57 -> 0.65 of 1.35), so this is not the gain mechanism: the level of the values lives in the weights, and unvisited regions revert to the fixed baseline, so bushes resembling rewarded experience are preferred over novel ones. Next: a recorded scan of constant baselines, and their interaction with the gain.

## Baseline scan: a fixed baseline beats the running mean (100 seeds, tag `scan-prior`)

`ConstantPrior(level)` (new component) keeps the baseline fixed for ever; the standard `NeutralPrior` follows the running mean of the bush means. Reward lead over `nearest` S1 / S2 / S3 / S4 (mean over sessions; final Interlude accuracy and learning-curve area in brackets for S3):
- running mean (standard): +50 / +71 / +25 / +82 (57; S3 acc 0.87, area 0.59)
- constant 0.1: +53 / +92 / +64 / +92 (75; S3 acc 0.80, area 0.39, t80 0.98)
- constant 1: +65 / +86 / +63 / +89 (76; S3 acc 0.86, area 0.52)
- constant 2: +62 / +75 / +64 / +94 (74; S3 acc 0.90, area 0.64, t80 0.29)
- A fixed baseline raises the reward lead in every session (S3 from +25 to about +64) and the minimum across sessions from 25 to 53 to 63. Constants 1 and 2 also learn faster (S1 area 0.67 / 0.69 against 0.63; S2 0.53 / 0.47 against 0.44; S3 0.52 / 0.64 against 0.59) while 0.1 gets its reward at the price of knowledge (slower, lower accuracy: S3 0.80, area 0.39), so about 1 to 2 looks best on both measures. The learned attribute slopes grow little (the scratch check), so the mechanism is the level living in the weights and unvisited regions reverting to the fixed baseline, not a larger scale of deviations.
- The earlier scratch check had a constant 0 doing badly (S1 +20, S4 +19); 0.1 does not. With a baseline of exactly 0 every unseen bush has utility 0, the rate utility ties, and the actor picks by bush id instead of by travel time; a small positive baseline keeps the nearest-first ordering. (I had predicted 0.1 would behave like 0: wrong.)
- S3 remains the weak session (+64 against the oracle's +231, a 28% share).
- Not applied: the default prior is unchanged (`NeutralPrior`); candidates are `ConstantPrior(1)` or `(2)`, possibly with a gain of about 2, not yet crossed.

## The learner's default prior is a fixed 0.1 (PI), and a 10-seed check of the new default

**Decision (PI):** `DeltaRuleCritic` defaults to `ConstantPrior(0.1)` instead of the running-mean `NeutralPrior` (which stays available). Reason: the scan showed any fixed baseline raises the reward lead (S3 from +25 to about +64), but larger constants (1, 2) act as an optimism bonus, i.e. a curiosity or exploration mechanism, which is to be reserved for the actor; 0.1 is small and positive, so the rate utility still ranks unseen bushes by travel time (a baseline of exactly 0 would tie them). The cost is slower, slightly less accurate Interlude learning (S3 accuracy 0.80, area 0.39 in the scan). The standard `learner` is now this agent (new spec hash); the old running-mean learner is `learner_meanprior` in the `scan-prior` population, and records made before the change stay in the database under the old spec.

**Minimal check (3 agents, seeds 0-9, tags `min-std`, `min-long`; noisy by design):** on the standard durations the new learner leads `nearest` by +40 +- 16 / +78 +- 14 / -6 +- 43 / +71 +- 39 (S1-S4), final accuracy 0.88 / 0.82 / 0.83 / 0.88, learning-curve area 0.50 / 0.53 / 0.41 / 0.54. On the same ten seeds the earlier running-mean learner scored 323 / 431 / 598 / 1102 and the new one 324 / 444 / 630 / 1168 (+1, +13, +32, +66), the direction of the 100-seed scan, and accuracy and area match the scan's 0.1 learner. Seeds 0-9 are a hard subset for the learner in S3 (`nearest` scores 636 on them against 567 over 100 seeds), so S3 needs 50 to 100 seeds before it can be called. With the longer sessions (S1 120, S2 120, S3 180, S4 180) the lead on the same seeds is +74 +- 21 (S1; +40 at 90 s), +78 (S2, identical to the 120 s run, as it must be), +6 +- 65 (S3; +33 quality gain against +6 at 120 s) and +76 +- 34 (S4; oracle +204). The S3 patch-size test and the 100-seed long-session run were cancelled as too long; the partial `long-main/S1` records stay in the database.

## S3 patch size: smaller terraces make S3 learnable (100 seeds, S3 at 180 s, terraces kept, new default learner; tags `s3patch-freq0.6/1/1.5/2`)

`terrain_noise_frequency` set the patch size of the moisture field (0.6 is the S3 asset: wavelength about 165 units); the terraces (4 levels), the reward function and the value distribution were unchanged (top-decile excess 1.61 to 1.63 and the value sd are the same at every frequency; overrides only, no asset changed). What the frequency changed in the world (20 worlds): the correlation of bush values 30 to 60 units apart fell from +0.53 (0.6) to +0.25 (1.0), -0.01 (1.5) and -0.09 (2.0); at 0 to 30 units from +0.72 to +0.62, +0.42, +0.26; the local spread over the global spread rose from 0.86 to 0.95, 0.98, 0.99.

Reward lead over `nearest` (868 / 849 / 851 / 860 in the four worlds), 0.6 / 1.0 / 1.5 / 2.0:
- oracle +312 +- 21 / +291 +- 14 / +271 +- 10 / +223 +- 8 (quality 374 / 368 / 368 / 345, efficiency -62 / -77 / -97 / -122)
- learner +98 +- 22 / +132 +- 16 / +150 +- 12 / +145 +- 10 (quality 117 / 158 / 181 / 182), a share of the oracle's lead of 0.31 / 0.45 / 0.55 / 0.65
- learner final Interlude accuracy 0.85 / 0.86 / 0.84 / 0.85 and learning-curve area 0.48 / 0.48 / 0.46 / 0.47: what it knows does not change with the patch size; what changes is how much of it pays.

**Reading:** the long, uniform patches were what kept the learner from using what it knew: with persistent moisture the good bushes are a migration away and the successive samples it takes are nearly the same level; with smaller patches (correlation gone beyond about 40 units) the best bushes are within a hop or two and the learner's quality gain rises from +117 to +182 against the oracle's +345 to +374. The oracle's lead falls (312 to 223) because its efficiency cost grows (it walks farther for the best bushes) while its quality is stable. The learner's gain levels off between 1.5 and 2.0, so about 1.5 (wavelength about 66 units) is enough; at 1.5 the share (0.55) is in line with S1 and S4 and the oracle still leads by +271 (32% of `nearest`'s 851). The longer session alone (0.6 at 180 s: share 0.31, learner +98) gave about the same share as 120 s (0.28), growing the lead in proportion to time.

**Not applied:** S3's asset is unchanged. A smaller patch size changes the look of the terraces (ground colour and height tiers) that participants see, which is a visual-channel change to be judged in the Editor and decided by the PI; if adopted, the world file must be regenerated (`scripts/world.py S3 --unity`) and S3's Interlude regenerated. S4 uses the same terrace parameters (moisture weight 1.5) and has not been tested.

**S3 set to frequency 2 and elevation 12 for a playtest (PI, 2026-10-26; temporary):** `terrainNoiseFrequency` 0.6 to 2 and `terrainMaxElevation` 20 to 12 on S3 and S3_Interlude (Unity CLI, then the S3 `.world` and `.interlude.json` regenerated; 372 tests pass, including the freshness checks). The elevation was lowered because at frequency 2 and elevation 20 the valley's median slope was 12.4 deg (99th percentile 63 deg) and 82% of the bushes within 150 units were hidden from the start by terrain (0.6 and 20: 4.6 deg, 37 deg, 41%). At 2 and 12 it is 7.7 deg, 50 deg and 68%: better, still steeper and more occluded than the design, and steeper than S1 and S2 (continuous moisture, no terrace ramps). The simulator's cone ignores terrain, so agent results do not include occlusion; the agent results for frequency 2 (S3 patch-size entry) used elevation 20 and are unaffected by the elevation (the simulator did not use it outside the Interlude placement checks; the opt-in `OccludedConePercept`, built later, reads it for line of sight, and the default cone still ignores it). A lower elevation (about 8) would bring the slopes nearer the design if the playtest finds them too steep.

**Adopted (PI, 2026-10-26): S3 and S4 use terrain noise frequency 2 and elevation 12.** After a playtest the PI judged S3 at frequency 2 and elevation 12 good (smaller terraces and the steeper terrain) and made it the default, with the same change for S4. `terrainNoiseFrequency` 0.6 to 2 and `terrainMaxElevation` 20 to 12 on S3, S3_Interlude, S4 and S4_Interlude (Unity CLI); the `S3_seed3.world`, `S4_seed4.world` and both Interlude files regenerated; 372 tests pass (the freshness checks included). The earlier "temporary playtest" status is gone. S4's world: 701 bushes, 175 to 179 per moisture level, valley slope median 7.6 deg (99th percentile 48.8), 65% of the bushes within 150 units hidden from the start. **Consequences:** every S3 and S4 result in the database made before this change was computed on the old terrain (frequency 0.6, elevation 20) and has a different environment hash, so new battery runs are new records and are not comparable with the old S3 and S4 numbers; the S3 patch-size test covers the sim effect at 0.6 to 2 (elevation does not matter to the simulator), but the effect on S4 and the whole battery on the new terrain have not been recorded yet. The simulator's view cone ignores terrain occlusion, which at this setting hides about two thirds of the nearby bushes from a person: an occlusion percept (the repo's `visibility.py` reconstructs what humans saw) is the way to model it (built since as the opt-in `OccludedConePercept`).

**Bush occlusion in `scripts/visibility.py` (PI request; terrain occlusion was already there):** `visible_bushes(..., bush_occlusion=True)` (default; `--no-bush-occlusion` on the command line) now also hides a canopy sample point when the line from the eye to it passes through another bush's canopy: an opaque half-ellipsoid centred on the ground at the bush's (x, z) with horizontal radius the canopy radius and vertical radius half the canopy height (the shape `Tree.ApplyAttributes` builds and the module already samples), the part of the ray inside it counting only above the ground. Only bushes that exist at that moment can hide another (in an Interlude only the trial's pair); the target's own canopy is skipped; a bush behind the target hides nothing. `visible_fraction` therefore drops for partly hidden bushes. Not modelled: translucent canopy edges, fruit, and a camera inside a canopy. Not hashed (`visibility.py` is not an engine file), so no result records are affected. Effect on a simulated person (25 random spots and headings in the S3 world of seed 3, bushes within 150 units in the 107 deg view): about 45 in the cone; terrain hides 10.8 (24%) on the old terrain (frequency 0.6, elevation 20) and 15.9 (35%) on the current one (frequency 2, elevation 12); other bushes hide a further 1.8 and 1.6 (about 4%); so about 33 and 28 are seen. The earlier "68% hidden from the start" counted all bushes within 150 units in every direction from the start point only, not the ones in view, and overstates the typical loss. The simulator's own view cone (`perception.py`) still ignores terrain and bushes; an occlusion percept built on this geometry was the next step (built since as `OccludedConePercept`, see below).


**`OccludedConePercept` in `scripts/perception.py` (PI request; opt-in, not the default):** the view cone plus line-of-sight occlusion with the geometry of `visibility.py`: a bush is seen when at least one of the 11 canopy sample points facing the eye lies in the horizontal cone and the line from the eye (session `eye_height` above the terrain's elevation grid) clears the terrain and every other bush's opaque half-ellipsoid canopy. The shared geometry (`SURFACE_RINGS`, `unit_directions`, `canopy_height_of`, `sample_grid`, `hidden_by_terrain`, `hidden_by_bushes`) moved from `visibility.py` into `perception.py` so that the simulator's observer and the reconstruction of what a person saw cannot drift apart; `visibility.py` imports it. Pass it as `percept=` (it is part of the environment hash through its spec); `ConePercept` stays the default observer, so the standard battery and every earlier record are unchanged. Not modelled: pitch (no vertical field of view), translucent edges, fruit. **Cost:** about 27 ms per look against 0.04 ms for the cone, because the 107 deg cone with no distance limit holds about 200 bushes (of which about 78 are seen on the S3 terrain), so occlusion runs are roughly an order of magnitude slower. `canopy_height_range` is read from the session parameters but is not in `fingerprint.SIM_FIELDS` (adding it would change every environment hash); an occluded run records the percept's spec but not that range, so a change to the range alone would not be seen by the hash (the default cone does not read it). Tests: `test_sim.py` (open ground equals the cone; a big bush hides a small one behind but not beside it; a ridge hides; never more than the cone in the real S3 world).

**Interlude elevation floor, `interludeMinElevationDifference` (PI, 2026-10-26; S3 and S4 at 3 units):** in the random mode a trial's two bushes must stand on ground that differs in elevation by at least this many world units, so the terrain difference is noticeable. A SessionConfig field (default 0 = off), read only by `scripts/interlude.py` (a placement mask `apart` on the pool's nominal moisture difference times `terrainMaxElevation`, then a check on the final bush positions, which shift with the canopy radii); the game plays the generated file and needs no code. **Why:** sampled on the new terrain, two bushes at the Interlude's 28-unit separation differ by 3.8 elevation units on average and 15% almost not at all, and that does not depend on the bush distance (the terrain is already independent at 28 units; the mean moisture difference is 0.29 at 25 units and about 0.34 from 60 to 200). **Why 3 and all pairs:** 3 is about one terrace step (0.27 moisture = 3.2 units) and discards 43% of random placements (2 units: 30%, 4 units: 56%, nearly the same for any terrain variant tried); applying it to every pair, not only pairs on terraces, was the PI's choice, and S1/S2 are left alone because moisture does not affect their reward. **Rejected here:** longer walks or wider bush spacing (no effect); regional terracing (a smooth mask blending the continuous field into terraces) as the way to get larger differences: in a prototype (10 seeds, S3 settings) it changed neither the pair differences (0.325 to 0.328 for all variants, the same as the terraced field) nor the moisture spread, only the look and the steepness (median slope 11 to 13 degrees against 9 for the terraced field, which would need a lower elevation to keep the playtested feel); kept as an open option, together with uneven terrace levels. **Consequences:** every Interlude result for S3 and S4 is on a different pair distribution (the Interlude hash changes through `SIM_FIELDS`, which gained `interlude_min_elevation_difference`, so every environment hash changes, and the engine hash changes with `interlude.py`): S3/S4 Interlude baselines have to be recorded again, and the previous battery's S3/S4 accuracy is not comparable. The 100-seed `newterrain-long-100` results are of the unconstrained pairs.

**Range tolerance in `costs.approach` and `Memory.reward_rate` (PI request, first two engine prerequisites of the exploration policies):** `approach` now treats a bush within `RANGE_TOL` (1e-6 world units) of its harvest range as in range. After the engine walked an agent to `reach` from the bush the leftover `dist - reach` was a rounding error of about 1e-13 in 47% of walks (measured on 20,000 random placements), so a second visit to a bush the agent had left early was charged a walk's turn and W press the game would not charge; no actor left a bush early before, now peek-and-leave will. Pinned by two `motor_costs` tests (the arithmetic on random positions, and an engine run that returns to a bush left after one fruit and must pay only the Space press), both of which fail without the fix. `Memory.reward_rate(elapsed)` (and `View.average_rate()`) give the average reward per second so far from the rewards the memory holds (a forgetful memory would report the rate it remembers), for rules that compare a bush with the average rate; it needs the clock, so the actor passes the time elapsed. Hash consequences: `costs.py` and `agents.py` moved, so every record made before is stale for lookup (the simulated trajectories themselves change only where a walk used to end a rounding error short; agents that never revisit a bush are unaffected in behaviour). The known-and-deferred item about this in `docs/REVIEW_POLICY.md` is now fixed and can be removed.

**Decided and implemented (PI, 2026-10-26):** the Interlude evaluation of the new exploration actors is greedy: `choose_between` takes the argmax of the critic's value (random ties), whatever the actor's choice rule, so exploration noise never enters the Interlude and there is no history dependence to resimulate. This changes the Interlude accuracy of the existing Softmax agents (the `choice-noise` population), whose earlier records then differ. Curiosity bonuses are in units of a fraction of the running mean value. Area-restricted search is the adaptive-radius variant in attribute space, kept simple (a plain radius that grows with misses), because a richer rule would amount to a hand-built uncertainty-reduction mechanism.

**Exploration policies, step 4: the GP critic and the UCB, Thompson and hybrid actors (PI request; `scripts/agents.py`):** `GPCritic` is Gaussian-process regression of a bush's mean reward per fruit on its attributes, with a swappable `Kernel` (`RBFKernel(length_scale, additive)`: additive, the default, is the mean of one 1-D Gaussian kernel per attribute, matching the additive reward function and the delta-rule learner's features; joint is Wu et al.'s isotropic 3-D kernel). Each bush is one observation (the mean of its fruits, noise variance sigma^2 / n). **Everything the prior and noise need is estimated from the memory (PI):** prior mean = mean of the bush means so far (`prior_mean` fixes it), prior sd = the spread of the bush means beyond what the noise explains (at least `min_std` 0.1; needs three bushes), sigma^2 = the within-bush variance pooled over bushes with two or more fruits (at least 1e-4, Wu's value); before they can be estimated it falls back to `initial_mean` 0.1 (the delta-rule learner's baseline), `initial_std` 1.0 and `initial_noise_std` 0.3 (placeholders that do not read the task's `rewardStd`). Its uncertainty is the posterior sd of the function, not of a fruit, so the per-fruit reward noise is not mistaken for something to explore. Actors (all rate utility within the 15 s window; the Interlude is greedy, see above): `PosteriorActor(beta 0.5, temperature 0.05)` (UCB; registry `gp_ucb`) = rate of `mean + beta * sd`, chosen by a `RelativeSoftmax` (utilities divided by the best one, so the temperature means the same in every session; Wu et al.'s softmax on raw values is not scale-free); `PosteriorActor(beta 0, sample=True)` (Thompson sampling; `gp_thompson`) = **one posterior draw of the whole value function per decision** (a joint draw over the bushes in the walking window, via an eigen-decomposition of the posterior covariance, so neighbouring bushes move together), hard max; `PosteriorActor(beta 0.5, sample=True)` (the hybrid; `gp_hybrid`) = that draw plus `beta * sd`, hard max (Gershman 2018). Registry: `gp_mean` (the GP critic with the standard actor: no exploration), `gp_ucb`, `gp_thompson`, `gp_hybrid`; battery population `explore-posterior` (with the delta-rule learner, the floor and the oracle); the three posterior actors were first three classes and are one `PosteriorActor` since the review (Thompson sampling is exactly the hybrid at beta 0). Horizon-dependent temperature, the curiosity bonus, peek-and-leave and area-restricted search came next (below). **First impression (6 seeds, not recorded, standard 120 s S1 and 180 s S3 durations; reward lead over `nearest`):** the GP critic with no exploration beats the delta-rule learner (S1 +149 vs +84, S3 +208 vs +178), and each exploration actor earns less than that (S1 +100 to +104, S3 +115 to +171), as expected for a bonus whose payoff is learning, which the reward lead does not show: the Interlude accuracy and its learning curve are where they have to be judged. Hash consequence: `agents.py` moved again, so records of every agent made before are stale for lookup.

**Exploration policies, steps 1 to 3 and 5: softmax with a horizon, curiosity, peek-and-leave, area-restricted search (PI request; `scripts/agents.py`, all with the standard delta-rule critic so only the policy differs):** (1) `SoftmaxActor(temperature 0.05, horizon)`: the rate actor with a `RelativeSoftmax`; with `horizon` the temperature is `temperature * time left / session length` (floored at 1e-3), so choices are loose early and greedy at the end (Wilson et al. 2014); a horizon actor is `deadline_dependent`, and its checkpoints are within-session curves (below). (2) `CuriousActor(beta 0.3, kernel)`: a bonus `beta * m / sqrt(1 + n)` added to each bush's value before the rate utility, `m` the mean reward per fruit so far (`Memory.mean_reward`, so `beta` is a fraction of the running mean value) and `n` the sum of an `RBFKernel` between the bush and every harvested bush (attribute space only, no spatial novelty: PI decision). (3) The hedge is the same class with `peek_fruits` (the first version let the agent walk straight back to the bush it had left, because standing in its range it cost only a key press; the review found it and a bush left early is now excluded for the rest of the session, so every earlier peek result was of that loop) (default None = harvest to empty): after that many fruits it leaves a bush whose own rate (mean reward per fruit over the fruit time) is below `margin` times the average rate so far (`Memory.reward_rate`), the marginal-value rule; `beta=0` with `peek_fruits=2` is peek-and-leave alone. With 0.2 s per fruit against several seconds of walking, staying almost always beats the average rate, so the rule only releases the poorest bushes. (5) `AreaRestrictedActor(radius 0.5, growth 2)`: the adaptive-radius variant the PI chose: after each bush, a mean reward per fruit above the mean so far is a hit and anchors the search (restricts the next choices to bushes within `radius` of it in attribute space, Euclidean on [0, 1]^3); a miss multiplies the radius by `growth`; if no bush in the walking window is inside the radius the restriction is dropped for that choice. **Defaults were picked from a 16-seed scan (long durations, reward lead over `nearest`, not recorded), because first guesses were bad:** a softmax temperature of 0.1 (relative utilities) cost 50 to 100 points against the learner (S1 +21 against +73, S4 -19 against +79), 0.05 about 10 to 25, 0.02 almost nothing; a horizon softmax at 0.2 was worse still (S4 -109), at 0.05 to 0.1 roughly equal to the learner; area-restricted search at radius 0.3 with growth 1.5 was far worse than the learner (S3 -138, S4 -265, because it walks 108 s instead of 77 s: attribute neighbours are not spatial neighbours), at radius 0.5 with growth 2 still behind it on S3 and S4 (+76 against +152, +7 against +79), at 0.8 about level; the curiosity bonus at 0.1 to 1.0 left reward level with the learner on all four sessions (within +/-15), so whether it helps has to be judged in the Interlude, not in reward. These are first defaults to sweep, not results. Hash: `agents.py` moved again.

**Checkpoints of deadline-dependent agents are allowed (PI decision, 2026-10-26):** `run_episode(checkpoints=)` and `run_battery` no longer refuse an actor with `deadline_dependent = True` (the planners, the horizon softmax). A checkpoint is a deep copy of the agent at session time t, scored on the Interlude; for an agent that does not depend on the session's length that equals a shorter session, and for one that does it is the agent as it stood at time t of a session of the full length, which is the state a participant has at that moment and the only thing the Interlude at the end of a human session can be compared with. The curves of such agents therefore must not be read as "what a shorter session would have given" (run sessions of different lengths for that). Why it was safe to relax: the Interlude evaluation is greedy for every actor (above), so scoring a copy never replays exploration or depends on the history of the session. The refusal protected a claim, not a measurement, so the claim in the docs changed instead. No stored result changes meaning (these agents were refused before). `softmax_horizon` is in the `explore-noise` population. The flag stays, as documentation of which curves are within-session.

**Matched critics: what makes the GP better than the delta rule (PI request; 30 seeds, long battery, tags `r30b-critic-ladder`, `r30b-scan-matched-noise`, and `r30-scan-alpha` for the delta rule's learning rate):** the GP critic got three options that switch its estimates off (`prior_std`, `noise_std`, `weight_by_count=False`) and a `FeatureKernel` (`phi(x) . phi(x')` of the delta rule's own RBF features, which makes the GP exactly Bayesian linear regression on those features). `weight_by_count=False` treats every bush as the mean of a full bush's fruits (noise variance sigma^2 / fruit count); a first version gave every bush the full per-fruit variance, which also made the fit about ten times more regularised and confounded the rung (its results, tag `r30-critic-ladder`, are superseded). **Ladder (lead / final accuracy / learning-curve area, S1 to S4):** learner +77/0.90/0.60, +88/0.83/0.55, +156/0.86/0.49, +106/0.89/0.51; `gp_mean` +128/0.94/0.74, +159/0.97/0.73, +192/0.92/0.69, +162/0.98/0.81; fixing the reversion value at 0.1 (`gp_fixmean`), weighting every bush alike (`gp_equalw`) and fixing the prior spread 1.0 and noise sd 0.3 (`gp_fixhyper`) each changed nothing resolvable (equal weights are identical to fixed mean because nearly every bush is harvested to ten fruits); with the delta rule's features as the kernel (`gp_matched`) +130/0.93/0.74, +158/0.97/0.72, +201/0.88/0.66, +159/0.97/0.79. **Reading:** with the same features, the same 0.1 baseline, equal weights and fixed hyperparameters, the exact fit still beats the online delta rule by about +53, +70, +45 and +53 reward points and 0.14 to 0.28 in learning-curve area, and almost the whole lead gap between `gp_mean` and the learner is that update rule; representation (the Gaussian kernel against the feature kernel: S3 accuracy 0.93 against 0.88, the one visible difference), the reversion value, the count weighting and the estimated hyperparameters are second order. The matched GP's noise sd (0.1, 0.3, 1, 3): 0.1 is slightly more accurate than 0.3 (S1 0.96, S2 0.98, S3 0.90, S4 0.98) and 3 is clearly worse (S1 0.92, S2 0.89, S3 0.84), so stronger regularisation hurts monotonically; the delta rule behaves like an under-fitted version (its learning rate 0.1, 0.3, 0.5, 0.8 gives S1 lead +46, +74, +77, +92 and learning-curve area 0.46, 0.57, 0.60, 0.63, still rising at 0.8 and below the matched GP). **Not done (PI skipped it):** a replay or multi-pass delta rule, which would test whether the gap is convergence alone. Dirty-tree runs; the tree should be committed and the runs repeated on a clean tree before the numbers go into SCIENCE.md.

**Replay in the delta-rule critic: a swappable `Replay` component (PI request; during the session; 30 seeds, long battery, tag `r30c-scan-replay-*`):** `DeltaRuleCritic(replay=None)` takes a `Replay` policy that says which stored bushes to learn from again after each finished bush: `FullSweeps(epochs)` (extra passes over everything stored, in bush-id order, which the world shuffles), `SampledReplay(steps, seed)` (uniform with replacement from its own seeded stream, restarted each session) and `PrioritizedReplay(steps)` (the largest current errors first). A critic without replay has no `replay` entry in its spec, so the standard learner keeps its identity. Recency-weighted replay is not built: it needs the memory to record the order of visits. **Result (lead / final accuracy / learning-curve area, S1 to S4; learner +77/0.90/0.60, +88/0.83/0.55, +156/0.86/0.49, +106/0.89/0.51; `gp_matched` +130/0.93/0.74, +158/0.97/0.72, +201/0.88/0.66, +159/0.97/0.79):** with one extra pass +113/0.93/0.71, +131/0.93/0.64, +203/0.84/0.59, +155/0.93/0.71; five passes +126/0.92/0.72, +149/0.96/0.69, +191/0.86/0.63, +149/0.96/0.76; 100 passes +128/0.94/0.73, +149/0.98/0.74, +191/0.88/0.67, +160/0.98/0.79, level with `gp_matched` on all three. So the whole gap between the delta rule and the exact fit of the same features was convergence: one pass per bush underfits, and a few passes (5 to 20) are enough to close it; the fixed-step online rule with enough replay is the least-squares fit (tested: 400 sweeps reproduce the exact feature-kernel GP). Sampled replay (20 or 100 steps per bush) and prioritised replay (5 or 20) close most of the lead gap too (+117 to +127 on S1) but are a little less accurate than full sweeps on S2 (0.91 to 0.96 against 0.96 to 0.98). Consequences: replay amount is a natural free parameter for fitting people (a trial-by-trial learner between no replay and the exact fit), and the Bayesian GP is not needed to explain the gain; it remains the way to get uncertainty. Dirty-tree runs; repeat on a clean tree before SCIENCE.md.

**The delta rule's read-out `gain` was removed, and the replay delta rule matches the exact GP (PI decisions; 100 seeds, long battery, tag `r100-two`):** `DeltaRuleCritic(gain=)` is gone (parameter, spec entry, read-out, its test and the `scan-gain` population; the standard learner's spec hash changes, so earlier delta-rule records are stale). The head-to-head the PI asked for, with the representation as similar as possible: `replay_len0_5` (delta rule, additive RBF features of width 0.5 with 8 centres, baseline 0.1, alpha 0.5, 100 replay sweeps after each finished bush) against `gp_matched_len0_5` (a GP on the same features through `FeatureKernel`, prior mean 0.1, equal weights, prior sd 1.0, noise sd 0.1; the noise sd came from the earlier four-value scan on seeds 0 to 29, which these seeds include). Paired differences (replay minus GP), per session S1 to S4: reward +0.9 ± 2.3, -4.1 ± 3.9, +3.3 ± 3.0, +7.3 ± 3.7; final accuracy +0.000 ± 0.004, -0.006 ± 0.005, -0.002 ± 0.005, -0.009 ± 0.002; learning-curve area +0.009 ± 0.004, -0.024 ± 0.007, -0.013 ± 0.006, -0.002 ± 0.003. Mean reward 511/510, 484/488, 1076/1073, 1443/1435 and final accuracy 0.955/0.955, 0.943/0.949, 0.898/0.900, 0.961/0.970. So the two are equivalent for reward and for final accuracy to within about one percent, and the replay delta rule is slightly slower early on S2 and S3 (accuracy 0.81 against 0.84 at 35% of S2). The critic gap between the delta rule and the GP was therefore convergence, as the replay scan at width 0.3 had indicated. Dirty-tree run: repeat on a clean tree before SCIENCE.md.

---

## Online data collection: one row-oriented schema, uploaded to Supabase (PI decisions, 2026-10-29)

Build plan and protocol: `docs/ONLINE_DATA_PLAN.md`. This entry holds the reasons and the rejected alternatives. It supersedes "Data output: `ForagingData/`..." above and the "paths and columns are fixed" rule in CLAUDE.md for the *first* real format: no dev or participant data exists, so the log is redesigned once now, for the server, and is frozen after the first participant.

**Decision.**
- **The online database is the default; local files are a developer mirror.** Each log stream is a table (`runs`, `sessions`, `events`, `trajectory`, `interlude_plan`, `interlude_trials`, `pid_registry`). The Editor and standalone builds can write the same rows to local files so offline work and replay keep working; online builds POST them to a separate Supabase project (not the `evidence_integration` one: RLS, quotas and deletes stay apart). Access is deny-all RLS plus Edge Functions with a per-run token, as in `evidence_integration`.
- **Mid-session resume, not session-boundary resume.** A participant who reloads or drops out continues the session from the last uploaded state. The server returns that state computed from the rows: session index and clock `t`, last pose, fruits taken per bush (count of `fruit` events per `tree_id`; the k-th fruit pays the pre-drawn `fruit_reward[bush][k]`), running score, Interlude progress and its planned order. Nothing else is needed because the world is a pure function of its seed, there is no regrowth and the sun runs on session time. A harvest bout in progress restarts and is marked in the `resume` event; the real-time gap is logged. Resume limits (maximum gap, number of resumes) are deferred; the data to apply them later is in the events.
- **The Interlude's full shuffled trial order is logged at the start** (`interlude_plan`), for resume and for tracking. (It was an unseeded `System.Random`, so the order of trials not yet shown was never recorded.)
- **Reward-relevant events upload within about a second; trajectory every 5 s.** A reload then never re-offers a fruit the participant took; the pose is at most 5 s stale and the gap is logged.
- **The game pauses until the database has acknowledged the data.** The client keeps a queue of unacknowledged rows; when a send fails or an acknowledgement is overdue (after a short grace window, a `SessionConfig` field) it stops the session clock behind an overlay like the instruction screens and resumes when the backlog is acknowledged. Complete data over uninterrupted play.
- **Trajectory is kept per frame, quantized, delta-coded, compressed and stored as chunk blobs.** One row per chunk (`run_id, session, first_seq, n_frames, t_start, t_end, data bytea`); `seq` is the frame index within the session, which makes uploads idempotent and gives resume its `t_end`. Quantization: **time 1 microsecond** (not the 1 ms first proposed: see below), x and z 0.01 world units (the harvest range gap is 7), yaw and pitch 0.02 degrees (`lookDegreesPerCount` is 0.022). **First measurement on the largest debug trajectory (37 s, 19.8k frames at about 530 fps in the Editor, time at 1 ms): CSV 888 KB (44.8 B/frame), CSV gzip 194 KB, quantized delta varint + deflate 14 KB (0.7 B/frame).** Phase 1 then checked the replay: `replay.verify` re-derives the fruit events from the trajectory, and the fruit timer sums frame times, so a rounded time can move a borderline frame. **At 1 ms the verification failed on 4 real debug logs (8 mismatches; a fruit one frame late); at 0.1 ms on 3 of them; at 10 us and 1 us none, with x, z, yaw quantized as above.** The time column is the noisy one (frame-time jitter), so 1 us costs about 2.8 B/frame instead of 0.9 (over 76 usable debug logs 3.55 B/frame at 1 us, and 0 of them verified worse than the unquantized originals). A whole run is then well under 1 MB; bandwidth is still not a constraint, and exact replay is kept. The chunk header carries a CRC32 of the uncompressed bytes (DEFLATE has no checksum, and a flipped bit in a body can decode to different valid numbers).
- **`harvests` is not stored.** It was a summary of the events plus the bush's attributes; the ingest step and `replay.py` derive bouts from `events` and the world file. The `note` column becomes a jsonb `payload`.
- **World files are not uploaded.** Their sha256 hashes are registered at release; `run-start` rejects a build whose world hash or commit is unknown, and flags a dirty build.
- **Prolific ID lives only in `pid_registry`;** every analysis table carries the pseudonymous `run_id`.

**Rejected alternatives.**
- *Adopting the Unity Experiment Framework (UXF).* It is built around Session/Block/Trial and per-trial files; this task is one continuous session with a per-frame log, an event stream and a manifest, and `replay.py` and `visibility.py` read exactly those semantics. UXF would mean remapping the task onto trials or running it beside our logger. What it offers (a data-handler abstraction, an HTTP POST handler, a DynamoDB WebGL handler) is a small piece of code here; it solves none of chunking, idempotent retry, resume, identity or Prolific. Its docs were last updated 2020 and I could not confirm Unity 6 / new Input System support. Kept only the idea of a sink interface.
- *Session-boundary resume.* Restarting an interrupted session replays a world whose reward mapping the participant has already learned, which corrupts the learning analysis (PI).
- *Raw files as blobs (events and trials too).* Keeps the old CSVs unchanged, but needs a second ingest step before anything can be queried or validated and forces a server-side parser for every format change. Kept only for trajectory, where SQL has no use and arrays compress.
- *Per-row trajectory.* Tens of millions of rows for a pilot cohort, and every row repeats `run_id` and `session`; the chunk table is smaller and queries (in Python) are as easy.
- *Downsampling the trajectory (for example 30 Hz).* Saves little once frames are delta-coded and compressed, loses the frame-exact replay and `HarvestManager` mirroring, and cannot be undone; a lower rate can be applied at analysis time.
- *Logging inputs instead of state and re-simulating.* Needs Unity's physics to be reproducible across machines and frame rates (existing decision: log state, not inputs).
- *Fire-and-forget upload.* Silent data loss; `evidence_integration` already warns after two consecutive failures, and here missing rows break resume as well, hence pause-until-acknowledged.
- *Reusing the `evidence_integration` Supabase project.* Separate quotas, RLS and clean deletion.

**Phase 2: the server (built 2026-10-29).**
- **Logic in SQL functions of an unexposed `server` schema, called by thin Edge Functions over a direct database connection** (`SUPABASE_DB_URL`, `npm:postgres`), not supabase-js and not PostgREST RPC. Reasons: the idempotent inserts, gap checks and resume state are then atomic and testable in Postgres alone; functions in `public` would be reachable by `anon` through the REST API (the `server` schema is not exposed and every grant is revoked); and there is no Docker here, so the Supabase local stack cannot run, while a real PostgreSQL (`pgserver`) plus the real functions under Deno can. The cost: the direct connection from an Edge Function is unverified on a real project (its `Db` interface is one file to swap).
- **A 200 from `append` means the rows are stored**; everything in a request commits or nothing does, so the client can drop rows from its queue on success and the pause-until-acknowledged rule has a clear meaning. Sequence conflicts are 409s: the client re-syncs through `run-start`, which returns the `*_next` numbers.
- **The server derives, never trusts:** a chunk's `first_seq`, frame count, time span and last frame come from decoding it (TypeScript decoder, tested against the Python golden chunk); the resume pose is the last decoded frame stored with the chunk.
- **A returning Prolific ID gets a fresh token and the old one stops working** (so a second tab cannot keep writing into a resumed session). The Prolific ID alone authenticates the return, as in `evidence_integration`: anyone who knows another participant's ID could take over their run; accepted because the data is not sensitive and the ID is the participant's own.
- **Dirty builds are accepted and flagged** (`runs.build_dirty`); an unregistered commit, or a world or Interlude hash not in `worlds`, is refused (403) so that data can always be tied to registered code and worlds. A resume on a newer commit is allowed and recorded (`build_commits`).
- **Rejected:** a `completed`-only check at finish without per-session checks (a participant who left early would pass); letting later appends change a session's config, world or name (immutable after the first append); a Python or Deno-free server for tests (it would not exercise the deployed code).

**Phase 3: the Unity client (built 2026-10-29).**
- **`DataLogger` keeps its name, scene wiring and per-frame/event hooks; everything after the rows is new** (`DataPipeline`, sinks, `TrajectoryCodec`). The scene needed no edit: the pipeline is a `DontDestroyOnLoad` object created on first use and the gate's UI is built at runtime, like `HudWidgets`.
- **The uploader must outlive scene reloads** (a session's last batch is still in flight when the next scene loads), hence the persistent `DataPipeline`; leaving a session and quitting wait for the queue to drain (`TryLeave`, `wantsToQuit`, 15 s cap on quit).
- **`PauseGate` is the only writer of `Time.timeScale`** (an instruction screen and the data gate can both hold the game; one releasing must not un-pause the other). `pause` events carry the reason in their payload instead of separate `upload_pause` events.
- **Local copy always, even online:** a participant's computer keeps a backup of what was uploaded, and an offline run is complete on its own. The local folder is named by the server's run id when online.
- **A 4xx from `append` stops uploading and shows a message; only network errors, timeouts, 408, 429 and 5xx are retried** (a bad token, unknown world or sequence gap cannot be fixed by retrying, and retrying forever would hold the participant at a black screen with no explanation).
- **`online.json` holds the URL and the publishable key and is committed with `enabled: false`;** the key is public by design. A participant build flips `enabled`. Rejected: putting the URL in `SessionConfig` (ten assets would have to agree, and it is not a session parameter) and an environment variable (a participant's machine).
- **Unity's player stops updating when its window is unfocused** (`runInBackground` is false): upload and the gate stand still then too. Observed driving a build on Xvfb without focusing its window. Not changed here; it matters for a participant who switches windows mid-session (the existing `focus_lost` events record it).
- **Removed:** `harvests.csv` (derived), `manifest.json` (replaced by the session row), `interlude.csv` (now `interlude_trials`), the `note` strings (JSON payloads), `SessionDataPath`. The old `ForagingData/` debug folders (661 of them) were deleted as the PI approved; `ForagingData/_worlds/` (56 MB of archived debug-time worlds) was left.

**Phase 4: resume (built 2026-10-30).**
- **Resume is keyed by the Prolific ID**, not by a stored token: an ID is the only identity the participant brings, it works on any computer and in a browser, and it is what Prolific supplies. A run with no ID cannot be resumed. Rejected for now: a token kept in local storage (a lab computer restarted for the next participant would resume the previous one's run).
- **The scene is reloaded for the session to continue**, because the first scene starts as session 0 before the server answers (the pipeline's start is asynchronous and the scene's objects initialise at load). The old scene's logger is told its data is superseded (`SceneSuperseded`) so nothing it recorded is sent. Rejected: making the whole scene wait for the server (the components initialise in `Awake`/`Start`, which cannot wait; a bootstrap scene would be a scene edit).
- **Sequence numbers are assigned when rows are flushed, not when they are logged**, because rows logged while the scene starts (a focus event, the Interlude's first trial) precede the point where the resume state is known.
- **`session_resume` is a new event type** (not the existing `resume`, which is the end of a pause). The clock continues from `clock`, the later of the last stored frame and the last stored event, so `t` stays monotone even though the last 5 s of frames may not have been uploaded; the fruits of that gap are in the events and not derivable from frames, which `replay.py` accepts by taking the counts from the log.
- **What is restored is what the data holds:** pose, clock, score, fruits taken per bush, the Interlude's order and finished trials. Not restored: the open bout and fruit progress (they start over, and the event names the bush), which individual fruits were taken (the first n are removed), the trial in progress. Alternatives that would restore more (logging per-fruit identities, bout progress) change the data format for little scientific gain.
- **The server's resume state is flat JSON** (arrays of small objects, -1 for none) because Unity's JsonUtility cannot read dictionaries or nulls; the alternative was a small JSON parser in the client.
- **`run-finish` is called from the client** after the last session's data is acknowledged, and when a resume finds every session complete; a failure other than a network error ends the attempt rather than holding the participant (the researcher can finish a run from the database).
- **An abandoned session still logs `session_end` with `completed` false**; a resumed session's events therefore continue after it. Kept because `run-finish` checks for the event and the participant's last data is flushed by it.

**Phase 5: the WebGL port (built 2026-10-30).**
- **A `Boot` scene preloads StreamingAssets into memory** (`StreamingData`), and the game reads files through it everywhere. Rejected: copying the worlds into `Resources/` (a second 20 MB copy in the repository, and every build, to avoid one scene), making `GameManager.Awake` asynchronous (every component initialises from what it loads), and starting the game scene and reloading it once the files arrive (components would initialise on missing data). The scene costs one hop on desktop; playing `SampleScene` in the Editor bypasses it, and `StreamingData` falls back to reading files, so the development loop is unchanged. The file list is generated (`streaming_files.txt`) because a browser cannot list a directory.
- **The click that starts the game is the gesture the browser needs** for pointer lock, audio and fullscreen; the Boot scene waits for it. After that, whenever the capture is released (Escape) the game holds still behind "Click to continue" (`PointerLockGuard`, a third reason in `PauseGate`), so looking never fails silently. Not verifiable headless: needs a real browser.
- **A browser build has no local copy and needs the server:** without `online.json` enabled it shows a message and does not play. The server is the only record, which the pause-until-acknowledged rule already assumed.
- **Server and participant ID come from the address:** `?PROLIFIC_PID=` always; `?onlineUrl=&onlineKey=` only in a development build (a link must not be able to redirect a participant's data). `?fullscreen=0` skips forced fullscreen (testing).
- **UnityWebRequest.timeout is not honoured in a browser, so every request is aborted by the client after its own timeout** (`HttpSink.Send`); an aborted request is a connection error and is retried.
- **IL2CPP/WebGL builds here use `ExplicitlyThrownExceptionsOnly`, so a null reference does not throw:** `_file.Write` on a null sink ran with a null `this` and failed later with a misleading "path1 is null" (found in the browser, fixed with `?.`). Code that is skipped on a platform has to be null-safe by hand.
- **GitHub Pages sends no `Content-Encoding`, so the build uses Brotli with Unity's decompression fallback** (`Player Settings > Publishing`; files become `.unityweb`); the fallback is slower than the browser's own decoder, a cost taken for a host the PI already knows. Rejected: uncompressed output (wasm and data several times larger to download) and a host that can set headers (a different workflow to learn). **This changed `ProjectSettings/ProjectSettings.asset` (`webGLDecompressionFallback`, and WebGL platform entries from switching target) and `ProjectSettings/EditorBuildSettings.asset` (the scene list: `Boot` first), which CLAUDE.md says not to touch unasked; they are needed by the port and listed here so the diff is expected.**
- **Deploys are one fresh commit in a separate repository** (`scripts/deploy_webgl.sh`), not part of this repository's history and not built in CI (Unity needs a licence), which keeps each deploy from adding tens of megabytes to a history that cannot delta them. It never pushes.
- **No unload flush for now:** a `pagehide` post with the unsent rows (a jslib plus `fetch(keepalive)`) would save the last second of events and five seconds of frames when a tab is closed, but resume already recovers the session and the plugin can only be tested in a real browser. Left out; revisit if real tab closures lose more than that matters.

**Phase 5 follow-up: no code-driven fullscreen (2026-10-30).** The first real-browser test showed black screens (with the game's sound still playing) around the switch to fullscreen, and a headless run reproduced a garbled canvas only when `Screen.fullScreen = true` was called after the click. The Boot scene no longer requests fullscreen; the canvas keeps the page's size and the participant may use the page's own button. Whether any change of canvas size breaks the drawing (window resize, F11) is not known. The more robust design, not built: size the canvas once in the page's own HTML before Unity starts, put the start and "click to continue" prompts in the page (an HTML overlay cannot go black with the canvas), a permanent "reload; progress is saved" note, a lost-graphics-context message, and an optional page-level fullscreen request before the canvas is sized.

**Phase 5 follow-up: a fixed drawing buffer, scaled by the page (2026-10-30).** Even without a fullscreen request, the page's own fullscreen button left the game black and it did not recover when fullscreen was left (PI's real-browser test, Chrome on Linux): any change of the canvas size breaks the drawing. `scripts/patch_webgl_page.py` (run by `deploy_webgl.sh` on the copy it publishes, so `Builds/web` stays as Unity wrote it) sets `matchWebGLToCanvasSize = false`, a fixed 1280x720 canvas buffer and CSS `object-fit: contain` at the window's size, and hides Unity's footer and fullscreen button: Unity never sees a size change (resize, F11, zoom), and every participant gets the same 16:9 picture whatever the window (field of view and resolution no longer depend on the display; the session row's `display` is 1280x720). The cost is a softer picture on large screens; the size is an argument of the script (a bigger buffer costs frame rate on weak GPUs). Checked headless only: the buffer stays 1280x720 across window sizes and the start screen still draws; the game scenes and browser fullscreen (F11) need the PI's browser. A custom WebGL template (a folder under Assets, chosen in Player Settings) would do the same without patching but changes ProjectSettings; the script fails loudly if a Unity upgrade changes the page it patches. Pointer-lock deltas are raw device movement, so letterboxing does not change the look sensitivity; UI clicks would be offset by letterboxing (the game only uses "click anywhere").

**Phase 5 follow-up: Escape pauses, the cursor shows, and trials record their pauses (2026-10-30).** Unity's `Cursor.lockState` does not notice the browser releasing the mouse capture (Escape, switching tab or window): across all browser runs no pause with reason `pointer` was ever logged, so the guard never engaged. `Plugins/WebGL/PointerLock.jslib` reads `document.pointerLockElement` and `PointerLockGuard` pauses on its absence (after a 0.5 s grace after a click, because the browser grants a request a few frames late): the clock stops (`PauseGate`, reason `pointer`), the sound is muted (`AudioListener.pause`), the system cursor is shown so the participant can click away or switch tabs, and a click recaptures and resumes. Chrome ignores a capture request made within about a second of an Escape, so the first click may need repeating. The overlay stays opaque ("Paused"), so a pause does not show the world. **Scientific side effect:** a participant can now pause for as long as they like, in any session, and the Interlude's trial clock stops while paused, so a pause inside a timed trial is free thinking time. The browser cannot be stopped from releasing the capture, so each Interlude trial records `paused_seconds` (real seconds held still while the trial was live; `interlude_trials`, added at the end) so analyses can flag or exclude such trials; pauses between trials and during instruction screens are not counted. Not built, to decide with the data: a maximum pause, or restarting a trial that was paused. The drawing buffer is now 1920x1080 (`patch_webgl_page.py` default; about 2.25 times the pixels of 1280x720: weak GPUs will show it in the logged frame statistics).


**Consent and participant-ID screen, in Unity (2026-10-31).** Online builds (`OnlineSettings.Active`) open with `ConsentScreen` (Boot scene, before the click-to-begin step): consent text from `StreamingAssets/consent.txt` (first line `version: <id>`), a participant ID (locked when `?PROLIFIC_PID=` is present), a typed signature, an agreement box. Alternatives: an HTML page before the canvas loads (robust against canvas failure, native text input and scrolling, could test WebGL first) was rejected because a participant whose canvas fails cannot do the study anyway, and a second implementation would be needed for desktop builds; keeping one code path and one look won. Consent is asked on every visit, including a return to resume (simpler, and each is logged). The typed signature is stored (`consents`: run, text version, name, client time) apart from the analysis tables like the Prolific ID. Typed and Prolific IDs share one registry (the same `[A-Za-z0-9_-]{1,64}`); lab IDs should carry a prefix such as `LAB-` so they cannot collide with Prolific IDs. The screen is browser-only: desktop builds and Editor play never show it. The page's canvas is now sized to the picture rather than letterboxed with `object-fit`, because Unity maps mouse positions from the element's box and the screen has buttons. UI text uses one typeface (Inter, OFL, `Assets/Fonts`, `Resources/Fonts/Inter SDF`) and the sizes in `UiStyle`, on canvases that all scale from 1920x1080.


**Participant wording, Prolific completion, desktop without consent (2026-10-31).** Participant-facing text uses one vocabulary: "bushes" (never trees), "points" (never reward or bonus, including the Interlude's hidden points, shown as "+N points" with no count of correct trials, so the end screen says nothing about how the choices went), "session" for every block (an Interlude is still called an Interlude: a friendlier name was considered and rejected for now), "a new area" (not "world"), "features" without hints about which matter, sentence-case headings, and "Press [Enter] to ..." below the text with keys on chips (`UiStyle.Chip`; `[Key]` in an instruction file). Each screen is one centred block (heading in bold, text, prompt) so no element has its own position to collide with another. A Prolific **completion code** comes from the server (`run-finish` returns `completion_code`, the secret `PROLIFIC_COMPLETION_CODE`, a dummy until the study exists) rather than from `online.json`, so it is not in the public build; it is returned even when the run's data have problems, because an incomplete upload is not a reason to withhold payment. The final screen shows it and, if the page address carried `PROLIFIC_PID`, redirects to Prolific's completion URL after six seconds (a same-tab navigation needs no user gesture). Typed-ID participants see the code and "You can close this page." The consent / ID screen is browser-only: desktop builds are for lab use (`-pid`), and a consent screen there would only slow scripted runs; the Editor never uploads. Removed as unused after the wording change: the correct-trial counters in `GameManager` and `NextStageLabel`.

**Review of the online data stack (2026-10-31).** An adversarial review of the server, client recorder and resume code found one data-loss path and removed about 300 lines. `server.start_run` now takes the run's advisory lock (the one `append_batch` takes) before reading the resume state: without it a second tab opening the same ID while the first tab's last upload was committing resumed from a stale state, and its first events were dropped by `on conflict do nothing` while the server answered 200 (`test_a_returning_start_waits_for_an_upload_that_is_still_committing`). A returning ID whose run is already finished gets the completion code from `run-start`, so a participant who closed the tab during the 6 s before the Prolific redirect can still be paid. **Rejected / removed:** resuming an anonymous run by token (`server.resume_run`; no client used it, every browser run has an ID); the client's held-upload buffer (always empty, `Flush` never submits before the run is ready); the C# trajectory decoder (nothing used it; the Python and TypeScript decoders are tested against each other). The five migrations were squashed into two before any real participant (the final schema is identical) and the project's migration history repaired to match.


## Reward scale: best bush 4, `rewardFeedbackMax` 4, `rewardStd` 0.6 (PI, 2026-10-30)

After playtesting, every S3/S4 bush paid well and a few very well, against S1/S2 (best bush 4.3 and 6.2 versus 3.0). Additive weights summing to the best bush's value cannot give S3/S4 as many poor bushes as S1/S2 (a sum of independent features concentrates near its mean: share with R < 0.5 is 4% and 1% versus 13% and 23%; std of R 0.66 and 0.57 versus 0.87), and the alternatives (an offset or a nonlinearity) change the reward system, so the sessions were instead matched on best bush and mean.
- **Max 4, not 3 or 5.** Popup size and pick pitch scale linearly with per-fruit reward over `rewardFeedbackMax` (was 6, so the best fruits used half the range). Whole-number rewards 0-4 are five distinguishable levels, so the best bush pays 4 and the ceiling is 4. Rejected: lowering only `rewardFeedbackMax` to 3.5 (cheaper, no regeneration, but the reward units stay as they were); P, S1, S2 weight 3 -> 4, S3 1.33/2.67, S4 1.2/1.8/0.9 (S4's exact scale-up would put its best bush above 4, and these give means 2.0, 2.0, 2.0, 1.95).
- **`rewardStd` 0.6, not 0.3 or 0.4.** Scaling the noise with the weights (0.4) keeps signal to noise but leaves a bush at a whole-number R paying that number 79% of the time; the PI wanted visible variation after rounding at every R. 0.6 gives 40% (0.4: 21%, 0.3: 10%); the cost is a harder task (a 10-fruit bush mean has standard error about 0.2) and a stronger zero clamp on low bushes.
- **No per-fruit cap.** About 1-3% of fruits in S1/S2 exceed 4 because of the noise (max 6); popup and pitch clamp at 4, the number and the score do not. Capping would lower the mean of the best bushes and break "no normalization".
- Simulated results from before this change are stale; weight-specific test constants (test_world S4, test_interlude extrapolation floor) were left to update with the re-run.

## Review of replay and offline tooling: legacy loader removed, ties, world archive, resumed Interludes (2026-10-31)

An adversarial review of `replay.py`, `rundata.py`, `server_admin.py` and `run_tests.py` (topics 6-7), run against four real browser runs (33 sessions, 2018 fruits) pulled from the database.

- **Legacy loader and `convert_legacy.py` removed.** `replay.py` read two layouts (the DataLogger's `manifest.json`/`harvests.csv`/`note` folders and the online one), with two event parsers and a `SessionLog.online` switch between camelCase and snake_case keys. Nothing writes the old layout and no folder of it exists (the 661 were deleted in phase 3), so the loader, `parse_note`/`fields`, the converter and the tests that built legacy folders are gone; those tests now build sessions with `rundata.write_session`. Also: `rundata.write_session` no longer re-quantizes (it writes what it is given), `Bushes.value`, `rundata.read_run` and dead helpers went, and `run_tests.py` derives dependencies from imports (the hand-kept table had drifted and skipped tests that its modules affect).
- **Frame-time ties are resolved by the log.** Browsers hand Unity whole-millisecond frame times, and `fruitHarvestDuration` is a whole number of milliseconds, so the frames' sum often equals the fruit time exactly. The game's float32 sum fell on either side and the log does not say which; replay's double sum fell on the late side. Before the fix `verify` failed 22 of the 23 browser sessions with fruits: 198 of 2018 fruits (about 98 per 1000, against the 0.1-0.3 per 1000 measured on the debug logs) were one frame late, every one of them at a tie. Within `TIE` = 10 microseconds of the fruit time the logged fruit (same bush and k, within 0.1 ms of this frame) now decides; elsewhere, and for an agent with no log, the plain comparison stands. Rejected: mirroring float32 accumulation (it removed the late fruits but created 59 early ones; the game's exact `deltaTime` is not recoverable from the log). The proof is still not vacuous: moving logged fruits one frame later is caught in 20 of 23 cases, and the other 3 sat on a tie. The session's closing release is accepted on either of the last two frames (the sun's clock reaches the duration on the second-to-last frame, so the bout ends there or one frame later) instead of within 1.5 median frame times of the last row, which missed it whenever the last frame was long.
- **Worlds of a pulled run are archived by `pull_run`.** A browser never archives its world files (only the Editor and standalone builds do), and the working tree's world files are regenerated, so participant data could be replayed only on a machine that had played the same worlds locally. `pull_run` now writes the world and Interlude files its sessions used into `<out>/_worlds/<sha8>_<name>`, from git at the run's `build_commit` when the sha256 matches (a warning otherwise), and replay looks in the `_worlds` folder next to the run folder first.
- **A resumed Interlude's replay carries nothing over.** The game restarts the unfinished trial in a fresh scene with every bush full (`DataLogger` restores fruits taken only for sessions), so the rebuild of the fruits-taken state at a `session_resume` is skipped when the log has trials, and the running total is reset at every resume. No resume exists in real data yet.

**Interlude points on the final screen; practice shows what it would have paid; Escape quits on desktop (2026-10-31).** An Interlude's end screen no longer shows its points, except on the practice Interlude, which shows what its choices would have earned and pays nothing (`InterludeManager.Points` counts what was earned or would have been; the logged `bonus` and `GameManager.InterludeBonus` stay 0 in practice, so no stored column changes meaning). The final screen shows "This interlude: +y points" and the total. Reason: the earlier per-Interlude "+y points" revealed the number of correct choices (y = 5 x correct), contradicting the stated design that no count is shown; the person chose to keep the information to the final screen rather than reword the docs. The Interlude's earlier "x / n correct" screen (entry above) was already replaced by points in the wording pass. A resume inside the practice Interlude restores only paid points, so its practice display restarts at 0 (accepted: rare, and nothing is paid). **Accepted:** on a desktop build the first Escape press quits the game (`QuitHandler`), and the practice controls line still says "Escape: pause", which is true in the browser; desktop builds are for lab use, so the person judged the quit acceptable. **Unchanged placeholders:** `consent.txt` says "about 30 minutes" whereas the design adds up to roughly 15-18; replace it with the approved IRB text.

## S5: equal bump heights (2026-11-02)

**Decision (PI):** both S5 bumps have height 2.8 (centres and width unchanged), replacing 2.8 and 1.8. **Why:** in the first pilot run the lower bump got 9% of the fruits against 24% for the taller one (4 of 113 nearby bushes visited); at reward noise 0.6 per fruit a 1.8 peak is easy to miss, which made S5 mostly a test of finding the taller bump. With equal heights, finding one bump is not enough to be optimal. **Cost:** the S5 world and Interlude were regenerated (worlds must be re-registered); mean S5 reward rises a little.

## Fruit colour ramp: plasma replaces viridis, and speed 11.25 everywhere (PI, 2026-11-04)

**Decision (PI):** the fruit ramp is plasma (blue-purple, magenta, orange, yellow), same 21 equal-OKLab-step stops, generated by `scripts/fruit_ramp.py` (`CHOSEN = "plasma"`). `playerMoveSpeed` is 11.25 in all twelve assets (sessions 7.5 x 1.5; the Interludes were 15 and the practice Interlude 7.5, now the same value as their sessions).

**Why:** a pilot participant (jhl) said the colour range was narrow and hard to remember, and that walking felt slow. Plasma has more hue change and higher contrast against the canopy than viridis (canopy contrast 16 against 9 in the table below, "Fruit colour ramp: viridis").

**Known costs (not fixed):** plasma was weak for protan (2.6) and tritan (3.1) steps against viridis' 4.0 and 5.5 (worst case 2.1 against 2.9), and it passes through pink and coral, so the "no red" part of the earlier constraint no longer holds (the red ripeness association is back, partly masked because the reward direction varies by session). The faster speed halves the walk-time cost relative to the old sessions and lengthens the Interlude walk to a bush (22.6 / 11.25 = 2 s, was 1.5 s at speed 15): a trial still fits `interludeTrialSeconds` 10. `player_move_speed` is in `fingerprint.SIM_FIELDS`, so every recorded simulation environment hash changes and the agent results are stale until re-run (not re-run). Participants before 2026-11-04 saw viridis and speed 7.5, so their data are not comparable on perceptual difficulty or time cost.

**Canopy tint (PI, 2026-11-05):** each bush's canopy is the moss texture times a tint, drawn per bush from its own seed (`fruitSeed ^ 0x1bd1e995`), uniform in [0, 1] and mapped dark conifer (0.55, 0.70, 0.65) at 0, no change at 0.5, light sage (1.30, 1.20, 1.30) at 1 (`SessionConfig.canopyTintDark/Light`, `CanopyTint(u)`; both white switches it off). Purely decorative: independent of shape, colour, moisture, reward and position, the same bush has the same canopy in every run, and `CanopyMaterial.mat` stays white. Why: a darker canopy raises the fruit contrast at mid and high attribute values (OKLab distance about 31 to 35 and 56 to 61), a lighter one raises it at the purple end, so a spread varies contrast per bush instead of fixing one trade-off; the scoring of tints is in the session notes of 2026-11-05 (the weakest point of plasma is its dark purple end, which no canopy tint moves by more than 2 to 4). Cost: a fruit's contrast with its canopy now varies between bushes (the lightest sage lowers the orange and yellow end from about 56 to 44-48). Not in the world files and not read by the simulator.

## Fruit colour ramp: viridis, equal perceptual steps (2026-11-02)

**Decision (PI):** fruit colour follows the viridis ramp (dark purple, blue, teal, green, yellow), stored as 21 evenly spaced stops in `SessionConfig.fruitColorRamp` and generated by `scripts/fruit_ramp.py` (viridis re-spaced so equal steps of the colour attribute are equal perceptual distances, OKLab). This replaces the two-colour blue to orange blend (`fruitColorLow`/`fruitColorHigh`, removed). The hard constraint "blue to orange only, no red/green" is replaced by "no red; generated, not hand-picked". Fruit radius rose from 0.6 to 0.7 (about 17%) for more signal per fruit.

**Why change it:** the old ramp blended blue and orange in RGB, so its middle was a dark dull mauve. Measured in OKLab, steps of 0.1 in the attribute ranged from 4 to 7 (uneven), the smallest step was 0.8 for tritan vision, and the worst case over vision types and lighting was 0.4: mid-range bushes were hard to tell apart for everyone, worse for colour-blind participants. A pilot participant also reported trouble separating mid-range colours.

**Goals used to choose:** even perceptual steps along the whole ramp; steps that survive protan, deutan and tritan simulation (Machado et al. 2009, severity 1) and lighting changes (dim, bright, warm, cool); a mix of hue and lightness rather than lightness alone (fruit are small and lighting moves lightness); contrast with the canopy and ground; and no red.

**What was compared** (`scripts/fruit_ramp.py`; the prototype also built hand-made ramps from OKLCH anchors): the old blend; the same path re-spaced; a violet-bridge ramp; diverging ramps through a pale neutral, lavender-grey, cream or pale yellow; ColorBrewer PuOr; cividis; viridis; plasma; YlGnBu reversed; and three monotone-lightness customs (navy, lilac, sand, gold; a floor-lifted diverging ramp; ink, violet, rose, light yellow). Smallest step between attribute values 0.1 apart, worst over vision and lighting, hue share of the change:

| ramp | normal | protan | deutan | tritan | worst case | hue share | canopy contrast (min) |
|---|---|---|---|---|---|---|---|
| old blend | 4.0 | 3.4 | 3.9 | 0.8 | 0.4 | | |
| viridis | 8.1 | 4.0 | 6.1 | 5.5 | 2.9 | 45% | 9 |
| cividis | 6.4 | 6.1 | 5.8 | 4.0 | 3.4 | 33% | 4 |
| plasma | 9.3 | 2.6 | 5.3 | 3.1 | 2.1 | 51% | 16 |
| PuOr (reversed) | 7.5 | 6.8 | 7.9 | 5.6 | 2.1 | 24% | 11 |

**Why viridis:** the largest steps (8 against 4 to 7) with a large hue share (45%), the smallest step is acceptable for every vision type (4.0 for protan, the weakest), it is a standard colour-vision-safe ramp, and it has no red. The diverging ramps (pale or white middle) solved the dull middle but make mid-value fruit the most conspicuous: contrast with the canopy varied by 40 to 60 percent along the ramp. Plasma is weak for protan and tritan and passes through pink and red. Cividis has the best worst case but a grey-olive middle that disappears on the ground. PuOr and the dark-ended ramps rely on lightness and go nearly black, which vanishes on shaded canopy.

**Known costs (not fixed):**
- The teal and green middle of viridis has low contrast against the green canopy (distance 9 against 16 to 18 for the alternatives). The canopy colour may be retinted away from green if this shows up in play; the canopy is the free parameter.
- Contrast with the canopy varies along the ramp (spread 1.29), so salience is not constant across attribute values. The same holds for every ramp that uses lightness.
- The green-to-yellow part of the ramp keeps a weak ripeness association (low = purple, high = yellow). It is partly masked because reward direction varies by session (linear, inverted, peaks). Counterbalancing the ramp direction across participants would remove it; not done.
- All distances use OKLab as a perceptual model, not a measurement of these participants. The canopy and ground colours used for contrast are approximations. Not yet judged in the game on real monitors.
- No world, Interlude or simulation record changes (colours are not read by the simulator); this changes what participants see, so data collected before it is not comparable on perceptual difficulty.

**Radius:** 0.7 instead of 0.6 (in every session asset; the 0.15 in the code is only a default). Fruits are small spheres on large canopies; a bigger sphere carries more colour signal per glance. No effect on harvest rules (range uses the canopy), replay or visibility.

**Fruit brightness (same day, after the ramp):** in Play the fruit looked much dimmer than the palette. From `FruitUnlit.shader`: the shaded side fell to 30% of the colour, half of the result was a flat colour times a dim ambient term, the painted-plaster texture multiplies the colour, and the sun's post-exposure (about -0.1 EV at the start, -0.6 EV at the end of a session) darkens everything, fruit included, as the sun lowers. Three `SessionConfig` parameters now control it: `fruitShadingFloor` (0.3 before, 0.65 now: the shaded side is 65% of the lit side), `fruitBrightness` (1.2) and `fruitExposureCompensation` (1: `SunController` passes the inverse of the post-exposure to the shader as `_FruitExposureComp`, so fruit keep their brightness through the session, as the unlit-fruit rule always intended). Values are first guesses to be judged in Play; the ramp's perceptual steps are unchanged because brightness is applied equally across the ramp. Rejected: raising `fruitColorPreservation` to 1 (flat discs, no 3D shape) and boosting saturation of the stops (they are already at the ramp's design values; the loss was in shading, not in the colours).

## S5: one bump (2026-11-02)

**Decision (PI):** S5 is a single Gaussian bump over (shape, colour) plus the linear moisture term (height 3.0, width 0.2, a new hidden centre), replacing the two-bump version. **Why:** in two pilot runs (one participant) the two-bump S5 was too hard: the first time the lower bump got 9% of the fruits, the second (both bumps 2.8) the participant found one bump and visited 1 of 129 bushes near the other, reward per fruit stayed at about the world mean for two thirds of the session (1.8 and 1.5 against 1.66) and the Interlude was 11 of 20 (chance is 10). S4 is already three features at once; a single nonlinear peak is a smaller step. **What is lost:** the exploration-against-exploitation test (finding a second optimum after finding the first); it can come back as a later, harder session. **Cost:** S5 world and Interlude regenerated and the worlds re-registered; earlier S5 data are not comparable. The centre is only in the gitignored key file and the assets.


## Downloading participant data for analysis (2026-11-04)

**Decision:** `scripts/human_data.py download` mirrors the database into two forms under `ForagingData/`: the raw per-run layout of `rundata.py` (so `replay.py` and `visibility.py` read a participant like a local log) and `humans.sqlite`, tidy tables for pandas/plots (`participants`, `sessions`, `events`, the view `fruits`, `interlude_trials`). The participant ID (`pid_registry`) and the signed name (`consents`) are in `participants` and `run.json` so a filter such as `load(exclude=["peter"])` can drop the developer's own runs; `token_hash` is never downloaded.
**Why these choices:**
- *The Supabase CLI, not `FORAGING_DB_URL`:* the CLI is already logged in on the dev machine; the connection string was never set up. One query helper (`query`) is the only transport; psycopg could replace it.
- *SQLite plus the layout, not Parquet or CSV only:* no new dependency (pyarrow is not installed), SQL when wanted, and the layout keeps replay working. Trajectory frames stay in the layout (`Humans.trajectory`): in the table they would be millions of rows for no gain.
- *Incremental:* a run is fetched again only when its status, last upload time or session count changed; the whole database is under 1 MB of trajectory per 5 participants, but every run costs about 4 s of CLI calls.
- *Runs cleared from the server are kept* with `on_server = 0`: the participant tables have been cleared before (pilots), and the download may be the only copy.
- *No derived performance metric* (total score, accuracy per participant): the metric is undecided (see the results database notes); the tables hold `final_score`, `n_fruits`, `n_correct`, `bonus` as logged.
- *Not recorded by the game:* the WebGL renderer string, so a software-rendered browser can only be spotted through `mean_frame_ms` in `sessions`.


## Interlude design: trial count, repeats and gap windows (agent test bed, PI, 2026-11-04)

**Decision:** the Interlude of S1 to S5 is 20 trials: 18 distinct pairs spread evenly over a feature-gap window of 0.15 to 0.55 and a reward-gap window of 0.25 to 1.5 spreads of the session's reward, plus 2 exact repeats of earlier pairs (`interludeRepeatCount` 2, at least 8 trials apart). The generator got optional ceilings (`interludeMaxRewardGap`, `interludeMaxFeatureGap`, 0 = none) and the repeat options; four `SessionConfig` fields, set on the five assets; the files were regenerated. Participants who played earlier saw the older 20 distinct pairs.

**How it was chosen:** `scripts/interlude_design.py` is a test bed. A *target* is a learned value function: the critic of `replay_len0_5` (the replay delta rule on RBF 0.5 features) after it learned, through `human_agents.replay_into_agent` in fast mode, from each of 4 participants' sessions S1 to S5 (20 targets), plus 5 synthetic critics (four linear with known weights, one peaked on shape). A design is drawn (trials, repeated share, a similarity range spread evenly: the generator's own `choose_gap_trials` on random attribute pairs, no terrain); the target chooses by a softmax on its value difference (tau times the spread of its values over the session's bushes, greedy picks are separable); a basis is fitted as a preference model (logistic on feature differences, ridge by cross-validated choice log-likelihood) and scored against the target's own function over the session's bushes. 30 seeds per cell, dirty tree, one run each (no standard errors: seeds within a target are not independent samples of participants).

**Results (Pearson of the fitted against the learned function; weight RMSE and sign errors are of the least-squares attribute weights, so read them only for roughly linear targets):**
- *Number of trials* (tau 0.25, all new pairs, 12 000 fits): N = 10 / 20 / 30 / 40 gives 0.79 / 0.85 / 0.87 / 0.88 for a linear basis and 0.82 / 0.90 / 0.94 / 0.96 for quadratic, RBF 0.3 and RBF 0.5; weight RMSE 0.28 to 0.13, sign errors 15% to 3% for the flexible bases. The gain per ten trials is about +0.08 (10 to 20), +0.04 (20 to 30) and +0.02 (30 to 40). Linear-rule sessions (S1, S3, S4) and linear synthetic targets are recovered equally well by every basis (0.93 to 0.97 at N = 20); a linear basis cannot represent S2's peak (0.68 at N = 20, never above 0.72) or the synthetic peak (about 0), where RBF 0.3 is best at every N (0.73 at N = 20, 0.86 at N = 40). S5 (a bump): linear 0.89, flexible 0.95 to 0.96 at N = 40.
- *Repeats and tau* (N = 20, RBF 0.3): the share of the 20 trials that repeat an earlier pair costs recovery, never helps: at tau 0.25 Pearson is 0.91 / 0.91 / 0.88 / 0.85 for 0 / 10 / 30 / 50%; the cost at 50% falls from 0.078 (tau 0.1) to 0.048 (tau 1.0), as noisy pairs gain more from a second look. **Tau is the largest effect:** 0.93 / 0.91 / 0.85 / 0.74 for tau 0.1 / 0.25 / 0.5 / 1.0 (sign errors 3% to 27%; the peak target goes from 0.77 to 0.38).
- *Similarity window* (N = 20, tau 0.25, 10% repeats, RBF 0.3): near-ties and the narrow band of very similar pairs are the worst. Feature gap: floor 0.05 / 0.15 / 0.25 / 0.35 with ceiling 0.7 gives 0.90 / 0.91 / 0.92 / 0.92; a ceiling of 0.25 gives 0.82 with floor 0.05. Reward gap (units of the session's spread, gaps drawn up to 2.5): a ceiling of 0.5 gives 0.67 to 0.77 (31% sign errors), a ceiling of 1.5 gives 0.91 to 0.93, the best window 0.5 to 1.5 or 1 to 1.5; S2 is the most sensitive (0.44 with the ceiling at 0.5). Several windows lie within 0.01 of the best, so the window was chosen from what the geometry allows.
- *The committed hybrid trials* (the 20 distinct pairs of 2026-11-02; reward gaps 0.25 to 3.4 spreads, median 1.5 to 1.9, only 40 to 50% inside 0.25 to 1.5; feature gaps 0.11 to 0.67): Pearson 0.91 (S1 0.92, S2 0.86, S3 0.92, S4 0.94, S5 0.90). The new windows with 18 distinct pairs plus 2 repeats (the repeats swapped in by hand for this check, exact repeats in the files): 0.93 (S1 0.96, S2 0.85, S3 0.96, S4 0.95, S5 0.94), sign errors 3% against 7%; S2's peak stays the weakest.
- *Can the participants' method (`human_analysis.py`, the Interlude logistic regression) recover what an agent learned?* (`scripts/agent_inference.py`): with 200 simulated picks per trial the fitted weights have a cosine of 0.9 or more with the agent's own least-squares weights in every session; with 20 trials and one pick each, tau 0.25 gives a median cosine of 0.97 (90% of fits above 0.9; the cosine to another session's ideal weights is about 0.3), tau 1.0 a median of 0.87 (41% above 0.9); the sign of each weight agrees only about 80 to 87% of the time, so the dominant direction is recovered and the small weights less reliably.

**Why these choices:**
- *N = 20:* the knee of the trial-count curve; ten more trials buy about +0.02 for 100 s of a participant's time. *Basis RBF 0.3 for the sweeps:* never worse than linear, far better where the rule is peaked (S2, S5), small cost where it is linear at N = 10; the weights of a linear basis mean nothing for a peak, so function-level scores are the main metric there.
- *10% repeats (2 of 20):* the cost in recovery is within noise; the purpose is a consistency check on real participants (a repeated pair should get the same answer), which the simulated chooser, with no side bias and no memory of its earlier pick, cannot value. Two agreements out of two is a coarse screen, and an identical scene invites repeating one's own earlier pick (the separation of 8 limits this, not removes it).
- *Exact repeats with bush entries of their own:* the game does not refill a bush between trials, so a repeat that reused the bush ids would find the bush the participant harvested before depleted; a copy of the entries (same position, radius and attributes, fresh pre-drawn rewards that the hidden outcomes make irrelevant) needs no change to the game. Confirmed in a playtest (S1's trial 19 repeats trial 6 and trial 20 repeats trial 1, the logged rows have equal attributes and different bush ids).
- *Rejected: repeats with the sides swapped or at another site.* Moisture is the terrain's at the bush's position, so a swapped or relocated pair does not have the same attributes.
- *Rejected: an adaptive Interlude* (the next pair chosen to be most informative given the fit so far), probably the best recovery per trial, but the trial set must be the same for every participant to be comparable.
- *Rejected: calibrating the choice noise from the participants.* An effective temperature per participant was estimated (`agent_inference.py --noise`: pooled 0.3 to 0.9 with lapse rates 0 to 0.8; S1 picks ran against the critic for two participants), but it mixes choice noise with how far a participant's value function had converged by the Interlude, so it is not trusted; the sweeps use the agents' tau (0.1 to 1.0) and no lapse rate.
- *Not run: the five generator modes at N = 20* (the generator makes one Interlude per session and mode, so there are only five designs per mode and the comparison has no power). The committed hybrid trials already recover as well as the abstract designs (0.91 against 0.91 to 0.93), so the terrain rules do not cost recovery.
- *Window in raw reward units:* the existing minimum is in raw points, so the new ceiling is too; the windows are set per session from the generator's own `scale` (the spread of the reward over typical bushes) and printed in `docs/SCIENCE.md`.
- *A repeat count above half the trials is clamped* (a short Interlude, as the tests use, keeps its pairs).

**Consequences:** `interlude.py` is an engine file, so every earlier simulation is stale by the engine hash, and `fingerprint.SIM_FIELDS` lists the four new fields (every environment hash changes). The agents' Interludes in the battery are generated by the same function, so a session override of the trial count or the repeat count applies to them too. Not yet done: the same function-level recovery for the first-visit choices of a session (`prior_carryover.py`), and a quadratic or bump fit with the participants' own data.

## Custom practice feature set: cube bushes, black-to-white fruit (2026-11-05; REMOVED the same day)

**Removed (PI, 2026-11-05):** replaced by the ABAB double feature sets and a random-reward practice (see "Session structure revised" and the feature-set entries below). The cube canopy (`CanopyForm`), the practice swap (`customPracticeConfigs`, `-customPractice`) and the `P_Cube` assets were deleted; what follows is kept as the record of what was tried: a renderable cube with a random yaw, a black-to-white fruit ramp, and a list swap in `GameManager`.

**Why:** the default practice (P) uses the same shape and colour channels as S1, so what participants learn about the reward mapping there can carry over into S1. A practice set with different features lets S1 start fresh. Practice is not analysed, so the set is a mode, off by default.

**What:** `SessionConfig.canopyForm` (`Ellipsoid` 0, `Cube` 1). A cube is a half-buried unit cube scaled to the canopy width, with a random yaw per bush drawn from the bush's own seed (`fruitSeed ^ 0x2545F491`, independent of the fruit layout); the fruit layout is the usual hemisphere direction pushed radially out to the cube surface; the blocker is a `BoxCollider` on a child of the canopy (so it takes the yaw and the spent shrink). The shape channel is removed by giving the asset equal width and height ranges (the side, 3.5) and a zero shape weight, so `world.py` needs no change (radius comes from the width range). Fruit colour is the `gray` colour map through `fruit_ramp.py --stops --ramp gray` (21 equal OKLab steps, black to white). Assets `P_Cube` / `P_Cube_Interlude` (world seed 100, own world files) are copies of P / P_Interlude; the reward is colour only (linear, weight 4) in place of P's shape-only reward, since the practice needs one attribute that predicts reward.

**Switching:** `GameManager.customPracticeConfigs` holds the two assets; they replace the list's practice session and practice Interlude (matched by kind) when `GameManager.useCustomPractice` is ticked, `customPractice` is true in `online.json`, `-customPractice` is on the command line, or `?customPractice=1` is in a development build's address. Off by default. The session row's `name` (`P_Cube`) and its stored config (`canopyForm`) identify the mode.

**Rejected:** a reference from the practice asset to its custom variant (`JsonUtility` would write it into the logged config as an instance id); a runtime override of the practice asset's fields (the world, hashes and logs would not tell the modes apart).

**Not done:** `perception.py` and `visibility.py` still model every canopy as an ellipsoid, so occlusion of a cube is approximate (practice only; harvest range, which `replay.py` checks, depends on the radius alone). Instruction text is unchanged (it does not mention the different look). The rim-light overlay was not tuned for flat faces.

## Hue-arc colour sets for alternating sessions (2026-11-05)

**Why:** a second colour set lets sessions alternate (ABAB) so what a participant learned about one colour mapping cannot carry over to the next session. The aim was two sets that each change over hue only (lightness fixed, so lightness is never the axis that carries reward in either set) and share few hues.

**What:** `fruit_ramp.py` ARCS: `warm_arc` (OKLab lightness 0.65, hue 20 to 140: red-coral, orange, yellow-olive, green) and `cool_arc` (0.65, hue 215 to 335: teal, blue, violet, magenta), each at 92% of the largest chroma the sRGB gamut allows at that hue, resampled to 21 equal perceptual steps. `./venv/bin/python scripts/fruit_ramp.py --stops --ramp warm_arc` prints the stops. They are 75 degrees of the hue wheel apart at the nearer ends. The machinery to alternate them across sessions, and the assets that use them, are not built yet.

**Measured (lightness 0.65):** smallest 10% step 3.3 (warm_arc) and 3.7 (cool_arc), against 9.3 for plasma; smallest distance between a stop of one and a stop of the other 18.4 normal, and 17.3 / 16.2 / 3.1 under protan / deutan / tritan simulation. Inside a ramp the smallest step for colour-blind simulations is 0.1 to 0.3 (essentially none), so a colour-vision screen or a separate analysis of colour-vision-deficient participants is needed before using hue-only ramps in data collection.

**Rejected:** (a) ramps that vary in lightness as well (internal steps 7 to 8 and colour-blind steps 5 to 6.5), because lightness could then act as the reward axis in both sets; (b) random-search hue paths (they drift through grey and perform worse than arcs); (c) arcs longer than 160 degrees (they leave no gap between the two sets); the 20+120 start for warm_arc was the PI's choice, better than 0+140 in separation from cool_arc (18.4 against 11.2) at a smaller step (3.3 against 4.0).

**How they were found:** scratch scripts (not kept) searched arc start and sweep at lightness 0.55 to 0.80 and scored internal steps, steps under protan/deutan/tritan simulation (Machado et al.) and the smallest distance between the sets.

## Height-only and width-only shape sets (2026-11-05)

**Why:** the shared shape axis scales the canopy's width down while its height goes up, so a participant who learns "tall and narrow pays" in one session can carry it into the next. Two optional alternatives let sessions alternate (ABAB) between ellipsoids that change in one dimension only: a **height-only** set and a **width-only** set (an ABAB machinery is not built yet; this adds the sets and the render rule).

**What:** `scripts/shape_sets.py` `SETS`: `height_only` (width fixed 4, height 4 to 15) and `width_only` (height fixed 4, width 4 to 12; width runs from the range's y to its x, as in the shared axis). They are `SessionConfig` field values only (`canopyWidthRange`, `canopyHeightRange`), so `world.py`, `visibility.py`, the collider and the rim light work as for the shared axis, and a collapsed width range (height-only) gives a constant canopy radius (spacing and harvest range independent of the shape). New fields: `fruitSizeFollows` (Nothing 0, Height 1, Width 2) and `fruitSizeSlope` (0.3), read by `SessionConfig.FruitRadiusFor` and `Tree.ApplyAttributes`: fruit radius = `fruitRadius * (1 + slope * (size - mid) / half)`, linear in the followed dimension, +-30% across its range (0.49 to 0.91 at the base 0.7). Default Nothing: existing assets are unchanged. Render only: nothing to regenerate. `shape_sets.py <set> <asset>` prints the `unity command set_serialized_field` lines that apply a set.

**Chosen from renders** (Python mock-ups at the game's camera: eye height 5.1, 75 degree vertical field of view, 20 and 40 units): the PI preferred the linear scaling to a strictly proportional one, which gives 0.29 to 1.11 (a 3 to 4 times change) and lets the fruit size dominate the picture. The ranges were raised from 1 to 15 / 1 to 6 after the first renders: with a minimum width or height of 1 the fruit (radius 0.7) were as big as the bush and the shape read as a cluster of fruit.

**Known issues, not solved:** (1) both sets grow to the biggest bush at their high end, so a "bigger is better" prior can carry over unless the rewarded end is randomised; (2) absolute height or width depends on viewing distance, unlike the aspect ratio, so judging it needs size constancy; (3) tall bushes are visible from far away, which can change how often they are visited; (4) the slope, ranges and fixed dimensions are provisional ("tweak later" PI, 2026-11-05); (5) no assets use the sets yet.

## Session structure revised (PI, 2026-11-05)

**Decided, not yet built.** The first study's session ladder is replaced (when built) by P (random per-bush reward) and S1 to S7: colour linear, shape peaked, one of two features linear, one of two features peaked, weighted mixture of two, linear-times-Gaussian, and a 2-D Gaussian with a separate centre and width per axis (table in `docs/SCIENCE.md`, "Planned session structure").

**Why:**
- The hypothesis (more features, nonlinearity and interaction make a mapping harder to learn, slower and with a lower ceiling) needs a ladder that adds one thing at a time. The old ladder changed several at once (S1 had two distractors; S3 and S4 mixed a terrain feature with a visual one; S4 to S5 added an interaction and a bump), and a pilot found the two-bump S5 too large a step.
- Moisture as a reward feature was spatially structured and tied to position (regional choices, hidden bushes on terraced terrain, a prior of its own); patch structure and scarcity are better studied in dedicated later experiments, so the first study keeps reward density about uniform and moisture, elevation and ground colour become decoration.
- A practice session with a random reward per bush carries no feature mapping into S1.

**S1 colour, S2 shape:** a peaked mapping is easier to see on shape, whose ends of the spectrum are clear, than on colour, which is a wheel (a peak on a wheel has no ends to compare). Counterbalancing colour against shape across participants is left for later.

**Not decided, left open on purpose:** hints (draft wording per session in the table; they state the class of rule and so change the old principle of never describing the mapping; pilots decide whether to keep them), the matching of reward statistics across sessions (parametric tuning), session durations, the Interlude's trial count for the 2-D sessions and its analysis, the ABAB alternation of feature sets and its counterbalancing.

**Rejected:** keeping moisture as a reward feature in the first study (its spatial structure is a confound for a complexity-and-learnability test; it is kept as machinery for later experiments); two S6-type 2-D sessions as written in the proposal (the second is S7); the two-bump S5 (pilot: too large a step); reporting hints as settled before a pilot.

**What it costs:** a Gaussian with per-axis widths and a product term (C#, `world.py`, mirrors, tests), a random per-bush value for the practice session, "identical" shape and colour as configuration, removing moisture from the Interlude's feature gap, the agents, the human analyses and the battery, redrawn assets and worlds, and about five more minutes of play.

## ABAB feature sets: machinery (2026-11-05)

**What:** two alternating feature sets, `A` (colour `warm_arc`, shape `height_only`) and `B` (colour `cool_arc`, shape `width_only`), in `scripts/feature_sets.py`. A participant has a **start variant** (0 or 1); the practice session (number 0) uses that set and session n uses `LETTERS[(start + n) % 2]`, so S1 already looks different from the practice and every session differs from its neighbours. The variant is a hash of the participant ID (FNV-1a, bit 16, `DesignVariant.ForPid`, mirrored by `feature_sets.variant_for_pid`, pinned by a test), so a participant who returns to an unfinished run gets the same sequence; no ID means A. `-variant A|B`, `?variant=A|B` (development builds only, like `?onlineUrl`) and `GameManager.variantOverride` override it for testing.

**Assets, not runtime overrides:** each (session, set) is an asset, `S1_A`, `S1_B`, with `S1_A_Interlude`, made by `scripts/build_sessions.py` from a template asset by copying it and setting the set's fields (`fruitColorRamp`, the canopy ranges, `fruitSizeFollows`, `fruitSizeSlope`; the Interlude also `interludeFor`). `GameManager.sequenceA` and `sequenceB` hold the two ordered lists and the one for the participant's variant is played; with both empty the old `sessionConfigs` list is played, as before. Which variant a session ran is in its name (`..._A` / `..._B`) and its logged config; **no data column was added** (the server, the session row and the database are unchanged; a server-balanced assignment is left for later).

**Why assets:** the world file, the Interlude file, the results database and the data all key on the asset's name, and a cloned `SessionConfig` would have to touch each of those lookups. The costs: a world file per (session, shape set), about 4 MB each, although only the canopy radius array differs between the two shape sets (the terrain, positions, attributes and per-fruit rewards are the same, from the same seed); sharing the terrain between variants would save most of it and needs the replay and visibility tools to compute the radius from the logged config, so it is not done. The template assets are not played.

**Rejected:** a random start variant per participant (a returning participant could get the other sequence); alternating each channel on its own parity (the two channels change together so a participant always sees one of two complete looks); logging the variant in a new column before the server work.

**Not done:** counterbalancing which feature is relevant in a session; server-side balancing of the two variants (a participant's hash is balanced in the long run, not per recruitment batch).

**Toggle between the two designs (2026-11-05):** `GameManager` has three lists and a `design` setting. `sessionConfigs` is the **default design** (the template assets as they are, no alternation); `sequenceA` and `sequenceB` are the **ABAB design**. `design` (Default or Abab) is the Editor setting; `StreamingAssets/online.json` `"design": "abab"`, `-design abab|default` and `?design=abab|default` (development builds only) override it, in that order of increasing strength. Selecting ABAB with the lists empty logs a warning and plays the default list. `scripts/build_sessions.py <P S1 ... S7> --wire` fills all three lists from the template names in play order (`--wire-only` when the variant assets exist), so adding a session means building its variants and re-wiring. Rejected: one list with a per-session flag (the two designs differ in every asset after the practice, so two lists read more clearly), and choosing the design from the participant ID (the design is a property of the deployment, the variant of the participant).

## New-ladder plumbing: constant features, random bush value, decoration moisture (2026-11-05)

**What:** `SessionConfig.shapeVaries` and `colorVaries` (default true; off gives every bush the middle value 0.5, so identical canopies or one fruit colour; the attribute draws are still made so no other random stream moves), `randomBushValueRange` (a value drawn uniformly per bush from the range and added to the reward function, independent of every attribute; stream 9 of the world seed, drawn only when the range is not (0, 0), so every existing world is unchanged), all read by `world.py` and `interlude.py` and checked in the world file's parameter list (`check_values`; Unity's `FindMismatches` carries the same keys). `world.FIELD_DEFAULTS` gives an older asset file (Unity writes a new field only when the asset is saved) the new fields' defaults.

**Moisture as decoration:** `moisture_matters(params)` is true when the moisture reward weight is not 0. When it is false, moisture is out of `interlude.feature_gap` (`feature_weights`: a channel that does not vary or does not pay has weight 0), out of the ignored-feature check of the designed Interlude, and out of what the simulated agents sense (`agent_moisture`: a constant 0.5, in the world, the Interlude's bush table and the human-agent replay). Sessions where moisture pays (S3 to S5 as they are) are unchanged. The human analyses (`human_analysis.py`, the carry-over scripts) still use the real moisture as a choice regressor: it tests whether the decoration steers choices.

**Interlude with a random reward:** the session's reward function is zero everywhere (the random value is the whole reward), so the Interlude's pairs tie and every trial's correct side is `either`, which the game already handles (`InterludeManager` scores `either` as correct and the practice Interlude awards no bonus). The Random-mode generator no longer redraws tied pairs when the session has a random reward.

**Costs:** `fingerprint.SIM_FIELDS` has the three fields (every environment hash changes; recorded simulator results are stale anyway once the sessions are replaced).

**Not done here:** the terrain configuration (one continuous low-relief setting for every session, an asset setting for the new sessions), the new reward terms for S6 and S7, and the assets.

**Test policy during the new-ladder milestones (PI, 2026-11-05):** `run_tests.py --fast` while building; the full run (`--all`, about 13 minutes: world and Interlude freshness, the fingerprint field check, the simulator, agent, battery and results runs) once at the end, after the last milestone. Checks the slow tests will need to confirm at the end: the fingerprint test (the three new fields were added to `SIM_FIELDS` by hand), the world freshness test (the new fields are written to a world file's parameter list only when they differ from the default, so the committed worlds should be unchanged), and the Interlude freshness tests (P, S1 and S2 Interludes were regenerated after the decoration-moisture change).

## Sessions P, S1, S2 of the new ladder (2026-11-05)

**Built:** `scripts/ladder.py` is the table of the ladder's reward functions and applies it to a template asset and its Interlude (the Unity CLI, an open Editor). P: `randomBushValueRange` (0, 4) and every weight 0 (world seed 200); S1: shape does not vary, colour `Linear` weight 4 (201); S2: colour does not vary, shape `GaussianPeak` weight 4, peak 0.65, width 0.2 (202). Moisture weight 0 everywhere (decoration), terrain as the old P, S1 and S2 (continuous, low relief). New world seeds (200 + the session number) so a participant who played the old sessions meets new worlds. `build_sessions.py` then makes the ABAB variants, generates the worlds and Interludes of the variants and (by default) of the templates themselves, and `--wire` fills `GameManager`'s lists.

**Provisional:** the reward numbers (best bush about 4 per fruit; which end of colour pays more and where the shape peak is are draws, not design), the durations (60, 90, 120 s, the old assets'), the Interlude lengths and modes (practice 3 random trials, S1 and S2 20 hybrid trials, the old assets'), and the instruction texts (the old files; the hint texts in `SCIENCE.md` are drafts). With one varying feature the Interlude's reward gap and feature gap are the same measure (S1 and S2 hybrid trials spread one gap).

**Replaced:** the old P, S1 and S2 assets and their worlds were overwritten; the old S3 to S5 assets and worlds are untouched until milestone 4. Until then the default and the ABAB design both play P, S1 and S2 only.

**Tests under the new ladder (2026-11-05):** the generator tests of `test_interlude.py`, `test_world.py` and `test_feature_flags.py` no longer depend on one session of the ladder: they set `shape_varies` and `color_varies` explicitly (the ladder's S1 and S2 have identical shapes or colours), and a shape-linear reward stands in for the practice session, whose real reward is random and has no designed Interlude (a designed-mode Interlude of a session with no relevant feature is not possible). The participant-replay test skips a run stopped before its first frame (the Editor test plays leave such runs in `ForagingData/`).

## Playtest tweaks to the ABAB sets (PI, 2026-11-05)

After a first playtest of ABAB S1 and S2:
- **`cool_arc` widened** from 120 degrees (215 to 335) to 165 degrees (185 to 350, teal to pink-magenta): the fruit were too hard to tell apart. The smallest 10% step rises from 3.7 to about 4.9; the gap on the hue wheel to `warm_arc` (20 to 140) is 45 and 30 degrees (it was 75 and 45). The protan, deutan and tritan steps stay near 2, 0.2 and 1 (hue-only ramps, see "Hue-arc colour sets").
- **A fixed shape is the set's smallest bush, not the middle of its range.** New `SessionConfig.shapeWhenFixed` and `colorWhenFixed` (default 0.5) give every bush that value when `shapeVaries` or `colorVaries` is off; the shape sets set `shapeWhenFixed` (0 for height-only, 1 for width-only), so S1 (colour varies, shapes identical) shows a 3 x 3 (height-only) or 4 x 4 (width-only) dome instead of a wide 4 x 8. Read by `world.py` and `interlude.py`; in the world file's parameter list only when not 0.5.
- **Height-only is taller and skinnier:** width 3 (was 4) and height 3 to 20 (was 4 to 15); the fruit radius follows the height as before (0.49 to 0.91). Width-only is unchanged (height 4, width 4 to 12).
- **`build_sessions.py` saves the assets before generating** (the generators read them from disk; a field set through the CLI is not on disk until `save_all`, which showed up as a stale world).
- The default design (the template assets and the shared aspect axis) is unchanged.

**Design modes and local quick testing (2026-11-05):** `GameManager.design` is now Default, Abab (ABAB lists, start variant A: the practice session uses set A, S1 set B, S2 set A), Baba (start variant B: S1 set A, S2 set B, to see the other set in each session) or Counterbalanced (the start variant from the participant ID, what a deployment plays); `online.json` `"design"`, `-design default|abab|baba|counterbalanced` and `?design=` (development builds) select the same names. `-variant` still overrides the start variant. **Quick test:** the Editor menu Foraging > Quick test (short sessions) (an EditorPref: per machine, not in the scene, never in a build) or `-quick` on a standalone build makes a practice session 15 s, any other session 30 s and an Interlude play at most its first 5 trials (`GameManager.quick*` fields), on a runtime copy of each session asset (`SessionConfig.QuickCopy`), so no asset changes. Written, compiled, not yet tested by a person.

## Capsule canopies for the ABAB shape sets (PI, 2026-11-05)

**Why:** a stretched ellipsoid sharpens its crown as it gets taller (and flattens it as it gets wider), so a "height-only" or "width-only" set still read as a change of shape, not of size. **What:** `SessionConfig.canopyForm` (Ellipsoid 0, Capsule 1) and `canopyEdgeRadius` (1.5). A capsule canopy is a half-buried cylinder of the canopy's width and height (visible height half the canopy height, as for the ellipsoid) with a top edge rounded by a quarter circle of constant radius: for height-only (width 3) a hemisphere on a cylinder that gets longer, for width-only (height 4) a flat top of growing radius with the same rounded edge. `Tree.cs` builds the mesh from the profile (cached per size, quantized to 0.05, so bushes of one size share a mesh), uses the mesh as the blocker (`MeshCollider` on the canopy, instead of the root capsule collider), places the fruit evenly by area over the top, the rounded edge and the wall, and takes the harvest ring and the visible centre from the visible height. Both shape sets (`shape_sets.py`) set the capsule form; the default design's shared aspect axis stays an ellipsoid. Render only: worlds and Interludes need no regeneration (the radius is half the width as before).

**Known:** `visibility.py` and `perception.py` model every canopy as an ellipsoid, so occlusion of capsule bushes is approximate (a capsule is wider than an ellipsoid of the same size at mid-height); the crown of the rim-light overlay is a 3% enlarged copy of the capsule mesh; written and compiled, not yet looked at in play (the PI tests this pass).

**Capsule canopies: the first version stalled the load and drew inside-out (PI playtest, fixed 2026-11-05).** Three defects: (1) the mesh triangles were wound inwards, so with back-face culling only the far inside of each canopy showed; (2) a `MeshCollider` added to the canopy object, which already has a `MeshFilter`, takes that mesh by itself, so each bush cooked a convex hull of the full canopy mesh (Unity's 256-polygon limit, a hundred "Couldn't create a Convex Mesh" errors and a load of about 20 s); the blocker is now a low-poly convex mesh (12 segments, a few rings, cached per size) on a child object with no `MeshFilter`; (3) the fruit loop's point `t = (attempt + 0.5) / max(count, attempt + 1)` drifts to the ground as attempts grow, so on a long wall every retry of an underground fruit chose the same low spot and ran 5000 attempts; the capsule takes `t` from a golden-ratio sequence with at most 300 attempts. After the fixes the capsule scene runs at the 120 fps cap in the Editor. Unity's built-in capsule primitive was considered: a scaled primitive stretches its hemispheres (the crown would change with the height again) and cannot make the width-only form (a flat top with a rounded edge), so the canopy stays a generated profile mesh.

**Capsule canopies: texture, fruit scatter and the width range (PI playtest, 2026-11-05).**
- **Texture:** the canopy mesh's UVs were scaled by each ring's circumference, which swirls the texture on the dome. They are now the sphere primitive's mapping (u round the bush 0 to 1, v along the outline from the top to the ground 0 to 1), stretched with the bush as the ellipsoid's was.
- **Fruit:** a golden-angle sequence (and a golden-ratio sequence along the profile) shows as a spiral on a long wall. A capsule canopy now scatters its fruit as the ellipsoid's jittered Fibonacci pattern does not on a long surface: points drawn at random by surface area from the bush's own seed, each kept at least 0.8 of the mean spacing from the others (dart throwing; the distance shrinks by 10% every 40 rejections), above the terrain. The ellipsoid's own placement is unchanged.
- **Width-only range:** 2.5 to 8 (was 4 to 12), height fixed at 4; the fixed-shape bush of a session where the shape does not vary is 2.5 x 4. The fruit radius still runs 0.49 to 0.91 across the range. The variant worlds and Interludes of the width-only set were regenerated (the canopy radius changed).

## ABAB is generated and not committed (PI, 2026-11-05)

**Decision:** after playtesting, the PI prefers the default design (the shared aspect axis and plasma ramp on the template sessions) and expects to keep it; the ABAB design stays as code that can be regenerated, and its large generated files are not committed. **What is generated and ignored (`.gitignore`):** the variant session and Interlude assets (`*_A.asset`, `*_B.asset`, `*_A_Interlude.asset`, ...), their world and Interlude files (about 4 MB per world), and `Assets/Resources/AbabSequences.asset`. **What is committed:** the code (`feature_sets.py`, `shape_sets.py`, `build_sessions.py`, `ladder.py`, `DesignVariant.cs`, `AbabSequences.cs`, the capsule canopy form, `fruit_ramp.py`'s arcs) and the default design's templates, worlds and Interludes. **Regenerate with** `./venv/bin/python scripts/build_sessions.py P S1 S2 ... --wire` (an open Editor; add the bases as the ladder grows); `GameManager.design` Abab, Baba or Counterbalanced then plays it.

**The sequence lists moved off the scene:** the ABAB lists are the generated `Resources/AbabSequences` asset (a `ScriptableObject`, loaded with `Resources.Load`, included in a build with the variant assets it references), not fields of `GameManager`, so the committed scene never references an ignored asset; without the asset the ABAB designs are unavailable and `GameManager` logs a warning and plays the default list. The default list (`sessionConfigs`) stays on the scene and `build_sessions.py --wire` still fills it from the templates.

**Archiving later:** if the default design is kept for good, the ABAB code can be moved to an archive branch or folder; nothing else depends on it (the capsule canopy form and the fruit-size rule are `SessionConfig` options that default off).

## ABAB feature sets: the exploration in one place (2026-11-05)

A summary for whoever reads only this; the entries above hold the detail. **Question:** can alternating two complete looks (colour ramp and canopy shape) across sessions keep earlier learning from carrying over? **Path:** (1) the first idea was a different practice look (cube bushes, gray fruit), built and removed the same day when the two-set alternation replaced it; (2) colours: a search for a second ramp found that a hue-only pair (constant lightness, so lightness is never the reward axis) gives steps near 4 to 5 and fails for colour-blind participants, while ramps that also vary in lightness score better but could make lightness a reward cue (hue arcs `warm_arc` 20 to 140 degrees and `cool_arc` 185 to 350 chosen); (3) shapes: aspect-ratio ellipsoids were replaced by height-only and width-only sets after mock-ups, then by a capsule canopy because an ellipsoid's crown sharpens with its height; tussock, lobed and waisted shapes were looked at and not used; (4) machinery: start variants from the participant ID, per-variant assets, Default / Abab / Baba / Counterbalanced designs, a quick-test mode; (5) a playtest of the result: the PI preferred the default design, so the ABAB files are generated on demand and not committed (entry above). **Kept in the repo:** the code and the `SessionConfig` options (`canopyForm`, `canopyEdgeRadius`, `fruitSizeFollows`, `fruitSizeSlope`, `shapeVaries`, `colorVaries`, `shapeWhenFixed`, `colorWhenFixed`, `randomBushValueRange`, which default to the old behaviour), `fruit_ramp.py`'s arcs, and `GameManager`'s design modes. **Not kept:** the variant assets, their worlds and the sequence asset. **If the default design is kept for good**, the ABAB-only code (`feature_sets.py`, `build_sessions.py`' variant steps, `DesignVariant.cs`, `AbabSequences.cs`) can move to an archive branch. See "ABAB feature sets: what was tried" in `docs/SCIENCE.md` for the findings and what reviving it would need.

## Sessions S3, S4, S5 of the new ladder (2026-11-05)

**Built** with `scripts/ladder.py S3 S4 S5 --recreate` (a copy of S2 and S2's Interlude each, then the fields of the ladder table): S3 colour `InvertedLinear` weight 4 with shape varying but not paying (seed 203, 120 s); S4 shape `GaussianPeak` weight 4, peak 0.30, width 0.2, colour varying but not paying (204, 150 s); S5 shape `Linear` 2.4 plus colour `InvertedLinear` 1.6 (205, 180 s). Copying S2 gives them the continuous low-relief terrain (the old S3 and S4 were terraced because moisture paid there; moisture weight is 0 now), the hybrid Interlude and the rest of S2's settings; the durations and instruction files (`SESSION_ONLY`) are the old assets' and the Interlude's own settings stay. **Why this shape:** the plan's contrasts (S1 against S3, S2 against S4) need the same feature and function class with a distractor added, so S3 and S4 repeat S1's and S2's, with the direction (S3) and the peak position (S4) changed so the earlier answer does not carry over; the choice of which feature is relevant, and its counterbalancing, is left to later (PI, 2026-11-05: "we can counterbalance, or run multiple sessions"). **Provisional:** the weights (S5 is 2.4 and 1.6, a 60/40 split; the reward spread across sessions is not matched yet), the durations, the instruction texts. **Not built:** ABAB variants of S3 to S5 (generated on demand), S6 and S7.

**Tests after S3 to S5 were replaced (2026-11-05):** several generator tests (terraced moisture, moisture as a reward feature, extrapolation trade-offs, bumps) had been written against the old S3, S4 and S5. `scripts/legacy_sessions.py` keeps those assets (`scripts/fixtures/legacy_S3.asset` to `legacy_S5.asset`, from git commit d6f3576) and `legacy(name)` gives the overrides that make the S2 template behave like them, so the tests still exercise those generator paths without depending on the shipped sessions.

## Sessions S6 and S7, and the two new reward terms (2026-11-05)

**Reward terms:** (1) `RewardBump.widthColor`: the Gaussian's spread along colour, 0 meaning the same as `width` (a round bump), so the S7 bump has its own spread on each axis (`width` is along shape) and every existing asset behaves as before; (2) `RewardProduct` (a list `products` on the reward function): `height * f(linear feature) * exp(-(g - center)^2 / (2 * width^2))` with `f(x) = x` or `1 - x` and the Gaussian on the other feature. Python mirrors in `world.bush_value`; `check_values` and Unity's `FindMismatches` carry the new fields (a product's, and a bump's colour spread when not 0, are written to the world file only when present, so earlier worlds stay identical, and a config that has them against a file without them is stale). `interlude.relevant_features` counts a product like a bump (both features relevant) and designed-mode Interludes are refused for either (their contrasts assume additive terms).
**Values:** S6 shape up times a colour peak at 0.6 (width 0.25), height 4 (seed 206); S7 a 2-D Gaussian at (shape 0.30, colour 0.70), spreads (0.25, 0.15), height 4 (207). Provisional like the others: the reward spread across sessions is not matched, and S6's best bush needs shape 1 and colour 0.6, so the optimum is at the edge of the shape range; the share of bushes above half the best is 16% for S7 (the old S5's bump had about 17%, found by trial and error in the pilots). The Interlude stays hybrid (20 trials, 2 repeats); whether 20 trials recover an interaction is the later Interlude analysis.
**Not done:** the carry-over scripts (`prior_carryover.py`, `carryover_decay.py`) summarise a session's rules as a count of bumps and do not know products; the agents' critics were not changed (an additive critic cannot represent either interaction; the joint-kernel GP can).

## Terraced terrain with less relief for every session, and new durations (PI, 2026-11-05)

**Terrain:** `ladder.py` `TERRAIN` sets on every template session and its Interlude: `moistureTerraceLevels` 4, `moistureTerraceSharpness` 0.3, `moistureTerraceResidual` 0.1, `terrainNoiseFrequency` 2, `terrainMaxElevation` 6 (the old terraced sessions: 12). Moisture pays in no session, so the terraces are decoration (plateaus of four ground colours and heights). The value 6 is a first guess at "less" and is one number in `TERRAIN`. Positions and attributes of the bushes do not depend on moisture, so a regenerated world differs in its terrain grids, the bushes' moisture and elevation and the Interludes' placements. The generated ABAB variants carry the old terrain until rebuilt (`build_sessions.py`). **Durations:** practice 30 s, S1 and S2 90 s, S3 and S4 120 s, S5 to S7 180 s.

## Spatial evenness of the reward: tile balancing and swaps (PI, 2026-11-05)

**Request:** make harvesting even over the map at several spatial scales (a lucky participant should not find and exhaust a rich cluster), as dedicated methods that can be turned on or off per experiment; compare the improvement over a random draw and over simply choosing a new seed; no simulated foragers in the metric ("too many independent variables"); a mild amount of randomness is wanted and inevitable.
**Built:** `scripts/spatial.py` (metrics, `tile_assignment`, `optimise`, `balance`), `SessionConfig.spatialBalance` (Off 0, Tiles 1, TilesAndSwaps 2; Off by default, in `ladder.py` as `SPATIAL_BALANCE` for every session), the world generator's use of it (stream 10 of the world seed; `world.py` draws the practice session's random value before the balance step so the stream is unchanged when it is off), `spatial_report.py`. The world file's parameter list carries `spatialBalance` only when not 0, so existing worlds are byte-identical; Unity's staleness check treats a missing name as Off.
**Method:** the records are dealt to other positions, so the marginal distribution of shape, colour, the random value and the reward are exactly the independent draw's. Tiles: hierarchical stratified dealing over tiles of 240, 120 and 60 units (the sorted values dealt by stride scheduling with random starting phases, random order within the finest tile), so each tile has an even mix of reward quantiles at every scale. Swaps: random pairs of bushes exchange records when the cost falls, until the target 0.3. **Cost:** the mean over scales and two channels (the reward and its top-decile indicator) of the squared ratio of the disk-mean spread to its random-assignment null (1 for a random world), tracked incrementally with the disks each bush is in. **Why records and not values:** the reward function and the attribute draws stay what they are, and the shape's canopy radius moves with the record.
**Measured** (20 seeds, practice, S2, S5, S7): cost as drawn 1.02 to 1.08; best of 5 random seeds 0.86 to 0.89; tiles 0.55 to 0.57; tiles and swaps 0.30; largest top-decile cluster 4.3 to 5.0 bushes as drawn, 2.8 with tiles, 2.1 to 2.3 with swaps. A seed search is a small part of the gain.
**Limits:** it needs a reward that does not depend on moisture (the moisture stays with the position; `generate_world` refuses otherwise); the 0.3 target and the scales are module constants (`SWAP_STEPS`, `TARGET`, `SCALES`), not config; the metric does not look at the terrain's visibility (hidden bushes) or at the lattice spacing beyond the cluster link; no worlds were regenerated with it on, so every committed world is still the independent draw.

**Spatial balance turned on for the ladder, with finer scales (PI, 2026-11-05).** `SPATIAL_BALANCE` in `ladder.py` is TilesAndSwaps and every session's world and Interlude was regenerated. The PI's reasoning: the large tiles and radii average out on their own, so the scales matter at the foraging scale. Measured on S2 (8 seeds): the spread of disk means in units of the bushes' own spread is 0.69, 0.56, 0.44, 0.31 and 0.15 at 30, 45, 60, 120 and 240 units for a random world, so patchiness a participant meets is at the scale of a few neighbouring bushes. Optimising at 60, 120 and 240 left 0.61 at 30 units; **the scales are now 40, 60 and 120** (disks of at least 2 bushes below 60 units) and the swap target 0.4, giving about 0.56, 0.40, 0.21 and 0.09 at 30, 45, 60 and 120 units and a largest top-decile cluster of 1.8 to 2.0 (random: 4.3 to 5.0). Choosing the best of 5 seeds gives cost 0.91 to 0.94 against 0.40. **The cost of fine scales:** neighbouring bushes become negatively correlated (Moran's I at 15 and 22 units about -0.2 for tiles, -0.4 at target 0.4, -0.6 at target 0.3, against 0 for a random world), a regularity that stronger targets make more visible; the target is the knob (`spatial.TARGET`). Each regenerated world's per-scale numbers are reproduced by `spatial_report.py`; the earlier numbers at scales 60, 120 and 240 are superseded.

## ABAB archived; adversarial review clean-up (PI, 2026-11-06)

**ABAB archived.** After playtesting the PI kept the default design, so the alternating feature-set code left the project: `feature_sets.py`, `shape_sets.py`, `build_sessions.py`, their tests, `DesignVariant.cs` and `AbabSequences.cs` moved to `archive/abab/`; the capsule canopy (`Tree.cs`), `CanopyForm`, `FruitSizeFollows`, `GameManager`'s design toggle, `OnlineSettings` `-design`/`?design=`, the `fruit_ramp.py` hue arcs and the generated variant assets were removed (`archive/abab/removal.patch` reverses the edits). The earlier ABAB entries above stay as the record of why. The worlds do not change (no ABAB field was in a `check_values` key). The default design's world generation is `ladder.py`, `world.py --unity`, `interlude.py` (no `build_sessions.py`).

**The sensor does not read the reward (red-team RT-5).** `agent_moisture` made simulated agents sense a constant moisture when moisture was decoration, which read the hidden reward function in the percept and spared agents a distractor participants see. Removed: agents sense the terrain's moisture in every session (the ladder's critics must learn that it pays nothing, as participants do). The Interlude designer still uses `moisture_matters` (it knows the reward); the Interlude sidecar no longer has a `moistureMatters` key (the Interludes were regenerated). Agent results recorded before this are not comparable (the engine and agents hashes moved).

**Colour constraint relaxed.** Plasma is the default ramp; its orange-to-magenta range includes red hues and its smallest 10% step is 2.6 for the worst vision type. The "no red" and "no green" constraints left CLAUDE.md and `test_fruit_ramp.py` (the step check now needs more than 2.5).

**Review fixes.** `spatial.py` joined `ENGINE_FILES` (balanced worlds depend on it); `human_agents.session_params` takes the logged reward function (pilot S3 to S5 were replayed with another session's); `prior_carryover.py` skips participant sessions whose logged world differs from the current asset of the same name. **Deferred (PI):** the pilot sessions' names (P, S1 to S5) mean other sessions now; rename when the experiment/session structure is introduced, then key sessions by name and world hash (`human_curves.py` pools by name).

## Experiments: a run per (participant, experiment) (PI, 2026-11-06; server side, milestone 1)

**Why:** the game is becoming experiment-centric. A participant logs in once (Prolific ID or name, one signature), sees a menu of experiments (Tutorial, Complex Features, later others), each a progression of sessions with its own rules, and may leave and continue. Experiment titles change from time to time, so a title is data (`experiments.title`) and the code (`TUT`, `CF`, the asset prefix) is the key.

**Decisions:** (1) **One run per (participant, experiment)** (`runs` unique on the pair), not one run per participant with experiment-tagged sessions: a run keeps contiguous session indices 0..n-1, its token, its resume of the latest session and its finish check, so `append`, `resume_state`, `pull`, `replay` and `human_data` work per run unchanged. The rejected alternative (sessions carry an experiment and an experiment-local index inside one run) would have changed the contiguity rule, resume, finish and every reader. (2) **A participant token** from `participant-start` authorizes the menu and starting runs, and feedback for the participant's own runs (so a finished experiment's Completed screen can show its code and take or replace feedback); a run token still authorizes uploads. Logging in with a known ID issues a fresh participant token, as returning with an ID always issued a fresh run token (so anyone who knows an ID can log in as that participant; Prolific IDs are 24 random characters, typed IDs are for testing). (3) **Consent once per participant and consent version**, at login; the server answers `needs_consent` for an ID with none of the client's version on file and creates nothing until the signature arrives. (4) **Prerequisites are enforced by the server** (`experiments.requires`, checked when a run is created; the menu's `unlocked` only shows it). (5) **Completion codes per experiment** in the `experiments` table (not an environment variable per experiment); a finished experiment is not rerun but `run-start` returns its code. Payout settings are stored per experiment (`payout`, not read by the server) and decided later. (6) **A build offers experiments** (`release_experiments`: code and session count), replacing `releases.n_sessions`. Never change an experiment's session list while a participant is mid-run (a run keeps the count of its first build).

**Migration:** existing (debugging) runs become the experiment `legacy`, one participant each, so nothing is lost; `test_server.py` applies the migration to a database holding old rows. **Not deployed** (the PI deploys). **Next:** the client (ExperimentConfig assets, the naming scheme with experiment prefixes, the menu and login screens, DataPipeline per run, per-experiment downloads).

## Experiment assets and the naming scheme (PI, 2026-11-06; milestone 2)

**Names:** every session asset starts with its experiment's code: `TUT_S1` and its Interlude `TUT_I1` (the Tutorial: the old practice session P, random reward, seed 200), and `CF_S1` to `CF_S7` with `CF_I1` to `CF_I7` (Complex Features, the old S1 to S7, seeds 201 to 207). `CF` stands for the experiment's title and can be changed with it (the title is data: `ExperimentConfig.title`, `experiments.title`); the code is the key (asset prefix, folder, database). The experiment's code is read from the asset name (`SessionConfig.ExperimentCode`, `world.experiment_of`): the part before the first underscore, so there is no field to keep in step with the folder. Interludes are `<code>_I<n>`, found from their session by `interludeFor` and by `world.interlude_name`.

**Where things live:** `Assets/ScriptableObjects/Experiments/<code>/` holds `<code>.asset` (`ExperimentConfig`: code, title, `requires`, the ordered session list, `downloadPerSession`) and the session and Interlude assets; `Assets/StreamingAssets/Experiments/<code>/` holds everything the experiment downloads: its instruction texts, worlds and Interlude files (so a per-experiment manifest is a folder listing, milestone 5). `instructionsFile` is now a path under StreamingAssets (`Experiments/CF/instructions_S3.txt`); `consent.txt` and `instructions_resume.txt` stay at the root. The generators and tools follow the layout (`world.unity_world_path`, `replay.find_world_file`, `server_admin register-worlds` and `archive_worlds`, `ladder.py`, `run_tests.py`).

**`GameManager` plays an experiment:** its session list is the experiment's (`GameManager.ActiveExperiment`, set by `BeginExperiment`, which the menu will call), falling back to the `defaultExperiment` field of the scene's GameManager (Complex Features) when the game starts from the scene without a menu. The old `sessionConfigs` list is gone. The "session N of M" numbers already counted over the active list, so they are per experiment now.

**The old names still work** in Python (`world.LEGACY_NAMES`: `P`, `S1` to `S7` and their `_Interlude`s map to the new names) because the tests, the agent battery and the results database call sessions by them; they mean the current sessions, which they already did after the ladder replaced the old ones. Not renamed: the pilot data (logged names are the old ones).

**Done by a headless Editor run** (`unity run` with a temporary editor script, deleted afterwards): `AssetDatabase.MoveAsset` renamed and moved the assets (GUIDs kept, so the scene and the other references survived), and the script set `interludeFor` and `instructionsFile` and made the two `ExperimentConfig` assets and the scene's `defaultExperiment`. All worlds and Interludes were regenerated (their content did not change except where the generators changed). **Renaming a code later** is the same operation by hand: rename the assets and the folders, fix `interludeFor` and `instructionsFile`, regenerate or rename the generated files, and update the database rows (`experiments.code` and the runs' `experiment`); never while a participant is mid-experiment, and past data keeps the old names.

## The experiment menu and login (PI, 2026-11-06; milestone 3, with the client half of milestone 4)

**Built (compiled headless, not played):** `Bootstrap` (the Boot scene, which is the menu: no new scene), `ConsentScreen` split into an ID screen and a consent screen (the agree checkbox is gone: the typed signature is the agreement; a returning participant is not asked again), `MenuScreen`, `ParticipantSession` (login, run-start and feedback calls, the standings), `ExperimentCatalog` (`Resources/ExperimentCatalog.asset`: TUT then CF), the Editor's `Foraging > Experiments` window (`ExperimentPlayer`). `DataPipeline` no longer starts a run itself: it adopts `ParticipantSession.PendingRun`, which the menu got from `run-start` (with the resume state for Continue, handled as before), and at the end of an experiment shows the completion screen (code, feedback, "Back to the menu", and "Return to Prolific" when the address carries a Prolific ID) whose menu button calls `DataPipeline.ReturnToMenu` (destroys the pipeline and resets its statics, then loads Boot). `GameManager.BeginExperiment` resets the session list, index and totals.

**Choices:** (1) The menu is part of the Boot scene, not a scene of its own: one scene already does the preload, the login and the click-to-begin, and the statics (`ParticipantSession`) survive the reloads. (2) After choosing an experiment a browser still shows "Click anywhere to begin" (the pointer lock and audio need the click, and the menu's own click is consumed by the button). (3) The Editor and lab builds with no server offer every experiment, unlocked; `-pid` on a lab build's command line skips the ID screen and asks for no consent, as before. (4) A finished experiment's completion screen can take or replace feedback with the participant token (no run token exists in the menu). (5) A refresh of the menu is a new login (a fresh participant token each time), so a second tab logging in as the same ID makes the first tab's menu calls fail with a message to reload.

**Not built:** per-experiment downloads (milestone 5: the browser still preloads all of StreamingAssets before the login), a scroll for more than six experiments, progress for a Continue beyond "n of N parts", `rename_experiment.py`. **To verify by playing:** login and consent in a browser build with the server, Continue after quitting mid-session, the prerequisite lock, the completion screen and its feedback, the Editor window.

## Session preview in the Editor (PI, 2026-11-06)

**Why:** the game scene builds its world at Start, so the Scene and Game views were empty before Play. `Assets/Editor/SessionPreview.cs` builds the last non-Interlude session of the GameManager's `defaultExperiment` (CF_S7, the richest world, for Complex Features; TUT_S1 for the Tutorial) in edit mode with the game's own components: a `TerrainManager` on a new ground object for the terrain (the session's mountain colours are applied to a copy of the material, because `TerrainManager.Start` would instantiate one, which edit mode reports as an error) and the bush prefab with `Tree.Awake` and `ApplyAttributes` for the 700 bushes. Everything is under one root marked `DontSaveInEditor | DontSaveInBuild`, so it is never written to the scene, and it is cleared when Play starts (the game builds its own world). An `EditorApplication.update` check, once a second, builds it when it is missing (the Editor or scene just opened, a recompile, the end of Play) and rebuilds it when `defaultExperiment` changes (`Foraging > Preview on scene open`, on by default; the menu items also build and clear it by hand). The first version relied on `sceneOpened`, which does not fire for the scene the Editor opens at start, and showed CF_S7 whatever the default was. Checked in the Editor: 700 bushes, no console errors, the Game view shows the session (terrain, fog, bushes with fruit).

**Touched runtime code:** `Tree.cs` calls `Discard` where it called `Destroy` (six places): `Destroy` is an error in edit mode, `DestroyImmediate` is not; the behaviour in play mode is unchanged. **Not verified:** the Scene view framing of the menu command (a capture of the Scene view showed the view unchanged); the preview on a very slow scene open (700 bushes build in a few seconds).

**Fix (same day): the preview left copies behind.** `SessionPreview.Clear` found its root with `FindObjectsByType`, which skips objects that are not saved, so it never removed anything: every rebuild (scene open, a change of `defaultExperiment`, the end of Play) added another copy of the world, the copies were still there during Play (extra bushes, non-interactive) and, once a domain reload had lost the materials made in edit mode, they showed pink. `Clear` now takes the roots from the loaded scenes. The preview is also cleared before a recompile, before the scene is saved and when the Editor quits, so no stale copy survives either. Checked in the Editor: three builds in a row leave one root, Play has none, and after Play one fresh root is rebuilt; no console errors. If objects built in edit mode ever cause trouble again, drop the preview (delete `Assets/Editor/SessionPreview.cs`; `Tree.cs`'s `Discard` can stay).

## Light fog in the ladder's sessions (PI, 2026-11-06)

**What:** fog was off in every session (a Decisions entry above: the scene's 80 to 120 fog hid every bush beyond 120 units, which acts as a view limit). The ladder's sessions and Interludes now have light linear fog: `SessionConfig.fogEnabled` on, `fogStartDistance` 100 and `fogEndDistance` 300 (new fields; `scripts/ladder.py` `FOG`; `GameManager` sets `RenderSettings.fogMode`, start and end from the session). Nothing nearer than 100 units is touched; at 200 units a bush is half fogged; the colour is the scene's fog colour (grey), the mountains take `mountainFogStrength` (0.3) of it. **Why:** far bushes are hard to make out anyway and the fog hides how far away the unreadable ones are, while the preview (which uses the scene's settings) already looked fogged. The PI tunes the distances by hand in the Inspector (the three fields on any session asset); `SessionPreview` follows an Inspector edit of the active experiment's session within a second (it applies the session's fog to the scene's render settings, which the next save keeps).

**Watch:** fog changes what a participant can see at a distance, so pilot data without fog is not directly comparable; the simulator's sensor (`ConePercept` distance) does not model fog (a known gap, `visibility.py` neither), so its distance should be chosen to match the fog once the level is settled. The assets were set with the CLI (only the three fog fields, so Inspector tweaks stay); a future `ladder.py` run sets them with everything else.

**Fog level chosen (PI, 2026-11-06):** after trying the first values (100 to 300) by hand the PI settled on `fogStartDistance` 50, `fogEndDistance` 200 and `mountainFogStrength` 0.15, set on all 16 session and Interlude assets (CLI, only those fields) and in `ladder.py`'s `FOG` (the new fields' defaults are 50 and 200 too). Everything said above about comparability and the simulator's sensor not modelling fog stands, with a closer fog: bushes are half fogged at 125 units.

## A little more light (PI, 2026-11-06)

**What:** the fog dulled the arena, so two new `SessionConfig` knobs brighten it: `sunIntensityScale` (multiplies the sun's intensity curve at every elevation; 1.2) and `postExposureOffset` (stops added to the post-exposure curve at every elevation; +0.3 EV). Both default to "no change" (1 and 0) and are set on the 16 ladder assets (CLI, only those fields) and in `ladder.py`'s `LIGHT`; `SunController.EvaluateLighting` applies them. **Why two:** the sun's intensity acts on the canopy and fruit highlights only (the terrain and fruit shaders ignore it, see "What responds to the sun" in CLAUDE.md), so raising it alone would leave the ground, most of the arena, as dull as before; post-exposure brightens everything on screen, and the fruit undo it (`fruitExposureCompensation` 1), so fruit luminance, a data channel, does not change. The values are a first guess for the PI to tune by hand; the Editor preview cannot show them (the sun runs in play mode only). **Watch:** brighter canopies and ground change the contrast the fruit are seen against, though not the fruit; pilot data from before the fog and the light is not directly comparable.

## Per-experiment downloads (PI, 2026-11-06; milestone 5)

**What:** a browser no longer preloads all of StreamingAssets before the login. `streaming_files.txt` (written by `BuildInfoWriter` before each build) lists only the common files (everything outside `Experiments/`: consent, online.json, build_info, the resume text); the files of an experiment are fetched when the participant chooses it (`StreamingData.Fetch`, with a "Loading <title>... n%" screen in `Bootstrap.Begin`). Which files: `ExperimentConfig.FilesOf(session)` (the session's world, its Interlude file and its instruction text, computed from the assets themselves, so there is no per-experiment manifest to keep in step) and `FilesToStart()` (every session's, or with `downloadPerSession` the first session's only). With `downloadPerSession` the game fetches the next session's files while the current one runs (`GameManager.FetchNextSession`, called from `Awake`); the end screen waits ("Loading the next part...", `NextSessionReady`) rather than load a session whose files are not there, and retries a failed fetch. Desktop and the Editor read the files where they are (nothing is fetched).

**Why this and not per-experiment manifest files:** the session assets already name every file (`WorldData.PathFor`, `InterludePathFor`, `InstructionsFile`), so the list is derived where it is used; a manifest would be a second copy that can go stale. **Checked:** all 40 files the two experiments name exist. **Not verified:** a real browser download (the old `streaming_files.txt` in the working tree is stale until the next build rewrites it); `downloadPerSession` is off in both experiments, so the per-session path has not run. The download size: before this the browser loaded all 32 MB before the login; now the common files (a few KB) first, then one experiment's.

## Analysis tooling and experiments (PI, 2026-11-06; milestone 6)

**Done:** `human_data.py` reads the new schema (the participant through `participant_id`, the signature through the participant's consent, the run's `experiment` and `participant_id`) and writes them: `participants` gains `participant_id` and `experiment` and `sessions` gains `experiment` (columns added at the end; an old `humans.sqlite` gets them by `ALTER TABLE` and the rows fill when downloaded again, `download --all`); `run.json` carries both (`server_admin pull` and `download` write the run row). A session's `block` is now its own name (`CF_S1`), taken from `interludeFor` for an Interlude (`CF_I1` shares `CF_S1`'s block), with the names before experiments (`S1`, `S1_Interlude`) still paired the old way. `human_curves.py` groups by `block` and kind instead of by name, so sessions of different experiments are never pooled; its default sessions are `CF_S1` to `CF_S7`. `server_admin runs` prints the experiment. These need the migration deployed (the queries use `participant_id` and `experiment`); until then `human_data download` fails against the old schema.

**Not ported (the pilot analyses):** `idle_analysis.py` (and `human_gap.py`, `prior_carryover.py`, `carryover_decay.py`, `human_analysis.py`, which import its `MAIN`) still key on the names before experiments (`P`, `S1` to `S5`) and on one run per participant. They were written for the old six-session pilot, whose worlds no longer exist under those names (the worlds are skipped with a warning); porting them is a design of its own (seven sessions, two features, bumps and products, one run per experiment) and waits until there is data from the new ladder. `human_agents` and `replay` work for either naming, since they load the logged session name.

## First browser test of the experiments, checked in the database (2026-11-06)

One participant (peter1) played the Tutorial (TUT, 2 sessions) and Complex Features (CF, 14 sessions, short `?quick=1` lengths) on the development build of `f11e958`. **Checked:** both runs `finished`, build `f11e958` clean, no duplicate runs or participants; every session present, contiguous (event count equals the largest sequence number + 1 in all 16), one `session_end` each, the trajectory ends where the session ends, the final score equals the sum of the fruit rewards and the last running total in all 8 non-Interlude sessions, every world and Interlude hash registered; the 38 Interlude trials have no missing choice or response time (2 timed out); consent was stored once for the participant; and `scripts/replay.py` reproduces every logged harvest of all 16 sessions from the downloaded trajectories. The legacy data (7 runs, 4 finished and 3 in progress, under experiment `legacy`) is intact. **Fixed:** `server_admin.archive_worlds` looked for worlds only in the experiment folders, so downloading the legacy runs warned; it now also tries the flat `Worlds/` folder of the builds before experiments.

## Totals and points in the menu (PI, 2026-11-06)

**What:** (1) The last session's end screen is an ordinary one (its own points, "Press Enter to continue"); the totals are on the experiment's completion screen (`DataPipeline.ShowComplete`: "Points earned: N", then the completion code), not on the last Interlude screen. (2) `ExperimentConfig.countsTowardTotal` (off for the Tutorial): the completion screen shows no total for such an experiment and the menu leaves it out of the total; practice sessions and practice Interludes were already out of `GameManager.SessionScoreTotal` and `InterludeBonus` (they pay nothing), so the Tutorial adds nothing to either. (3) The menu has a Points column (a dash for a practice experiment) and a Total under it. The points come from the server: `server.menu` returns `points` per experiment, the score of its completed non-practice sessions plus the bonus of the trials of its completed non-practice Interludes, the same sum the game shows (new migration `20261107000000_menu_points.sql`, `ExperimentStanding.points`). **Not deployed:** the migration is written and tested locally (32 server tests, one on the points); the live server answers without `points` (the menu shows 0) until it is applied and the build is redeployed.

## Typography and music (PI, 2026-11-06)

**Font:** pair 4 of the candidates (a published comparison): **Nunito ExtraBold** for titles (size 54 and up) and **Nunito Sans** for everything else, **Nunito Sans Bold** for bold runs (HUD readouts, `<b>`; the weight table of the Nunito Sans asset points Bold at the bold asset). The three TTFs are static instances (`wght` 800, 400 and 700) cut with fontTools' `instancer` from the variable fonts in google/fonts, with their OFL licences, in `Assets/Fonts/`; the TextMeshPro font assets (dynamic atlases, 110 characters drawn in advance) are in `Resources/Fonts/`; `UiStyle` chooses by size and the scene's eight text objects were set the same way. Inter stays as the fallback asset. **Music:** synthesized in code (no licences; the CC0 candidates found for the menu loop and the jingle were not quite right and could not be listened to from here), three files in `Resources/Audio/` (`menu_loop` 32 s slow chord pads, `score_cue` a soft felt-piano arpeggio, `score_loop` 20 s quieter pad; no isolated tones, per the PI) played by `UI/Music.cs`: the menu loop from the Boot scene until an experiment starts, the arpeggio and then the score loop at the start of every score screen (sessions, Interludes, the completion screen), nothing during a session. Volume `SessionConfig.musicVolume` (0.3), fades 1.5 s. The generator is not in the repo (the WAVs are the product); regenerate by the same recipe if the loops change. **Not done yet:** the menu's 3D backdrop and the score-screen camera drift, and the wider layout restyle (spacing, alignment, hierarchy of the study's screens).

**Preview fix (2026-11-06, found while taking the mockup backdrop):** the Editor's session preview still turned magenta after a Play. An object marked not-saved survives a scene reload as a scene-less copy that still renders, with the materials the game's code made at runtime unloaded; `Clear` looked only in the loaded scenes, so these copies piled up (and `GameObject.Find` could return one). `Clear` now finds every root in memory (`Resources.FindObjectsOfTypeAll`), the presence check looks at the open scene's own root, the preview's runtime materials and meshes are marked DontSave, and an unhealthy preview (the first bush has lost its material) is rebuilt. Checked: two Play and Stop cycles leave one root and the bushes render with their materials.

## The study screens restyled (PI, 2026-11-06)

**Built from the approved mockups** (a published page, ten screens): `UiStyle` has the shared tokens (Title 72 and Heading 44 in Nunito ExtraBold, Body 38 and Small 28 in Nunito Sans, a spaced accent eyebrow), a generated nine-sliced **rounded sprite** and helpers over it (`Rounded`, `Place` for positions in reference pixels from the centre, `Pill` buttons 88 high, `Eyebrow`, `Backdrop`); one dark-glass panel (radius 28). New or rebuilt screens: `StatusScreen` (Boot: loading with a progress bar, connecting, click to begin, errors), the ID and consent screens, `MenuScreen` (status pills, a progress bar for an experiment under way, the Points column and the total), `CompletionScreen` (title, points, code, feedback, back to the menu and Prolific; replaces `FeedbackScreen`), `InstructionsScreen` and `ScoreScreen` in the game scene, and the HUD (the clock in an upper-left pill, the score in an upper-right pill, numbers only). The scene's own instruction panel, end-of-part panel and their texts are no longer used and stay hidden (the scene was not rewired).

**Parts, not sessions and Interludes:** the study's screens say "Part N of M" with N the position in the experiment's list (`GameManager.PartNumber`, `PartCount`); a session's central instruction is "Find the best fruit", an Interlude's "Choose the best fruit". The instruction files now start with that title line (the old `<b>Session {session} of {total}</b>` line is gone; `{part}` and `{total}` still work in the text) and end with their `Press [Enter] ...` prompt, which the screen shows as a pill; "Interlude complete" and "Choices complete" are gone. The score screen shows the points with no plus sign, in a panel. **Menu backdrop:** a pre-rendered frame of the world (`Resources/Backdrops/menu.jpg`, 215 KB) with a very slow zoom and sway, not a live render of a world in the Boot scene: that would need the terrain, bush prefab, lighting and fog in the Boot scene and a 2 to 4 MB world file in the browser's first download, for no change in how it looks. The score screens do have the real world behind them, with the camera turning at 3.5 degrees a second (`ScoreScreen`). Checked in the Editor with captures of each screen and a short quick-test session (instructions, HUD, score screen), no console errors; **not played in a browser**.

**Fixes after the first browser test (PI, 2026-11-06):** (1) the **prompt is the last line of the box** ("Press Enter to begin", "Click anywhere to begin"), under a rule, on the instruction, score and status screens, with the key in a chip (`UiStyle.Chips`: `[Key]` in any text); the loose pill at the bottom overlapped the Tutorial's controls reminder. (2) Those bottom hints, "Hold Space to harvest" and the controls reminder, are `HintPill`s (a rounded pill as wide as its text, keys as chips) at 140 and 44 pixels from the bottom, so they cannot sit under one another. (3) Instruction boxes are 1380 wide with 36 pixel text so a longer line does not wrap. (4) The completion code shrinks to fit its box. (5) **Music volume halved**, 0.15 on all 16 session assets and as the default. (6) **The backdrop is a still image shared by the Boot scene's screens** (one `BootBackdrop` canvas made once, below them): the jitter between screens was each screen building its own copy of a slowly moving picture, which started from rest, so the "slow zoom and sway" of the first version is gone (`BackdropDrift` deleted).


**After the second browser test (PI, 2026-11-06):** (1) The Boot scene's shared backdrop was empty: `BootBackdrop` set its "exists" flag before `Backdrop` ran, which then returned early (only the game scene's score screen, which builds its own, showed the picture); it builds first now. (2) **Palette kept** (blue slate; six alternatives were mocked up and none chosen). (3) Menu rows: a finished experiment is a full green bar and one under way a partial blue bar, with no "Completed" / "x of y parts done" caption; the pill stays only for not-started and locked rows (it carries the part count or the prerequisite). (4) The begin prompt is "Click to begin". (5) "View code" hides the "Connecting" status box before the translucent completion screen. (6) The welcome-back text lost its line about a harvest or choice starting again. (7) **The instruction box is wide (1640 px) and centred** with left-aligned text, instead of a left-hand panel with the world visible to its right (easier to read than a narrow centred one, consistent with the other centred boxes).

**Third browser test (PI, 2026-11-06):** the menu has no title, "Points" header or "signed in" line (the rows and the total say it); the login screen is "Welcome" (eyebrow) over "Foraging study" with "Enter your name/ID to continue" and no privacy note; the consent text is a one-line placeholder; the first-harvest message is a smaller centred notice box (`InstructionsScreen.Show(..., notice: true)`, no part number); the welcome-back text is two lines. **Stray highlight after a click and Enter:** not reproduced in the Editor; the page's canvas has no focus outline, tap highlight or text selection (`patch_webgl_page.py`), and a `UiStyle.Pill` button drops its selection after a click and has no keyboard navigation, so a later Enter cannot press it again. If it persists in a browser, look at which element is highlighted.

## Review of the experiments work (PI, 2026-11-06)

Adversarial review of everything since `8b25ee0` in the server, the experiment flow and the data tools (red-team and simplifier; full test run 556 passed). **Server (a new migration, `20261108000000_finish_run_checks.sql`; the two earlier ones are applied to production and stay as they are, so the simplifier's proposal to fold the points migration into the experiments one was refused):** (1) `finish_run` returns the **completion code only for a run the database confirms finished** (it used to return it with the problems, so a scripted call with nothing played got the real code), (2) a run whose build no longer lists the experiment is a problem, not a skipped check (it used to be marked finished at any session count, unlocking the next experiment), (3) the points of a run are defined once (`server.run_points`), used by the menu and returned by `finish_run`, and the completion screen shows the server's number instead of the client adding scores up (the client's running totals, `RestoreTotals` and the Interlude bonus static are gone; an offline run shows no points). **Admin:** `register-release --experiment CODE` reads the session count from the experiment asset at the commit (a mistyped count used to leave an experiment unfinishable and its successor locked), the release rows are replaced in one transaction, and `register-experiment` refuses a prerequisite that is not registered. **Client:** a browser build without `consent.txt` fails with a message instead of skipping consent; an experiment played directly (the Editor window, `-experiment`) ends in the menu and does not restart; `downloadPerSession` and the next-session prefetch are removed (never used by either experiment, never exercised; an experiment's files are downloaded when it is chosen); the session-numbering helpers that `{part}` made dead are gone. **Kept on purpose:** `experiments.payout` (payout ratios are decided per experiment, the column waits for them), the second `unknown_build` check in `start_run` (the error label is part of the tests; changing it needs a second copy of that large function). **Deferred:** `Refresh` answering `needs_consent` keeps the old standings silently (only reachable by deleting consent rows by hand); the session-count mismatch when a resume runs on a build with a different session count is not checked (a build is never changed mid-experiment, see the experiments entry); the human data download stamps every run with the participant's latest consent version (one consent text so far); `humans.sqlite` from before the experiments must be deleted and downloaded again (`_add_missing_columns` was removed).

## Experiments split by question (2026-11-06)

**What was decided (PI, with a design discussion; nothing built).** The single Complex Features ladder (CF_S1 to CF_S7) is to be split, and
extended, into experiments that each vary one family of things; the designs are in `docs/EXPERIMENTS.md`, the summary in `docs/SCIENCE.md`
("Planned experiments"). **Why:** the ladder changes the number of rewarded features, the nonlinearity and the interaction together (S5 goes back
to linear after S4's peaks, S6 adds nonlinearity and interaction at once), and duration, order and practice grow with the session number, so a
difference between two sessions cannot be assigned to one cause; each cell was also a single world with a single draw of weights and centres,
so one participant's S5 curve is one noisy sample. **Repeats:** a session is an instance from a pool (new seed, features, directions,
positions, weights), several per cell, so a per-participant per-condition estimate exists and the instance index is a regressor (practice at the
class is a result, not a confound). The order is an ease-in of the simplest cases, then intermixed in random order, so a participant cannot
assume the next session is harder (for example that three visible features mean three paying ones).

**Rejected or dropped along the way.**
- *Discrete cells for the number of rewarded features (visible and rewarded counts 2 of 3, 2 of 2 and so on).* Replaced by long sessions with
  three visible features and continuously varied weights, so the weak-weight detection threshold is a curve and the two- and one-feature cases
  are its corners (weights of zero). The distribution of the weights stays a TODO.
- *An oblique Gaussian ridge, and XOR (a saddle) or a reversal of one feature's direction across a gate.* The ridge was an unbounded line,
  effectively one feature in a rotated basis, and an axis-aligned 2D Gaussian with different spreads is separable (each feature's peak can be
  found alone); a **tilted, elongated 2D Gaussian** is the non-separable case with a place to find, so it replaced the ridge. XOR is two
  opposite-corner peaks tied by one rule: it overlaps the two-peak sessions of the sparse-rewards experiment and only tests inferring the second
  corner from the first. A gate with a flat off-region and the linear-times-Gaussian session (the old S6) are one family, so the interaction types
  became additive, sigmoid × sigmoid (the product is its shallow limit), sigmoid × Gaussian and the tilted bump. Three of those four are
  products of a function of each feature (additive in the log of the reward), so the analysis fits a multiplicative model besides an additive and
  a joint one; only the tilted bump is non-separable. A continuous mixture between additive and interaction was dropped as too hard as it stands.
- *Sparsity as the width of a bump.* A narrow 2D bump with the same width as a 1D bump is far sparser, so sparsity is defined in feature space
  (the fraction of the interval or plane in the top x% of reward) and matched across types where types are compared.
- *Knowledge of the reward function as a hint (patch experiments).* It is inferred from a participant's choices instead; the reward function is made
  easy to learn (linear in one feature, or additive in two) and redrawn per instance, with long sessions so the explore/exploit transition shows.
- *Time scarcity and patch contrast as experiments of their own.* Scarcity is always on (a session is too short to harvest every tile) and held at a
  fixed ratio; contrast is a variable in both patch experiments (crossed with travel cost in patch leaving; high early and low later in patch
  assessment, which confounds contrast with practice unless a second group runs the reverse or a random order).

**Not done, and the cautions.** The first draft of the patch-leaving hypothesis said the shortfall from the optimum grows with travel cost; that was
the assistant's addition, with no basis in the PI's design or a clean literature prediction, and was removed. `spatialBalance` evens the reward over
the map and conflicts with the patch experiments (off, or inside tiles); a moisture-paying reward conflicts with spatial balancing too, which bears
on FN's third feature; the Interlude's pair choice by reward gap does not cover typed pairs (RW), per-feature pairs (FN) or flat regions (FI). All are
listed as open items in `docs/EXPERIMENTS.md`.


## Generators split into stages; Designed Interludes removed (2026-11-09)

Phase 0 of building the five planned experiments (`docs/EXPERIMENTS.md`). The world generator and the Interlude designer were written for the CF ladder: one lattice
placement, three attributes, a reward summed from per-bush terms, an Interlude built from three designed trial kinds.

- **Three stages in `world.py`: layout, assignment, reward.** Each is a table of functions chosen per session (`layout`, `assignment`, `rewardStage` in `SessionConfig`; empty = the lattice, the independent draw, the summed terms, which is
  what every session so far used). The random streams stayed numbered by use, not by stage, so every shipped world regenerates byte-identically. Spatial balance is an
  assignment (it needs the reward of the records it deals); the patch experiments will add a tile layout and a tile-mean assignment instead of using it, because their patch means are the design.
  Rejected: one `generate_world` with a branch per experiment (each experiment would edit shared code); a class hierarchy for stages (three small tables are enough).
- **Declared features.** `world.session_features(params)` says which features are visible and which are rewarded, and each reward stage reports its own relevance, so the Interlude designer, the instruction texts and the analysis read one source
  and a new reward term needs no edit to them. Moisture is declared only if it pays or the asset says `moistureVaries` (not yet a `SessionConfig` field: FN adds it with flat terrain), so a decoration moisture is not a channel of the feature gap, as before.
- **Designed Interludes removed.** They searched placements for moisture relations that only the old terraced S3/S4 needed, and their trial mix assumed additive terms. The default is Hybrid, which already
  serves the continuous-terrain ladder. `interludeMode` 0 is kept as `RetiredDesigned` so the numbers in logged manifests do not move, and the generator refuses it. `TRIAL_KINDS` is an empty registry:
  each experiment adds the kinds its analysis needs (RW's global/local/median/valley trials, FN's per-feature trials, FI's trials along and across a tilted axis), recreated when that session is implemented, not carried ahead of need.
  For a session where moisture pays the Interlude may need rethinking (PI, 2026-11-09); nothing is assumed now.
- **Experiments are built from a design module.** `scripts/design/<code>.py` lists the instances of an experiment (fields, hint arm, durations); `scripts/build_experiment.py` makes the assets through `Assets/Editor/ExperimentBuilder.cs`,
  writes the instruction texts and generates the worlds and Interludes. An instance's `design` dict is stored as JSON in the asset's `designJson`, so the logged `SessionConfig` carries it and the session row needs no new column
  (rejected: a `design` column, which would have needed a database migration for no extra information). `ladder.py` stays for the CF ladder until CF is deleted.
- The edits moved the engine-code hash and added fields to `SIM_FIELDS`, so every recorded simulation result is now "stale" by hash (none is wrong).


## FN built on the new generators (2026-11-09)

- **Moisture is FN's third feature.** `SessionConfig.moistureVaries` / `moistureWhenFixed` give a flat, single-coloured valley where moisture is not visible (the baselines with one or two visible features), `moistureIsFeature` declares a visible moisture that
  pays nothing so the Interlude's feature gap counts it, and moisture pays through the ordinary linear component. The FN assets set `moistureTerraceLevels` 0: plateaus would make a linear mapping a four-level one.
  Rejected: a separate "visible" switch per reward stage; leaving moisture decoration and using only shape and colour (it would cap FN at two features).
- **Spatial balance with a moisture term.** The swap step takes an `offset` (what the site adds to the record it holds, here the moisture term) and evens the totals; the top bushes are those in the top decile of the total at the start. With no offset it is
  exactly the old code (all shipped worlds are byte-identical). The tile step still deals the records by value only; the swaps correct it. The refusal ("spatialBalance needs a reward that does not depend on moisture") is gone.
- **No new reward stage for FN.** A linear or inverted-linear component per feature with weight 4 x its share (the best bush pays about 4, as before) is the existing `terms` stage.
- **Per-feature Interlude trials** (`interludeFeatureTrials`, `TRIAL_KINDS["per_feature"]`): for each visible feature that pays enough to show (it must be able to make a reward gap of at least 0.15, three tie tolerances, so a feature that pays nothing, or the r = 0.1 weak ones, get none) a pair that differs in that feature only (others equal; moisture matched within 0.03 where it comes from the terrain), the true reward gap spread
  geometrically from 0.5 to at most 3 noise units (`rewardStd`), capped by what the feature can produce. They are taken out of `interludeTrialCount`, before the Hybrid trials, so the other sessions' stimuli do not move. The gap is a design value, not a threshold: the detection curve in the analysis estimates the threshold.
- **Provisional design numbers** (all in `design/FN.py`): weak weights from the family (1, r, r^2) with r in 1, 0.7, 0.5, 0.35, 0.2, 0.1 over a random ranking of the features (a stand-in for the open TODO), baselines of 60, 75 and 90 s with 8 Interlude trials, weighted sessions of
  150 s with 24 trials (2 repeats, 2 per-feature trials per feature). The weak weights at r = 0.1 are below one noise unit: they are deliberately beyond detection.
- **FN hints name the features (PI, 2026-11-09).** The baselines' hint says which features the answer is among ("The bush shape determines how many points a fruit gives", "Either the ... or the ... does", "One of the bush shape, the fruit color or the ground moisture does"), since
  hints are about structure and this is true; the weighted sessions say all three matter but some more than others. One text per baseline (the named features differ per instance), one shared text for the weighted sessions. The hypothesis on weak features changed
  from a detection threshold to "the probability of learning a rewarded feature is proportional to its weight relative to the others and the noise".


## FN progression: a grid of baseline cells (PI, 2026-11-09)

FN's first design was three baselines (V = 1, 2, 3 visible, one paying) and six weighted sessions. It became a grid of cells with R rewarded features out of V visible, R <= V: row 1 (1,1), (2,1), (3,1), row 2 (2,2), (3,2), each played three times, then six weighted (3,3) sessions, 21 in all.
- **Why:** the (2,2) and (3,2) cells separate "more features visible" from "more features rewarded", which the weighted sessions (always 3,3) cannot, and the repeats give within-participant estimates per cell. Rejected: only more iterations of row 1 (leaves R = 2 unmeasured); a cell (2,2) with random weights (equal weights keep the cell about the number of features, not the breakdown).
- **Order:** one pass through row 1, row 2, then the first weighted session; everything else shuffled across the whole set, so early sessions are simple and later ones are mixed (no confound of cell with time after the first pass).
- **Counterbalancing within a cell:** each feature pays once (R = 1), is the idle one once (R = 2, V = 3), each visible pair appears once (V = 2).
- **Durations:** 60 s at (1,1) plus 15 s per extra visible feature and 30 s per extra rewarded feature (PI, revised: 60, 75, 90, 105, 120 s and 150 s for (3,3); the first rule, 30 s per row or column, gave 180 s). A stand-in until Interlude timing is measured. Total play about 37 minutes plus Interludes.
- **Interlude trials (PI):** 5, 10 and 20 for R = 1, 2, 3 (the weighted ones keep 2 repeats and 2 per-feature trials per feature).
- **Screens count sessions (PI):** "Session n of 21 · Part A" on the instruction and score screens, Part B for the Interlude; the Interlude no longer counts as a numbered part.
- **Hints:** (2,2) "Both the X and the Y determine how many points a fruit gives."; (3,2) "Two of the three features determine ..." (PI's wording).
- **Not done:** drawing the per-participant instances from a pool (to cover the weight space beyond six points and balance feature identity across participants; touches run-start, resume and the server's session count); the tiling of the weight space.


## Tests state a configuration (PI, 2026-11-09)

The tests had grown around the CF ladder: sessions called by name (`S1`, `S3_Interlude`, ...), assertions about what a particular shipped session pays or varies, and old terraced or bump sessions reached through overrides on a live asset. Deleting CF, or building FN, would have broken or silently changed them.
- **Generator tests** build their session from a stated configuration (`scripts/synthetic.py`) on the tutorial's asset, and `test_realization.py` asks whether the intended variance appears in the generated worlds and Interludes (which features vary, what each pays, the noise, what an Interlude pair differs in), for several configurations and for every built design. These are the tests that say a design does what it claims.
- **Engine-level tests** (simulator, agents, battery, results, analysis, fingerprint, replay) need an arbitrary environment, not a particular one. They keep their `S1`-style names, which now resolve to frozen copies in `scripts/fixtures/sessions/` under the `frozen_sessions` marker, so they test the engine and not the current design. Rewriting them around synthetic sessions was rejected: it would change tests of the engine for no gain in what they check.
- **Not converted:** `test_ladder.py` (about `ladder.py` and the CF assets; retired with CF) and the freshness tests, which are about the live files and now loop over every session and Interlude asset instead of a list of names.


## CF removed (PI, 2026-11-09)

FN replaces the CF ladder as the game's experiment (RW, FI, PL and PA will replace the rest). The CF assets, world files and Interlude files are deleted from the build and the catalog (they are in git history), `scripts/ladder.py` and its test moved to `archive/cf_ladder/`, and the scene's default experiment is FN.
The old aliases `P`, `S1` to `S7` (and their Interludes) that the simulator, the agent battery, the results database and the engine tests use now name frozen copies of those sessions in `scripts/fixtures/sessions/`, so the environments recorded results were made in are unchanged and the battery keeps running on them until it is redefined on the new experiments' sessions.
Participant data from CF, if any is ever collected, would carry its own experiment code in the database; none exists.


## Publishing is one command (2026-11-09)

Deploying FN needed three manual registrations (experiment, worlds, release), each with an argument that could be mistyped (the commit, the session counts), and a database connection string exported in the person's shell. Now `server_admin.py publish --build <dir>` derives all of it: the experiments and their order and prerequisites from the catalog and the experiment assets, the commit from the build's `build_info.json`, the session counts from git at that commit, the files from the build itself. The connection string is read from `FORAGING_DB_URL` or from `~/.config/foraging/db_url`, refused unless only its owner can read it, so nothing has to be exported and an automated session can run the command (the string never enters the repository or a transcript).
`register_experiment` keeps an existing completion code and payout when none is given (it used to blank them, which a repeated registration would have done to a real Prolific code). Rejected: registering from the Unity side or from an Edge Function (the database password would then live in the game or in a function secret that the game can reach); a registration step per experiment in `build_experiment.py` (a build and a registration are different moments: the registration names a commit that exists).


## Terrace modes without a level count; FN's ground is diffusion (PI, 2026-11-09)

The ladder's terraces were n evenly spaced plateau levels. The wish was a naturalistic ground: plateaus of various sizes and elevations from the ordinary wavy field, a continuum of moistures and heights, larger regions of consistent value, and a control over coarseness. `SessionConfig.moistureTerraceMode` now has three modes: **Levels** (the smooth field or n levels, evenly or unevenly spaced: the old behaviour, every existing world byte-identical), **Staircase** and **Diffusion**.
- **Research** (procedural terrain tools: Houdini's Terrace node, Hesiod, World Creator, World Machine, a few forum answers and papers): the standard method is a remapping of elevation into steps with smoothed ramps, usually with a fade back to the original and masks for where it applies; naturalism comes from noise that shifts where the levels fall, from region masks, and from light blurring or erosion afterwards. Edge-preserving diffusion is known for denoising heightfields (its "staircasing" artifact is exactly a plateau) but is not sold as a terracing tool.
- **Staircase**: the field's rank (uniform over the valley) is shifted by a low-frequency noise (`terracePhaseShift`, about 0.4 to have an effect; at 0.07 to 0.16 it did almost nothing), put through a random staircase (`terraceMeanWidth` and `terraceWidthSpread` draw the plateau bands, `terraceMaxBand` caps one, `terraceMinStep` merges neighbours that are too alike; the number of plateaus is whatever comes out), and mixed with the smooth rank by `terraceStrength`.
- **Diffusion**: Perona-Malik diffusion of the rank field on a grid over the valley (`terraceDiffusionIterations`, `terraceDiffusionEdge`: a quantile of the field's slopes as the edge threshold; lower keeps more edges), rescaled **linearly** to 0..1, mixed by `terraceStrength`, read by bilinear interpolation. **Not rank-equalised**: a first prototype did equalise by per-pixel rank, which turns the tiny differences on a flat plateau into a slope and made diffusion look noisy and weak (it was dismissed wrongly for a while).
- **FN uses Diffusion** with an edge threshold of 0.1 and 500 iterations, noise frequency 0.8 (regions of several bushes; the CF ladder used 2, wavelength about 50 units, where a plateau held about 5 bushes) and a small top undulation (0.03). The Staircase mode stays available. An earlier agent study found larger patches harder for a learner to use (a 0.31 against 0.65 share of the oracle's lead at frequency 0.6 against 2): not measured for FN's moisture feature.
- **Tools**: `Foraging > Terrain preview` edits a throwaway `<code>_PREVIEW` copy of a session (git-ignored), regenerates its world through `world.py` and rebuilds the preview in the scene, so values can be tuned in 3D before they go into the design table.
- **Known and not fixed**: the base noise has lattice-aligned straight strips (a long straight edge along a border, parallel strips) that terracing turns into long straight plateaus. `moistureTerraceUnevenness` (uneven levels in the Levels mode) was an intermediate step and is kept, unused.


## Reward balancing leaks which feature pays; each feature is balanced on its own instead (PI, 2026-11-09)

`spatialBalance` (spatial.py: tiles at several scales, then swaps of whole (shape, colour) records, to even the reward over the map) was found, while practising FN, to leave large patches with very even colour or shape. Measured on the FN worlds (local spread of 60-unit disk means against chance, 1 = chance; Moran's I of neighbours):
- **The rewarded feature is conspicuously regular.** Balanced: 0.44 to 0.58 with Moran about -0.2 (neighbours deliberately unlike); the unrewarded features about 1.0; with balancing off every feature is at chance. That is a layout-only cue to which feature pays, and to where good bushes are.
- **The moisture offset I added (balancing the totals, including a moisture term) made it worse:** it coupled shape and colour to the moisture patches, correlations up to +0.66 (FN_S7, shape) and between -0.26 and +0.37 in the other weighted sessions, against about 0 unbalanced. A test of the totals' evenness did not look at the features' independence; it should have.
- **Why no balancing of the reward can avoid it:** evening the reward constrains the relevant features' local distribution and nothing else, so the relevant feature always differs from the irrelevant ones, unless the irrelevant ones are constrained the same way.
- **Rejected:** large scales only (the patches noticed were at 120 units), a partial strength (the cue shrinks, with no point where it vanishes), balancing positions instead of features (high-value bushes spaced apart: the same cue), changing the reward function (a scientific change), and choosing the most even of N world seeds (natural statistics but a small gain: patchiness 0.87 for the best of 30 against 1.01 for a random world and 0.47 balanced). Turning balancing off entirely was the fallback.
- **Adopted: `featureBalance`** (Off, Tiles, TilesAndSwaps; `featureBalanceTarget`, `featureBalanceScales`; assignment `balanced_features`). Each visible feature (shape, colour, and the practice session's hidden random value) is balanced over space on its own, with its own random stream, at scales 40, 60, 120 and 240, until the evenness cost reaches the target (0.7). They are dealt separately, so they stay independent of each other and of moisture, and no feature is treated differently from another whether or not it pays. It uses no reward and no moisture offset. Reward evenness then follows from the weights being on shape and colour, and not when moisture carries them; moisture keeps the terrain's own patchiness.
- **Measured on the FN worlds:** rewarded features 0.81, unrewarded 0.79 (local ratio at 60 units; chance is 1.0, the old reward balancing gave 0.44 against 1.0); moisture's correlation with shape and colour within 0.06 of 0 everywhere; reward patchiness cost 0.71 to 0.82 where shape and colour carry the reward (1.0 unbalanced), unchanged where moisture does. The balanced layout is still more even than chance for every visible feature; whether that looks natural is for the PI to judge in the Editor (the target is the control).
- `spatialBalance` is kept for the frozen sessions of the engine tests and cannot be combined with `featureBalance`. The FN design uses `featureBalance` and `spatialBalance` Off.

## World files: quantized and compressed grids, format version 2 (PI, 2026-11-10)
A world file was 4.03 MB, 97% of it five float32 grids of 449 x 449 (moisture, elevation, rock, snow, ramp; the bush table is 108 KB). The 21 FN worlds were 84 MB: it made the development build 211 MB, whose GitHub Pages deploy timed out three times (the release build of 110 MB and a 173 MB development build had deployed), and every participant downloaded all 84 MB when choosing FN. Version 2 stores each grid as unsigned codes between its own minimum and maximum (16 bits for moisture and elevation: a step of about 0.001 world units of height; 8 bits for the three 0-1 masks: a step of 0.004) in one gzip stream: about 0.8 MB per world, the FN folder 17 MB. Version 1 files still load (the loader and `read_unity_world` accept both).
- **Only the terrain grids are quantized.** The bush table (positions, attributes, values, fruit rewards) stays full precision, so what a bush pays and shows is exact; the ground's colour and the height under the feet move by at most half a step. `read_unity_world` (replay, visibility) and `WorldData.Load` decode with the same arithmetic (checked: minimum, maximum, mean and a sampled cell agree between Unity and Python on FN_S10).
- **The freshness test compares decoded content, not bytes** (the compressed bytes depend on the zlib that wrote them).
- **Rejected:** deriving elevation and the masks in C# from moisture and the mountain parameters (about 9 MB for FN, but elevation is not a clean function of moisture, differing by up to 0.76 in the valley, and it would duplicate the generator in C#); a lower grid resolution (a visual, hence scientific, change); 8-bit elevation (a step of 0.15 units would show as stair-steps).
- Every world hash changed, so the worlds were regenerated and the new files must be registered (`server_admin.py publish`). No participant data existed yet.

## The menu row is one line; the introduction explains the pay (PI, 2026-11-10)
Each experiment is one row of the menu (name, length, prerequisite, button, under a header line) instead of a two-line block, so that more columns can be added as participants need more information to decide whether an experiment is worth their time. The length is the session count and an estimated time ("21 sessions · ~90 min"; a started one shows "9 of 21 · ~51 min left" and a bar, a finished one "Completed" and a full bar). `ExperimentConfig` holds `estimatedMinutes` (0 = worked out from the sessions: durations plus each Interlude's trials at their time limit plus 20 s of instructions per part, to 5 minutes; an upper bound, to be replaced by the measured median) and `typicalPoints` (what an average participant earns; **a placeholder** (FN 600) that the menu does not show for now: a "Points (typical)" column was built and removed the same day, with the points earned per experiment that shared it; the total points row and its (i) went later the same day: the menu shows no points at all). The prerequisite column names the experiments to finish first ("-" for none; orange when unmet).
- **No money on the menu.** The pay is explained in the introduction (a fixed payment through Prolific plus a bonus per point, and the points-to-money rate), never as amounts per experiment: the amounts will change as the timing and the pay are tuned. A "Pay" column with dollar amounts was built first and removed the same day.
- **The introduction** (`IntroScreen`, `StreamingAssets/introduction.txt`: a title, then sections of a heading line and its text; the text now is one placeholder sentence each on payment, timing and pauses, sound) is shown once after the login of an online build, before the menu, and from a button near the bottom of the menu at any time; the consent form can be read again from a button beside it (`ConsentScreen.ShowView`, nothing to sign). Both buttons end the menu with a `ChosenCode` that is not an experiment (`MenuScreen.IntroductionCode`, `ConsentCode`), and `Bootstrap` shows the page and then the menu again. A returning participant sees the introduction once per page load, not once ever (the server keeps nothing about it).
- The completion code is a read-only input field (a click selects all of it) with a Copy button (`Clipboard`: `navigator.clipboard` with a textarea fallback in a browser, `GUIUtility.systemCopyBuffer` elsewhere); the browser path is untested in a real browser (a browser may refuse the write outside a user gesture, Safari most strictly), the code stays selectable either way.

## Hints bold their essential words (PI, 2026-11-10)
In the instruction texts a phrase between `**` is shown in bold teal (`UiStyle.Chips`, `UiStyle.Emphasis` #6FD3D0), with the `[Key]` chips. What is emphasised: in a baseline FN hint the quantifier (Both, Either, One, Two) and the features it names ("bush shape", "fruit color", "ground moisture"; "three features" in the two-of-three hint); in the weighted hint "All three features"; in the tutorial's session text "points", "time" and "Different bushes"; in the Interlude texts (FN and tutorial) nothing. One colour for every phrase: teal is neither an interface colour (accent blue, "completed" green) nor on the fruit colour ramp (a ramp colour could hint at which feature pays), and a colour per feature would say it outright. Tried and set aside the same day: bold alone (not clear enough), a softer teal, regular weight in teal, and fewer emphasised words (the quantifier alone, or the feature alone in a single-feature hint). The markers are written by `scripts/design/FN.py` (`baseline_hint`, `HINT_WEIGHTED`, `INTERLUDE_TEXT`) and by hand in the tutorial's text files; `test_fn_design.py` checks them.

## Reduced runs: `short` and `repeats` (PI, 2026-11-10)
Two independent knobs for development (`RunModes`) so that the whole path (the sessions and Interludes, the finish screen, the round trip to the menu, the loading bar) can be tested in minutes, or pilots run on friends and labmates in a fraction of the time. **`short`** (0 to 1) makes every session that fraction of its length (at least 10 s) and every Interlude play that fraction of its trials (at least 3), proportionally so that FN's timing steps between cells stay (a factor of 0.33 gives 20 s for the 1-visible, 1-rewarded cell and 50 s for the 3, 3 cell). **`repeats`** (1 or more) plays a cell's sessions only up to that iteration, each with its Interlude, read from the `iteration` in each session's design record (a session without one, the tutorial, always plays; more than any iteration that exists = everything): `repeats = 1` is the first pass, five baseline cells and one weighted session, six sessions of the 21. The weighted sessions count as iterations 1 to 6 in their order of appearance.
- **Where they are set:** the Editor's Foraging > Experiments window (two fields, EditorPrefs, kept between runs), `?short=0.3&repeats=1` in the address of a browser development build, `-short 0.3 -repeats 1` on a standalone development build. A release build ignores all of it (a link must not shorten a participant's run). They replace the old Quick test (the Editor menu item, `-quick`, `?quick=1`, GameManager's quick* fields, `SessionConfig.QuickCopy`), which used one fixed length for every session.
- **A reduced run must still finish**, so that the finish screen, the completion code and the menu can be tested. The game declares the run's session count at run-start (`expected_sessions`: sessions and Interludes alike; sent only when `repeats` drops sessions, since `short` alone leaves the count unchanged); the server (migration `20261110000000_reduced_runs.sql`) stores it in `runs.expected_sessions`, checks it in `finish_run` instead of the release's count, and shows it as the menu's `n_sessions`. **Only a release registered as a development release may declare one** (`releases.development`, set by `server_admin.py publish` from the `development` flag `BuildInfoWriter` writes into build_info.json for a development build); anything else gets 403 `reduced_run_not_allowed`, as does a count above the experiment's. A returning participant must use the same knobs (a resume that declares none finds the full count again). A reduced run that finishes counts as finishing the experiment (it unlocks dependents and shows the experiment's completion code): use pilot IDs and leave them out of the analysis, as for `peter`.
- **Logged:** a `run_modes` event (`{"short", "repeats"}`) after each session's start when either knob is on; the stored session config shows the shortened duration. The loading bar still loads the whole experiment's files, as a participant's would.
- **The menu** counts sessions without their Interludes ("12 of 21", with the bar following the parts done) and shows the reduced run's own session count and time. It used to print the server's `sessions_done` (completed sessions and Interludes alike) against the session count ("24 of 21").
- Rejected: a separate experiment for the one-of-each run (two knobs would need four variants, and it cannot shorten sessions); truncating the list without telling the server (the run never finishes and the code is withheld, or, with only `short`, the real code is handed out).


## Deploy commit messages come from the build, and the release keeps the record (PI, 2026-11-10)
The Pages repository holds one commit (`deploy_webgl.sh` makes an orphan commit and the deploy force-pushes it), so a hand-typed message is seen only until the next deploy, and GitHub's Actions list shows its own "pages build and deployment" for every run whatever the message. The message is now made from the build (`server_admin.py describe --build <dir> [--reason ...]`: "Development build d2edc3c (dirty): 146 MB, parts TUT 2, FN 42", then the reason, the full commit of this repository, what the build holds and when), so it is never typed and always says what is live; the optional argument of `deploy_webgl.sh` is the reason. The permanent record is the registered release: `publish --build` registers it with the same subject line (and `--note`, the reason) as `releases.note`, next to its commit, development flag and registration time. Rejected: a changelog file (the main repository's log and the releases table already are one), and a custom Pages workflow to name the runs (it would replace the built-in deploy for a label).
