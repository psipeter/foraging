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
then float32 grids (moisture, elevation, rock, snow, mountain ramp) at the mesh resolution, flattened `i*res + j`.
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
for zero feedback between sessions). The leak risk is judged small because every session has a different reward function and
only counts are shown, not which trials were right. The practice Interlude shows no score (it earns nothing).


## Interlude instruction text: terse, no controls or time limit in the text

**Decision:** the Interlude instructions are short lines in the style of the main sessions' text. The practice Interlude (`instructions_interlude_P.txt`) says only: two trees will
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
`dt`) would not be deterministic. The cost is about 350 KB for 150 s at 60 fps, the same as the old 10 Hz file with its visibility lists.

**Rejected:** (a) keeping `visible_tree_ids/distances`: derived (pose + terrain occlusion), bulky, recomputable offline; (b) a fixed
20-30 Hz log: simpler for agents but cannot reproduce harvest gating exactly (agents resample with `replay.steps` instead); (c) copying the
4 MB world into every session folder (hash + one archive instead); (d) Parquet (CSV is readable and a session is ~350 KB); (e) a
hand-enumerated config block in the metadata (it had silently omitted look sensitivity, sun and harvest-timing parameters; the serialized
asset cannot omit anything).

**Details future-us might "fix":** `t` is a double accumulated from `Time.deltaTime` by the logger itself (it stands still while an
instruction screen sets `timeScale` 0), not `SunController`'s clock, so events and rows share one clock exactly; `harvest_release` events
for bouts the Interlude cancels or the session end closes are not explained by the keys, so the replay takes them from the log and marks
them `forced`; events on a session's last frame may differ by one frame from the replay (it depends on whether the sun clock or the harvest
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
