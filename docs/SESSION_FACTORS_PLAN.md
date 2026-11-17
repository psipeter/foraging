# docs/SESSION_FACTORS_PLAN.md — session-level factors as continuous knobs (draft 2, 2026-11-17)

A plan, not a record: nothing here is built. It is for the PI and the researcher to revise before any code is written. Scientific questions: `docs/SCIENCE.md`. Why past choices were made: `docs/DECISIONS.md`.

## 1. Purpose and scope

Build the infrastructure that lets a session be created from a handful of **continuous knobs**, each held constant within the session, so that later we can choose which settings to run and how to balance them. In scope: what each knob means and how it is measured, how a knob is turned into generator parameters, how the realised values are checked and logged, how sessions are built from a table of knobs. **Out of scope** (later, after the PI meeting): which settings to run, the design matrix, per-participant order or subsets, the analysis pipeline, any change to the harvest rules or the UI.

## 2. What is decided (from the discussion)

- Five session-level factors: **reward-function complexity**, **sparsity of reward in feature space**, **travel time between patches**, **reward contrast between patches**, **reward diversity within a patch**. (The number of rewarding features is folded into complexity; moisture never pays and stays decoration.)
- Every non-categorical factor is a **continuous knob**. No levels are hard-coded; discretising is a step taken when a design is chosen.
- A reward function is described by its **2D value map** R(shape, colour) on the unit feature plane. Weights are the map's partial derivatives, not a separate concept; linear is one family among many. The categories of complexity will be brainstormed later, so the representation must not fix them.
- **Sparsity** starts as the Gini coefficient of the value map over the feature plane; the metric must be replaceable.
- **Travel time is geometry only**: the walk between patches over the player's speed.
- **Mean reward is held constant** across sessions, with two anchors: (a) the mean bush value of the world, (c) the points a reference policy earns in a session (the simulator's `oracle` and `nearest`).
- Fixed in every session (defaults may be tweaked later): 120 s of foraging, 9 bushes per tile, the per-fruit noise `rewardStd`.
- Each session has its own new reward function.
- **The first families are the earlier ladder: additive, multiplicative, non-separable** (all already expressible by the engine's reward terms). Specific maps are designed later.
- **Equalising maps is a transform of the 2D map, not only a gain** (draft 2). A baseline shift or a multiplication (a gain) is the default and the simplest such transform; more sophisticated ones (a monotone remapping of the value range, matching the distribution of values over the plane, and so on) are a **TODO for value-map design**, to be chosen once we know which maps we test. So the pipeline has a pluggable *equaliser* slot, not a hard-coded gain.
- **Noise is a second 2D map** σ(shape, colour) next to the value map, adjustable by the same kind of transform to meet criteria once the raw maps are known. The default, and the current implementation, is a flat plane (the fixed `rewardStd`). A non-flat noise map needs path B (it changes how `world.py` draws the per-fruit rewards), so until then the specification carries the field and the compiler refuses a non-flat one.
- **Ranking pools will be redefined relative to the value map** once maps exist (sample evenly across the map's reward range and gradients, and so on): a later TODO (see 8), not part of milestones 1 to 3.

## 3. Concepts

**Knob.** A number the researcher sets for a session (for example a target Gini, a target travel time in seconds). A session is `session(knobs, seed)`; the seed draws everything that is not a knob (see 6).

**Realised value.** What was measured on the world that was actually generated: the same five quantities plus the anchors. The knobs are targets; the realised values are what the analysis should use as covariates. Both are logged.

**Value map.** An array R on a grid over (shape, colour) at the fixed moisture, the expected bush reward before per-fruit noise and rounding (the game pays `max(0, round(R + Gaussian(0, rewardStd)))` per fruit). Descriptors computed from it, all continuous:

| Descriptor | Definition | Answers |
|---|---|---|
| sparsity | Gini of the clipped map over the uniform grid; also the fraction of the plane above half the maximum | 1.2.2 |
| effective weights | mean abs dR/dshape and dR/dcolour, their share and total | 1.2.1.1 |
| interaction | 1 - R² of the best additive fit f(shape) + g(colour) (0 = additive, up = conjoined) | 1.2.1.3 |
| nonlinearity | 1 - R² of the best plane (linear) fit | 1.2.1.3 |
| range | max - min | scale |

**Patch factors, measured on the generated world** (not on the map): travel time = median over neighbouring tile pairs of the walk between their clusters (cluster-edge gap and centre-to-centre distance) over `playerMoveSpeed`; contrast = SD across tiles of the tile-mean bush value (and the mean absolute difference between neighbouring tiles); diversity = mean over tiles of the SD of bush values inside the tile.

## 4. How a knob becomes generator parameters (the calibration order)

The five factors are not independent in the generator, so a request is solved in an order:

1. **The map** from the complexity and sparsity knobs (a map specification plus a width or sharpness parameter solved until the target Gini is met).
2. **The equaliser** to hit the mean-bush-value anchor (a). Default: a gain, a scale on R in the same place `REWARD_SCALE` sits today (the whole map is multiplied by one number per session; the shape is unchanged). The slot is a transform of the 2D map, so a shift or a more sophisticated remapping can replace it later (TODO for value-map design). Any such transform is a per-session rescaling, which CLAUDE.md's "never normalise the reward function output" may forbid: a **scientific decision for the PI**. The noise map gets the same kind of slot (default: flat).
3. **The spreads**: how far apart tile centres lie in the feature plane (between) and how far bushes lie from their tile's centre (within), to hit the contrast and diversity targets in reward units. `tiles.spread_for_reward_sd` already solves one of them for a target SD.
4. **The geometry**: `tileRadius` (closed form) for the travel time; the cluster radius stays at its default.
5. **Verification by simulation**: the anchor (c) is measured, not solved, on a few seeds; if it misses by more than a tolerance the gain is corrected and steps 3 to 5 repeated (a capped loop).

Steps 2 and 3 depend on each other (the mean value depends on where the tile centres lie), so they are solved together (a small root-find on gain and the two spreads), not one after the other. Expect that some knob combinations are unreachable (very sparse maps with high within-patch diversity, say): the sweep in milestone 1 maps the reachable region, and `realize` fails loudly outside it.

## 5. Architecture

- `scripts/value_maps.py` (new): a map is a **specification**, a list of primitives (a ramp along an angle with a slope, a Gaussian bump with centre, widths and rotation, and later a table or other family), evaluated on arrays, serialised to JSON; the descriptors of 3.
- `scripts/factors.py` (new): `measure(world)`, `calibrate(knobs, seed)`, `realize(knobs, seed) -> Instance` and a command line (`measure`, `sweep`).
- **Where the map reaches the world generator.** Two paths:
  - *A, no engine change:* compile a map specification into the existing `RewardFunction` (Gaussian bumps already have a centre, separate widths per axis and a rotation, so a mixture of them approximates any smooth map). Works today, limited to that primitive.
  - *B, a `map` reward stage:* `world.py` already selects the reward by `reward_stage` (`REWARDS`; the ranking pool and the tile modes call it as a function). A new entry reads the specification from a new `SessionConfig` string field (`valueMapJson`, beside `designJson`). Unity ignores it, because every world file carries the pre-drawn per-fruit rewards and C# evaluates the reward function only as a fallback that no shipped world reaches. Costs: an engine hash move (`world.py`, `ranking.py` are `ENGINE_FILES`; the results database holds nothing under the current hash, so none is lost), the field added to `fingerprint.SIM_FIELDS`, the field added in C# and on the assets.
  Plan: start on A (milestones 1 to 4 need no engine change), add B when a family cannot be expressed.
- `scripts/design/<code>.py` (a new design module, or FOR): a table of rows of knobs becomes `Instance`s through `realize`; `build_experiment.py` builds them with the worlds and ranking pools. `designJson` carries the knobs, the realised values, the anchors, the seed and the calibrator's version, so a session is reproducible and analysable. **No data column changes**: the logged session config is a JSON blob, so this is additive.
- Tests: described per milestone.

## 6. Nuisance randomisation

The seed draws what is not a knob: which feature carries a ramp, its direction, the positions of peaks, rotation, the tiles' feature centres, the ground levels. Participants can then learn a structure across sessions but not a specific rule (TUT already inverts shape for this reason). The descriptors of 3 must be **invariant** to these draws, and a test shows it: measure many seeds at fixed knobs and check the spread of the realised values against the calibration tolerance.

## 7. Milestones

| # | Deliverable | Acceptance | Needs |
|---|---|---|---|
| 0 | this plan, revised and agreed | the open decisions of 9 answered | you, the PI |
| 1 | measurement layer and a sweep over today's levers (7.1) | see 7.1 | nothing |
| 2 | `value_maps.py`: the ladder families, the noise map, descriptors, compile to existing terms (path A) (7.2) | see 7.2 | nothing |
| 3 | single-knob calibrators and the pluggable equaliser (7.3) | see 7.3 | the PI on the tolerances |
| 4 | joint calibration (gain and the two spreads), anchor (c) verification by the agents, **independence test** on a space-filling matrix of knobs | correlation matrix of the realised factors near identity over the reachable region; anchor (a) constant by construction, anchor (c) spread reported | the PI on the tolerance |
| 5 | loader and build: a table of knobs becomes built sessions; the knobs and realised values in `designJson`; ranking pools; example sessions (not a design) | `validate_run` and `replay` pass on a played example session; a rebuild is deterministic | a playtest of an example session |
| 6 | (later, after the PI) path B if needed; the design matrix; per-participant order and subsets | | the PI's interactions |

Sizes (rough): 1 and 2 are a few hundred lines each, 3 and 4 a few hundred with the sweep's driver, 5 about a hundred. Each milestone is its own commit with the tests passing (`run_tests.py --fast`; the slow tests only with approval).

### 7.1 Milestone 1: measurement layer and sweep (`scripts/factors.py`, part one)

No engine file is edited, so no hash moves. Reads worlds and sessions; writes nothing into the project.

- **`measure(world, session) -> dict`**: the patch factors of 3 (travel time as cluster-edge gap and centre-to-centre over `playerMoveSpeed`; contrast as the SD across tiles of the tile mean and as the mean difference between neighbours; diversity as the mean within-tile SD), the mean bush value (anchor a), the bush-level Gini, the realised noise SD (from the pre-drawn per-fruit rewards against the bush value), and the visits a 120 s session allows.
- **`map_descriptors(session)`**: the descriptors of 3 from the session's reward function evaluated on a grid over (shape, colour) (the grid evaluator mirrors `world.py`'s reward, nothing new in the reward rules).
- **Command line:** `factors.py measure <session>`; `factors.py sweep` over today's levers on a frozen session (`tileRadius`, `tileSpread`, the tile modes and `tileGoodFraction`, the reward weights, `rewardStd`), several seeds each, printing a table and the correlation matrix of the realised measures.
- **Tests** (stated configurations from `synthetic.py` on `FIX_T0`, not shipped sessions): analytic cases (a linear map has interaction 0 and nonlinearity 0; a flat map has Gini 0; one narrow bump has a high Gini and a high nonlinearity; a world with equal tile means has contrast 0; travel time equals the hexagon geometry); determinism; invariance of the descriptors to the seed.
- **Acceptance:** the sweep's table answers which of the five factors move together under today's levers, which can already be set alone, and the reachable ranges; the analytic tests pass; `run_tests.py --fast` passes.
- **Output the PI reads:** that table, because it shows how coupled the generator is before anything is built.

**Status (2026-11-17): built, cut down.** `scripts/factors.py` (`measure`, `map_descriptors`, `factors.py measure <session> [--seeds]`) and `scripts/test_factors.py` (7 tests: travel time against the hexagon geometry, a flat map has no contrast or diversity, tiles of a single point have diversity 0 and contrast above 0, the gain scales the reward measures and leaves the walk alone, the mean value and noise are the world's). The sweep over today's levers was dropped (the PI, 2026-11-17: M2 first, the sweep not needed). Measured on 10 worlds (seeds 0 to 9) of the two live sessions, FOR_S1 / TUT_S1: travel time 4.26 s / 4.26 s (cluster edge to edge; 4.55 s from the nearest bushes, 6.93 s centre to centre), **contrast 0.29 / 0.34 against diversity 0.86 / 0.97**, neighbour difference 0.34 / 0.38, mean bush value 2.21 / 2.09, bush Gini 0.23 / 0.27, realised noise 0.664 (the stated 0.6 plus the rounding of a fruit to whole points). **The patches barely differ from one another in FOR_S1**: with the default modes (`none` between, `pool` within) a tile's bushes are a random draw from the whole map, so the spread of the tiles' means is the sampling spread of nine bushes (0.86 / 3 = 0.29), and the variation inside a patch is about three times that between patches. A contrast knob in M3 has to start from the between-tile modes (`random`, `graded`, `bimodal`) and a within-tile spread, not from the default.

### 7.2 Milestone 2: value maps (`scripts/value_maps.py`)

Still no engine change (path A). The reward ladder itself is recorded in `docs/SCIENCE.md` ("Reward complexity ladder") and its rationale in `docs/DECISIONS.md`.

- **Specification:** a small frozen dataclass, JSON round-trip: `bumps` (the Gaussian is the only primitive; the ramps were removed 2026-11-17), `noise` (a flat SD by default; a non-flat map is representable but the compiler refuses it until path B) and `equaliser` (a gain, default 1). Primitives evaluate on arrays, so any descriptor is computed on a grid.
- **The ladder as constructors:** `additive` (a wide corner Gaussian), `multiplicative`, `nonseparable`, each with the nuisance draws (corner or centre, tilt, which feature has the long axis) taken from a seed, and the core `gaussian(centre, width, aspect, angle, scale)`; **a continuous knob between rungs** is the Gaussian's own parameters, read off the descriptors.
- **`compile(spec) -> SessionConfig reward fields`**: writes the existing reward fields (weights, bumps) so that `world.py` generates the world unchanged.
- **Tests:** the spec round-trips through JSON; the compiled map is what the generated world pays; the rungs keep their separability class over the seeds; the reference examples fall in separability up the ladder.
- **Acceptance:** one example of each rung compiled, generated, measured and described (`scripts/value_map_examples.py`); `run_tests.py --fast` passes.

**Status (2026-11-17): built, then revised** (`scripts/value_maps.py`, `scripts/test_value_maps.py`). **Revision after reading the earlier ladder work** (`docs/DECISIONS.md`, "Rejected or dropped along the way" and the FI entry; the first build used sigmoid products and a ridge, written from the plan's labels without it, and was removed): the core primitive is one **placeable, stretchable, rotatable Gaussian bump**, `value_maps.gaussian(centre, width, aspect, angle, scale)`, and the rungs are positions in its parameter space: **additive** = a **wide corner Gaussian** (decided 2026-11-17; `value_maps.wide_corner` and `additive`: spreads about 0.7 at the geometric mean, unequal to set the share of the slope on each feature, the corner drawn by the seed; raw interaction below 0.04 over shares 0.3 to 0.7; the exact two-ramp map was removed with the ramp components, a ramp pair is not a primitive), **multiplicative** = axis-aligned and stretched, **non-separable** = the same Gaussian turned. Rotation alone is the difference between the last two. The sigmoid product of the first build was removed (monotone products rank bushes like an additive rule in the log; `docs/DECISIONS.md`). The rotated parabola of 2026-11-11 was tested and dropped for the rotated Gaussian (DECISIONS); it is not built.

**Reference examples** (`scripts/value_map_examples.py`, figure `docs/value_map_examples.png`; one example per rung, a proposal, with the two Gaussians at the same centre (0.55, 0.45) so that stretch and rotation are the only differences):

| Rung | Map | interaction | log interaction | nonlinearity | Gini | shape share |
|---|---|---|---|---|---|---|
| additive | corner (1, 1), spreads 0.63 (shape) and 0.78 (colour) | 0.03 | 0.00 | 0.05 | 0.24 | 0.58 |
| multiplicative | width 0.15, aspect 1.5, angle 0 | 0.20 | 0.00 | 0.97 | 0.63 | 0.39 |
| non-separable | width 0.15, aspect 3, angle 45 | 0.61 | 0.84 | 0.94 | 0.50 | 0.50 |

Separability falls by a factor of 6 from the first rung to the second and 3 from the second to the third (interaction 0.03, 0.20, 0.61); log interaction splits the last two (0, 0.84). The Gini is **not** matched across the rungs (0.24, 0.63, 0.50), because a wide corner bump is near a plane and a narrow one is sparse: the sparsity-equalising step of M3 is what removes this, and until then a comparison of the rungs is confounded with sparsity.

**Degrees of separability, measured.** The raw `interaction` (1 - R² of an additive fit to R) does not separate multiplicative from non-separable, because a product is not additive in the value; a second descriptor, `log_interaction` (the same fit to log R where R is at least 1 percent of the maximum), is exactly 0 for any axis-aligned Gaussian, wherever it lies and however stretched, and grows with rotation (aspect 3, width 0.2, centre 0.5: 0, 0.37, 0.66, 0.82 at 0, 15, 30, 45 degrees; a round bump has none to turn). The two read together give the class: additive = raw 0; multiplicative = log 0; non-separable = both above 0. Findings that matter for the design:
- Sparsity and separability are **entangled** through the widths: for the aligned Gaussian in the middle, Gini falls from 0.54 to 0.29 as the width goes from 0.15 to 0.25, and stretching it lowers the raw interaction (width 0.2: 0.19 round, 0.04 at aspect 2, 0.01 at aspect 3: a bump that long crosses the whole range of one feature and is nearly a one-feature rule, as DECISIONS noted for FI). So a stretched multiplicative rung is close to additive in the value, and the multiplicative rung that most differs from additive is the round or mildly stretched one. The aspect and the width are knobs, and M3's sparsity solver must hold the separability class while it solves the width.
- A corner bump is near additive only when wide (raw interaction 0.31, 0.06 at width 0.3, 0.6); an edge bump wide along the edge is a function of one feature (raw 0.0003, shape share 0.98).
- With the Gaussian the mean bush value is stable across seeds (multiplicative 1.72 ± 0.02, non-separable 1.80 ± 0.05, against 1.0 ± 0.22 for the first build), so the equaliser has less to do for these rungs.
Descriptors are computed on a uniform grid of the map; the patch factors measured on a generated world (the part of M1 that M3 needs) are not built, and the M1 sweep is dropped.

### 7.3 Milestone 3: single-knob calibrators (`scripts/factors.py`, part two)

Each calibrator takes one target and returns generator parameters; the others are held at stated defaults. Unreachable targets raise an error saying what was reachable.

| Knob | Parameter solved | Method |
|---|---|---|
| travel time | `tileRadius` | closed form from the hexagon geometry and `playerMoveSpeed`; verified on the measured world |
| contrast | between-tile spread | `tiles.spread_for_reward_sd` (exists), then verified |
| diversity | within-tile spread | `tiles.spread_for_reward_sd` or the tile's within mode, then verified |
| sparsity | width (or sharpness) of the map's primitives | a one-dimensional root-find on the Gini of the map over the grid |
| mean level | the equaliser (default: a gain) | a one-dimensional root-find on the mean bush value of the generated worlds, over a few seeds |

- **The equaliser is an interface** (`apply(map) -> map`, plus a `solve(target)`), with the gain as the only implementation; a shift and the sophisticated transforms of the TODO below implement the same interface. The noise map has the same slot (flat only for now).
- **Tolerances** (proposals for the PI): travel time within 3 percent; mean level within 3 percent; contrast, diversity and sparsity within 5 percent of the target, each over 20 seeds (the spread across seeds is reported, since the draw of the tile centres is random).
- **Tests:** each calibrator hits a target on synthetic sessions within tolerance over the seeds; an unreachable target raises; the closed-form travel time agrees with `measure`.
- **Acceptance:** a table, for each knob, of target against realised value (mean and spread over 20 seeds) and of the other four factors' movement while it was turned (these are the numbers milestone 4 will try to remove).
- **Not in this milestone:** solving several knobs at once, anchor (c), the ranking pools (milestone 4 and later).

**Status of M3, step 1 (2026-11-17): the reachable (sparsity, complexity) region of the Gaussian family** (`scripts/map_region.py`; 6000 maps, centre anywhere with corners and edges over-sampled, short axis 0.05 to 1.5, aspect 1 to 6, angle 0 to 90; figure `docs/value_map_region.png`). The calibrator's targets are the map's Gini (sparsity) and its raw interaction (complexity); the class (additive, multiplicative, non-separable) is the log interaction, below 0.05 for an axis-aligned map.

| Gini | axis-aligned maps reach interaction | rotated maps reach |
|---|---|---|
| 0.0 to 0.2 | 0 to 0.06 | 0.02 to 0.68 |
| 0.2 to 0.4 | 0 to 0.12 | 0.02 to 0.74 |
| 0.4 to 0.6 | 0 to 0.21 | 0.04 to 0.73 |
| 0.6 to 0.8 | 0 to 0.37 | 0.06 to 0.73 |
| 0.8 to 1.0 | 0 to 0.81 | 0.16 to 0.77 |

Findings: (1) **Interaction is capped by sparsity for an axis-aligned Gaussian** (an upper curve rising with the Gini: at most 0.08 at Gini 0.2 to 0.3, 0.15 at 0.4 to 0.5, 0.28 at 0.6 to 0.7), so at low sparsity the multiplicative rung is hardly distinguishable from the additive one by the raw interaction, and it separates only where the map is sparse; (2) **a rotated Gaussian reaches any interaction up to about 0.7 at any Gini**, so the non-separable rung exists at every sparsity, and the top of the range is a ceiling near 0.75 to 0.8; (3) **complexity is not one number**: at one Gini (0.5 to 0.6, say) an axis-aligned and a rotated map can have the same interaction, and only the log interaction tells them apart, so a complexity target is a pair (class, interaction), not the interaction alone; (4) when both features must pay (shape share 0.25 to 0.75) the lowest interaction at Gini 0.4 to 0.5 is about 0.02 and at 0.6 to 0.7 about 0.05: an additive map exists at moderate sparsity but its interaction cannot be driven to exactly 0 without becoming a one-feature rule (an edge Gaussian); (5) the reference examples (Gini 0.24, 0.63, 0.50) do not lie on one Gini because the multiplicative rung needs sparsity to differ from additive. A matched-Gini ladder is possible only where the rungs overlap: at Gini 0.65, additive 0.05, multiplicative up to 0.28, non-separable 0.13 to 0.78.

**Status of M3, step 2 (2026-11-17): travel time and diversity** (`factors.travel_time_settings`, `diversity_settings`, `calibrate`, `fields`, `verify`; `factors.py calibrate <session> --travel-time S --diversity D`; 11 tests in `test_factors.py`). Measured on FOR_S1, 20 worlds per target:

| Travel time target | `tile_radius` | realised | tiles in the world | walk-only visits | contrast |
|---|---|---|---|---|---|
| 2 s | 30.3 | 2.000 ± 0 | 115 | 60 | 0.29 |
| 5 s | 49.8 | 5.000 ± 0 | 42 | 24 | 0.29 |
| 8 s | 69.3 | 8.000 ± 0 | 22 | 15 | 0.28 |
| 12 s | 95.3 | 12.000 ± 0 | 12.6 (min 12) | 10 | 0.26 |
| 16 s | 121.2 | 16.000 ± 0 | 7.2 (min 6) | 7.5 | 0.28 |

| Diversity target | `tile_spread` | realised | contrast | mean bush value |
|---|---|---|---|---|
| 0.1 | 0.036 | 0.100 ± 0.004 | 0.86 | 2.27 |
| 0.2 | 0.073 | 0.200 ± 0.008 | 0.84 | 2.26 |
| 0.4 | 0.157 | 0.400 ± 0.018 | 0.77 | 2.26 |
| 0.6 | 0.261 | 0.600 ± 0.028 | 0.63 | 2.25 |
| 0.8 | 0.454 | 0.801 ± 0.022 | 0.40 | 2.23 |
| 1.0 | refused | outside 0.003 to 0.856 for this map | | |

Findings: (1) **Travel time is exact** (the only limit is the ramp: at least 1.24 s) and independent of the map and of contrast and diversity, but **the number of patches falls with it**: below about 12 tiles (travel time above about 12 s) a world has too few patches; 120 s at 12 s per walk allows at most 10 visits, so long travel times cost patch variety and learning data. (2) **Diversity is hit to within 1 percent on average, with a spread of about 5 percent between worlds** (±0.018 at 0.4): a per-world tolerance tighter than about 5 percent needs worlds re-drawn or picked. (3) **Under the default tile modes diversity is not a knob**: bushes are drawn from the whole map, `tile_spread` is not read, and the diversity is the map's own SD (0.85 for FOR_S1); a diversity target switches the layout to between `random` and within `scatter`. (4) **Contrast and diversity are coupled by the map's variance**: contrast squared plus diversity squared is about the map's variance (0.4 and 0.77: 0.16 + 0.59 = 0.75, the variance of FOR_S1's map is 0.86 squared = 0.74), so with the map fixed a within-patch diversity target sets the between-patch contrast (0.86 at diversity 0.1, 0.40 at 0.8), and the maximum diversity is the map's SD. A contrast knob and a diversity knob in absolute units cannot both be free; what can be set apart is their ratio relative to the map's spread. (5) The mean bush value moves a little with the layout (2.21 under the default modes, 2.23 to 2.27 under `random` + `scatter`): the gain step of M3 absorbs that.

**Status of M3, step 3 (2026-11-17): the map calibrator, the proxies and the gain** (`value_maps.calibrate_map`, `map_proxies`, `solve_gain`; `factors.policy_points`; tests in `test_value_maps.py`). `calibrate_map(gini, interaction, klass)` searches the Gaussian family (differential evolution on a 41 x 41 grid, then a Nelder-Mead polish on 101 x 101; about 20 s a call) and returns a map within a tolerance of both targets, with both features paying (shape share 0.25 to 0.75), or raises ValueError naming the closest map (Gini 0.3 with interaction 0.3 aligned: closest Gini 0.39, interaction 0.10). Found: Gini 0.5 with interaction 0.10 aligned; Gini 0.4 with interaction 0.4 rotated. `solve_gain` bisects the gain until a proxy (`map_proxies` by name, or any function of a map, for example `policy_points`) hits its target.

**Does equalising a map-level proxy equalise what a forager earns?** (FIX_T0 session, 120 s, default tile modes, 20 worlds per cell; mean per-fruit pay set to 2.2 by the gain):

| Map | gain | peak bush value | median | q90 | `nearest` earns | `oracle` earns |
|---|---|---|---|---|---|---|
| additive (reference) | 1.00 | 4.0 | 2.08 | 3.5 | 703 | 795 |
| multiplicative | 2.67 | 10.7 | 0.93 | 6.6 | 730 | 1465 |
| non-separable | 1.63 | 6.5 | 1.79 | 5.1 | 728 | 1122 |
| aligned, sparse (Gini 0.7, interaction 0.25) | 2.80 | 11.2 | 0.39 | 7.4 | 753 | 1645 |

(1) **Equal mean pay equalises what the `nearest` policy earns (703 to 753, within 7 percent) but not what a skilled forager can earn**: `oracle` goes from 795 to 1645, a factor of two, so the headroom between a naive and a perfect forager grows with the sparsity and the complexity of the map. That is the "inherent difficulty" of the sessions: no gain can make both the floor and the ceiling equal. (2) **Which proxy is the anchor therefore decides who is paid alike**: the mean pay (or `nearest`) keeps a naive forager's earnings constant and lets a skilled one earn up to twice as much in a sparse session; anchoring on `oracle` keeps the best attainable score constant and makes a naive forager earn much less in the sparse sessions (`nearest` would fall to about 360 for the sparse map if `oracle` were held at 795, scaling the points with the gain); participants land between the two. Choice for the PI. (3) **The gain sets the feedback maximum**: with the mean pay at 2.2 the best bush pays 4.0 (additive), 6.5 (non-separable), 10.7 (multiplicative) and 11.2 (sparse), so `rewardFeedbackMax` runs from 4 to about 11, consistent with the expected 8 to 12 (the pick sound then has 1.1 to 3 semitones per point). (4) Solving on the `nearest` points directly (target 650, six worlds in the solve) lands within 6 percent of the target when checked on twenty worlds, the gap being the sampling of six worlds, and leaves the mean fruit pay between 1.7 and 2.0 across the maps: the proxies agree on the additive and non-separable maps and disagree on the sparse one.

### 7.4 TODOs left open on purpose

- **Value-map design:** which maps to test, and the equalising transforms beyond a gain (and the noise-map transforms), chosen once the raw maps are in mind.
- **Ranking pools relative to the value map:** methods to sample evenly across the map's reward range and gradients; ranking sets are then chosen from the map, not from today's tie-gap rule.

## 8. Risks and things that will bite

- **Ranking pools.** `ranking.py` picks the bushes of a set jointly from the reward with a tie gap and refuses a pool it cannot make ("widen the reward"). A sparse map gives many bushes near zero, which tie; high sparsity and a ranking in the same session may be infeasible. Milestone 4 checks that a pool can be built for every reachable setting, and the sparsity range may have to be limited by it. The longer-term answer (decided 2026-11-17) is to redefine the pools relative to the value map (7.4); until then this risk stands.
- **Signal against noise.** The per-fruit noise is fixed, the contrast and the gain are not, so the ratio of contrast to noise varies across sessions. That is a confound, not a bug; the realised SNR is a covariate, and whether noise should scale with the gain is a question for the PI.
- **Learning-data dose.** Long travel gives fewer patches in 120 s, so less to learn from. Intended (question 2.1.2), but report visits as a realised covariate.
- **Sparsity measured on the plane or on the bushes.** The Gini of the map is a property of the function; the Gini of the bushes depends on where tiles put them (so on contrast). The plan defines sparsity on the plane and reports the bush Gini.
- **Instruction text.** A map has no per-feature weight except the effective weights of 3; the old per-feature relevance (`RELEVANCE`, `session_features`) was removed with the ramp components (`docs/DECISIONS.md`, "Reward function: the Gaussian bump is the only term").
- **Hash.** Path B moves the engine hash once; every simulated result is stale then, as the policy says. Recorded as a decision at the time.
- **Reward noise at zero.** `max(0, round(...))` clips; a map with large flat zero regions pays 0 on most fruits, which also changes the experience (not only the numbers).
- **Tile ground level** (moisture, colour and height of the plateau) is decoration and must stay independent of value; the generator draws it on its own stream.

## 9. Open decisions (for revision)

1. **Sparsity metric.** Gini on the plane to start; alternatives (entropy of R / sum R, fraction above a threshold, the participation ratio). Does the metric need to be comparable between maps with different ranges?
2. **Complexity representation.** *Settled for the start (2026-11-17):* a sum of primitives, with the ladder additive / multiplicative / non-separable as the first families. *Still open:* richer families later (a table, a random smooth field), and whether a continuous knob between the rungs is wanted (an `interaction` parameter) and which other axes the continuous version has (number of components, weight ratio).
3. **Anchor (c).** *Settled (2026-11-17):* the points the `nearest` policy earns in a session, equal across sessions (provisionally 700 in 120 s); the `oracle` points and the map-level proxies are checks (`docs/DECISIONS.md`, "The anchor is the naive forager's points").
4. **The equaliser.** *Settled (2026-11-17):* a transform of the 2D map (default a gain), chosen at design time to equalise the points earnable across sessions, so "never normalise" no longer forbids a per-session gain (it still means no cap and no rescaling inside a session). The proxies for points earnable, and the feedback scale per session, are in `docs/DECISIONS.md`, "Reward scale per session". *Still open:* the transforms beyond a gain.
5. **Noise.** *Reframed (2026-11-17):* a second 2D map, flat (the fixed `rewardStd`) by default and for now; adjusted by the same kind of transform later; a non-flat map needs path B. *Still open:* scaled with the equaliser or independent.
6. **Contrast and diversity in reward units or relative to the mean?** (A coefficient of variation would make them independent of the gain.)
7. **Reachable region.** Is it acceptable for the design to be restricted to where all five knobs can be set independently, or must some combinations be forced?
8. **Which sessions the knobs build.** Does this live in FOR (S1 to Sn) or a new experiment code? How are the practice session and the tutorial affected (TUT keeps its own reward)?
9. **Path A before B.** *Settled (2026-11-17): milestones 1 to 3 need no engine change.* Path B is added when a family or a non-flat noise map needs it.

## 10. What does not change

The data columns, the replay and visibility rules, the harvest rule, the ranking-break design, the tutorial, the pre-drawn per-fruit rewards in the world file. `scripts/fixtures/` and `FIX_T0` are not touched; the tests build sessions from stated configurations (`synthetic.py`).
