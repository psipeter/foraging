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
