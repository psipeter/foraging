# docs/SCIENCE.md — scientific goals and the current task design

This is the scientific record: what the project is trying to show, how the
task operationalizes it, and what is open. It describes the **current** study
only. Retired designs (the Interlude, the S1 to S7 ladder, the planned
experiments FN, RW, FI, PL, PA, the old baselines) are in `docs/DECISIONS.md`
under "Historical: ... (moved from SCIENCE.md, 2026-11-19)". For code
conventions see `CLAUDE.md`; for the reasoning behind past design choices see
`docs/DECISIONS.md`.

Entries marked **TODO(PI)** are things the code or repo can't tell us —
facts only the researcher knows. Fill or delete them; don't let them
silently harden into assumptions.

---

## Scientific rationale

### Overarching goal

To study **learning and decision making in a more complex, naturalistic
environment** than standard laboratory paradigms allow. Foraging is the
vehicle: it is a capacity humans evolved to learn about, and it can absorb a
great deal of complexity even in a simulated environment (a landscape, a
clock, many options, many features) while remaining a task participants
understand immediately.

**The present study (FOR, TUT and the pilots).** Participants forage in a valley of hexagonal tiles, each with a cluster of bushes whose shape (canopy aspect ratio) and fruit colour (a plasma ramp) predict the points a bush pays. The independent variables are the reward function (a value map over shape and colour: the number, form and sparsity of the features; "Reward complexity ladder") and the spatial arrangement (the travel time between patches, the value and heterogeneity of the tiles). Every so often, at a patch switch, a short **ranking** of a few imaginary bushes reads out the learned value function without the confound of the harvesting itself. The dependent variables are which bushes are harvested and in what order, how long people stay in a patch and how far they walk, the harvesting efficiency against benchmark foragers, the rankings, and the movement and visibility data of the logs. The platform is meant to outlast any single question.

**Hypothesis (PI, 2026-11-05; now the complexity knob of the pilots).** Adding more features, feature nonlinearity and feature interaction to the reward function makes the mapping harder to learn: learning is slower and the performance ceiling lower. The pilots (PCX Complexity, PSP Sparsity, PSC Spacing) first calibrate what participants can tell apart along one knob at a time; experiments on patch leaving and patch assessment follow, and priors and unlearning are a further experiment not yet designed.

Key constraint: attributes must be clearly visible and perceptually
independent, and reward feedback must be unambiguous.

### Four features of "naturalistic" we care about

| # | Feature | How the current build realizes it |
|---|---|---|
| 1 | **Multidimensional, continuous-valued features** | Each bush has two continuous reward attributes, shape and fruit colour, each on its own visual channel; the reward is a function (a Gaussian bump) over both. A third attribute, moisture (ground colour and height), is decoration and pays nothing |
| 2 | **Multiple potential actions at every timestep** | Hundreds of bushes in the world at all times (for example 43 tiles of 9 at a 5 s travel time); the participant can approach any, harvest any in range, or keep exploring |
| 3 | **Continuous time and space** | Free movement in a continuous 3D world; a continuous sunrise→sunset clock; travel and harvesting both cost time; no trial structure in the foraging (the ranking sets inside a session are the one exception, a held clock and a short fixed task) |
| 4 | **Multiple goals/objectives** (extendable) | *Not yet implemented* — single objective (total reward). The platform is meant to allow adding objectives later (e.g. a second resource, a state variable, a hazard) |

The hope is that these interact to produce what discrete trial-based tasks
cannot: **continuous re-evaluation of options and values** as the participant
moves and learns, an **explore/exploit tradeoff** that is part of the
experience rather than a parameter of the task, **time management** (travel
vs. harvest vs. look-around), and possibly **navigation/route planning**.
Whether the task actually engages these processes is an empirical question
the data should address, not an assumption.

### Why this is a live concern in the literature

Evidence that the project's framing is shared by other researchers — not a
claim that this specific design has been done before. Quotes are from papers
whose text I read (marked **[text]** in References); other sources were
checked at abstract level only.

- **Standard lab tasks deliberately strip out real-world complexity.**
  Wise, Emery & Radulescu (2024) review "naturalistic reinforcement
  learning" and note that "real-world environments present a substantial
  challenge for human decision-makers due to their complexity, a
  characteristic that is often not replicated in reinforcement learning lab
  tasks," and that "tasks typically used to study human RL often
  intentionally prevent prior knowledge from being useful." They call for
  work on multidimensional feature representations, large state and action
  spaces, how people segment tasks in continuous environments, and how
  people handle arbitrary goals, and recommend virtual-reality paradigms.
  Mobbs, Trimmer, Blumstein & Dayan (2018) make a parallel point for
  decision neuroscience: "relatively little attention has been paid to the
  extent to which the structure of experimental environments relates to
  natural scenarios," and "most realizations of the aforementioned paradigms
  leave substantial gaps in our understanding of the ways that decisions are
  made in the real world" — advocating "a more naturalistic stance," with
  humans in "dynamic virtual ecologies." (Features 1, 2, 4.)
- **Decision science is mostly discrete two-option choice; continuous
  decisions are the open frontier.** Yoo, Hayden & Pearson (2021) write that
  "the academic study of decision-making is mostly limited to the simple
  case of choice between two options" and advocate studying *continuous
  decisions*: ones that "involve a continuum of possible responses and take
  place over an extended period of time," during which "the response is
  continuously subject to modification," where the options available
  fluctuate with recent responses, and where "continuous decisions face a
  much more extreme version of the explore/exploit dilemma than discrete
  choice paradigms." They also discuss switching goals within hierarchical
  policies, and suggest control theory and goal states/policies may serve
  better than value-based accounts. This is the closest statement of our
  feature 3 and of the continuous-reevaluation / explore-exploit interaction.
  (Features 2, 3, 4.) Related: Gordon et al. (2021) review "embodied
  decisions," in which options are time-varying and the dynamics of action
  matter (abstract-level).
- **Foraging is an established ethological framework for exactly this.**
  Mobbs et al. (2018) and Hayden (2018) argue decision neuroscience should be
  grounded in foraging; Hayden's perspective is that economic choice derives
  from psychological processes that evolved for food search, where most
  choices are sequential accept/reject encounters rather than simultaneous
  binary comparisons. Hills, Todd & Goldstone (2008) and Hills et al. (2015)
  argue that the exploration–exploitation machinery of spatial foraging is
  shared with internal (memory/problem) search, motivating foraging as a
  window into general cognition. Human foraging behavior is not well
  described by simple model-free RL and appears to track the environment's
  average reward rate (Kolling et al., 2012; Constantino & Daw, 2015) — but
  these classic human paradigms are trial-based patch-leaving tasks, so
  continuous space and time are largely untouched by them.
- **Multidimensional continuous features are known to matter for how
  learning works.** Feature-based learning — learning values of individual
  features rather than whole options — is a general strategy in
  multidimensional environments, one that improves adaptability without
  sacrificing precision (Farashahi et al., 2017). Niv (2019) argues the hard
  part of learning is *which features/state representation to learn over*,
  via selective attention. Contextual-bandit work shows people learn
  continuous feature→reward functions and use them to guide exploration,
  with Gaussian-process-like generalization in nonlinear settings (Schulz et
  al., 2018; Wu et al., 2018). Our reward function over continuous
  attributes (a Gaussian bump over two features, shape and fruit colour,
  positioned and stretched to make additive, multiplicative or
  non-separable maps) sits directly in this line, moved into an embodied,
  continuous-time setting.
- **Richer behavior needs better-characterized tasks.** Krakauer et al.
  (2017) argue neuroscience has under-weighted careful decomposition of
  behavior; this supports building a behaviorally rich task before looking
  for mechanisms (abstract-level).

**What the literature does not give us.** The sources support
"naturalistic, continuous, multidimensional, multi-option, eventually
multi-goal" as a recognized need. None of what I read specifies a design like
this one, and Mobbs et al. do not explicitly call for navigation or
concurrent goals as such (they emphasize trade-offs among needs, competition,
and predation risk). Related naturalistic paradigms exist that I identified
but did not read — a "Photographer" naturalistic RL task (bioRxiv 2025) and
the Kalliste Decision Task — and should be reviewed before claiming novelty.
A systematic review of prior virtual/open-world foraging paradigms has **not**
been done.

**A built-in tension.** Wise et al. note lab tasks often prevent prior
knowledge from helping. We partly do the same on purpose: attributes are
chosen to carry weak priors (constant fruit count; a purple-to-yellow colour ramp
with no red; see "Fruit colour ramp" in DECISIONS), so learning of the reward function is attributable to experience.
That trades some naturalism for interpretability — a deliberate position, not
an oversight.

---

## Current design: FOR, foraging in tiles with ranking breaks (2026-11-13; sessions rebuilt 2026-11-17 and 18)

**Direction.** One foraging task in which the reward function and the spatial arrangement are set per session, and a **ranking** of a few bushes is asked for periodically *inside* the session. Harvesting earns the main points; the rankings add a bonus per correct pair. (PI discussions of 2026-11-13 replaced five planned experiments by this one; DECISIONS, "FOR ...", "Cleanup: everything is FOR", "The crosshair harvest rule" and "Ranking breaks inside the session" hold the reasoning and the rejected alternatives.)

**Questions it can answer** (two families, one design): how people learn which features pay and how well they know it (the rankings read the learned value function out, without the confound of the
harvesting itself, and the same sessions give harvesting efficiency in real time), and how they forage in patches (when they leave a tile, how far they walk, how that depends on how different the tiles are).

**What a participant meets (2026-11-19).** The Boot scene is the experiment menu. After the login (Prolific ID, consent) it lists the catalog's experiments, one line each (the length the menu quotes is `ExperimentConfig.estimatedMinutes` set by hand, TUT 4 minutes and the pilots 12 minutes each, else the foraging seconds; the menu counts foraging time, not ranking time), with Start, Continue or View code; experiments whose prerequisite is not finished are greyed. The catalog now holds **TUT and the pilots PCX, PSC and PSP**, each pilot requiring TUT; `FOR` (the template, `FOR.REQUIRES` = TUT) is built but not in the catalog, so the menu does not offer it. Each experiment is its own run; at its end the completion screen shows the points and, except for the practice experiment (TUT: no code), the completion code, an optional feedback box and the way back to the menu. A session starts with its instruction page (after a 1 s wait; the game is held), ends on a score screen, and the participant continues with Enter (Space is reserved for harvesting). Participant-facing text says "points" (never reward or bonus; the instruction page also says "money") and "bushes" (never trees); an instruction page never says "higher is better" and does not describe the mapping. The pilots and FOR show one page, "Foraging task: Harvest and rank bushes to collect **points** / The more points you earn, the more **money** you earn" (PI, 2026-11-23: it stresses pay; the "new area, new rules" note was dropped); TUT's page and hints are in "The tutorial".

**Sessions as built (2026-11-18).** FOR is one session of 180 s and TUT one of 120 s, both realised cells of the additive rung (round corner Gaussian, Gini 0.4; `design/tables/FOR.json`, `TUT.json`, realised into `design/realized/`), with a ranking after every qualifying patch leaving; FOR's corner has both features paying more when higher, TUT's has shape paying more when lower. Their gains equalise the learner's points to the rate anchor (6.25 per second): FOR gain 1.65 (world seed 9182, learner 1093 points, anchor 1125), TUT gain 1.48 (seed 9102, learner 738, anchor 750). The pilots are in "Pilot experiments".

**The world.** A valley of hexagonal tiles (`scripts/tiles.py`; tile circumradius set by the travel-time knob (FOR 69.3, an 8 s walk between clusters; TUT 49.8, 5 s), ramp between plateaus 14, four plateau heights chosen so neighbouring tiles differ, maximum elevation 9). Each tile has a
tight cluster of 9 bushes in its middle (radius 15, minimum spacing 10), so reaching a cluster means a walk from the edge of the last one (FOR 8 s, TUT 5 s). The ground (colour and height) is the moisture channel
and pays nothing. **The start (0, 0), the exact middle of the world, is the corner where three tiles meet** (their clusters are a circumradius away, the same in every world). Worlds are generated in Python from one seed
(`world.py` with `tiles.py`; `worldHalfExtent` 350, an unclimbable rocky and snowy mountain band built into the terrain geometry, no bushes on it); the lattice has a seeded rotation. The seed fixes the terrain, the skyline, the bushes and their attributes, and every per-fruit reward; Unity loads the files from `StreamingAssets/Experiments/<code>/`.

**Which bush has what** (restructured 2026-11-18). Two steps.
- The **pool**: one point of the shape-colour plane per bush site, an even cover (scrambled Halton), so every region of the value map is sampled and the world's distribution of bush values is the map's own.
- A **placement** deals the pool to the sites of the tiles (`tilePlacement`); a placement never changes which bushes exist. Two are implemented: `random` and `balanced`. `random` is the pool in random order, so every tile is about equally valuable and holds bushes of widely varying value, and the decision is *which bushes of a tile to take*, not which tile. Optional checks redraw the placement (`tileCoverageMin`: a neighbourhood spans the plane; `tileStartSpreadMin`: the three start tiles differ). **`balanced`** deals the pool best first in bands of one bush per tile, each to the tile with the least total so far, so every tile holds one bush of each value band: tile totals (the sum of the 9 bushes' values, points after the session's gain) differ by about the last band's range, and each tile keeps the pool's spread of values (near-zero contrast between patches, similar within-patch SD). `tileSumTol` (points, 0 = off) redraws until no tile's total is further than that from the mean tile total. Checked on 40 worlds each of FOR_S1 and TUT_S1: the largest deviation from the mean tile total was 0.2 points (1% of a tile's 18 to 22 points; random placement: median 45 to 56%), contrast 0.005 (random 0.31 to 0.34), within-patch SD 1.5 to 1.8 (random 1.4 to 1.7).
- Since 2026-11-18 every shipped session (FOR, TUT and the pilots) uses `balanced` with `tileSumTol` 1.0 (`design/FOR.py`'s `TILE_FIELDS`), and the cells were re-realised on balanced worlds (`factors.PLACEMENT`). The default condition is near-zero contrast between patches and similar within-patch variance; patch contrasts and levels of variance are for later studies. **TODO: the more advanced placements** (the earlier between modes `graded` and `bimodal` and within modes `scatter` and `gradient` were deleted with the restructure) to be recreated to fit this design: value-sorted placement, a mix with one number for the share of the value variance that lies between patches (so that contrast and within-patch diversity become explicit knobs), a smooth spatial field of patch means, a gradient inside a patch. Until then within-patch diversity is the map's own spread and is measured, not set.
- **The reward** is the session's value map (since 2026-11-17 a Gaussian bump, the additive rung: a wide corner Gaussian, in FOR's prototype both features paying more when higher, both alike, peak 4 before the gain; per-fruit noise 0.6, fruit count 10, never normalised; "Reward complexity ladder").

**Is leaving a tile early the right policy?** `scripts/tile_calibration.py` (an oracle forager through the simulator on tile worlds) shows that the incentive to leave comes from the within-tile decline relative to the differences between tiles. **Measured on the pool-and-placement worlds (2026-11-18, 20 seeds, `tile_calibration.py FOR_S1|TUT_S1 --seeds 0-19`):** FOR_S1 (180 s, 8 s travel): the best top-k is top-5 (1372 points; top-4 to top-6 within 3%), top-1 loses 42% and top-9 13%; the best threshold is thr-60 (1421, 4.4 bushes per visit, +19.7% over exhausting every tile), thr-90 loses 33% and thr-10 11%. TUT_S1 (120 s, 5 s travel): top-4 is best (top-3 to top-5 within 3%), top-1 loses 35% and top-9 17%; thr-70 is best (+25.6% over exhaust), thr-90 loses 24% and thr-10 17%. Both shapes are an inverted U with a clear loss at each end (the shape check, `tile_calibration.profile_check`; the best policy is the best of the heuristics, a lower bound on the optimum). The measurements of the earlier layout (radius 45, patch centres and scatter: +9 to +11%) are history, and a later re-run (2026-11-17) did not reproduce them (DECISIONS, "Historical: the tile-leaving calibration ..."). The pilots' benchmarks (`scripts/patch_foraging.py`) are in "Pilot experiments".

**Harvesting.** A bush can be harvested while it is within the range (7 plus its canopy radius from the canopy's edge) **and a hidden circle around the crosshair touches its canopy**: `crosshairRadius` Z
(degrees of view angle; default 7, about five times the drawn crosshair's radius) against the canopy's real 3D shape, so looking above or below a bush does not count; a harvest in progress releases at 2 Z. A thin
grey crosshair is always drawn (`crosshairAlpha`, default 0.25) and brightens on a bush that can be harvested; on a harvestable bush its bars fade into the **harvest ring**, the fraction of that bush's fruit left (it is the crosshair's, not a ring above the bush). Z = 0 restores the old 35 degree cone of yaw. Holding Space collects one fruit every `fruitHarvestDuration` (0.2 s, so 10 fruits = 2 s a bush; the fruit nearest the camera first); walking is locked while Space is held, looking stays free; leaving the circle pauses the harvest (hint: "Look toward the bush to keep harvesting") and releasing Space ends the bout, a fresh press starts the next. Progress through the fruit in hand is kept on the bush, so a bush can be returned to. An exhausted bush stays as a landmark and obstacle but eases into a "spent" look (shrunk to 70%, drab tint), so depleted bushes are distinguishable from afar; there is no external record of which bushes are left beyond that. Approaching bushes glow gradually (a rim light, `CanopyRim`: a soft glow that grows with approach, plus a thin crisp edge line on the selected bush; the glow never reveals reward); a "Hold [Space] to harvest" pill appears on a harvestable bush.

**Ranking breaks.** (Decisions: "Ranking breaks inside the session", "The ranking stage", "A ranking after every patch transition", "Ranking points: a mode, and the mean value of the pair".)
- **When.** After every patch leaving that qualifies. FOR and TUT since 2026-11-18: `rankingEvery` 1 and no `rankingLeavings` schedule, so every transition asks for a ranking and travel time carries a constant cost of one ranking (before 2026-11-18 the schedule was the 1st, 2nd, 4th and 8th). A leaving is a patch switch, the nearest tile changing. It qualifies when: settle depth 0, at least `rankingMinBushes` (1) different bushes harvested since the last ranking ended (since the session began, before the first), none in the last 10 s (`rankingLastSeconds`), no cooldown (`rankingCooldown` 0). A crossing that does not qualify is ignored and does not wait. Leavings are numbered from 1 through the whole session. A resume does not restore the bushes harvested since the last ranking, so the next ranking after one waits for one more bush. A schedule, when set, picks the leavings that ask; with none, every `rankingEvery`-th switch. The menu's length counts foraging time only.
- **The stage.** The world's bushes fade to grayscale (0.25 s) and cannot be aimed at (the terrain greys 0.6 of the way). A set of 5 ranking bushes grows on an arc of 84 degrees at 16 units in front of the player, standing on a small bumpy **disc below the player's ground** (3 units down, drawn by an overlay camera so the camera is never moved; `RankingDisc`, DECISIONS "The ranking stage"), and the player, standing still, harvests them from most to least points (any bush in view, a started harvest is finished, 0.05 s a fruit, no outcomes shown). The ranking crosshair circle is 1 degree (`rankingCrosshairRadius`), so two bushes of a set (at least 2 degrees apart in the view) are never both touched. The session clock is held (the main clock goes grey) and a second clock counts the set's 20 s down; the player is free to walk again the moment the last bush is done. `rankingSets` sets per break (1 in FOR and TUT). The helper text on screen is "Rank these bushes from most to least valuable".
- **The pool.** Sets come in order from a pool of 30 per session (`rankingPoolSets`; 12 before 2026-11-18, raised because every transition now asks and the pool wraps; `ranking.py pool`), chosen jointly so the true values form a ladder (no ties) and the bushes spread over the feature plane.
- **Points.** A set has one pair per two of its bushes (10 for 5; true values closer than the tie tolerance are left out). A pair is correct only when both bushes were ranked and the first one ranked is worth more, so a bush left unranked when the 20 s run out counts every pair it is in as incorrect. `rankingBonusPerPair` (4, provisional) times a pair's weight per correct pair (`rankingPointsMode`: `pair` weighs every pair 1; `pair_mean_value`, the mode of FOR and TUT since 2026-11-18, weighs a pair by the mean of its two bushes' true values, so a miss among the best bushes costs more than among the poor ones and the ranking is worth about three times as much; `ranking.rankings_to_points` is the rule). A practice session (TUT) scores 0 for its sets.
- **Feedback is sealed.** During play a scored set shows a sealed "+???" popup (the harvest popup's motion, the score plate punches, its own chime), the same whatever the set earned, so the ranking gives no feedback on the values. The end screen shows the combined total in the middle with the foraging and ranking parts smaller on either side; the ranking part and the total count up together from the foraging score. A session's points are `foraging_points` and `ranking_points` of its row; the total is their sum.
- **TODO(PI):** the bonus rule, the size and number of sets, the instructions for the first break (which transitions ask was decided 2026-11-18: every one).

**Recording.** The log's `t` runs through a break; `rank_break_start` / `rank_break_end` events bound it and each set is one `ranking_sets` row of the foraging session plus `rank_set`, `rank_go`, `rank_set_start`,
`rank_pick`, `rank_set_end` events (`docs/ONLINE_DATA_PLAN.md`, "Ranking breaks"). `replay.py` re-derives the harvests of break windows and of the crosshair rule from the trajectory.

**Status.** Built: the tiles world with the pool and placement, the calibration and benchmarks, the crosshair rule, ranking breaks (trigger, stage, clocks, fade, scoring, logging, replay, resume, pool), the template session `FOR_S1`, the tutorial `TUT`, and the pilots PCX, PSP and PSC. Not built: further FOR sessions beyond the template, the advanced placements (above), instructions text for the rankings beyond the tutorial's hints, a difficulty score. Not play-tested with participants: no data exist ("Data").


### The tutorial (TUT, 2026-11-16)

One practice session, `TUT_S1`, in its own experiment that must be finished before the later experiments unlock (not paid, not in the menu's total, no completion code). **World:** FOR's tile geometry at a travel time of 5 s (FOR's is 8 s, 180 s), the world chosen by the cell search (`design/tables/TUT.json`, seed 9102), 120 s, ranking breaks on (one set per break).
**Reward:** shape **inverted** (a lower shape value pays more) plus colour (higher pays more), alike (since 2026-11-17 a round corner Gaussian at FOR's baseline knobs, realised from `design/tables/TUT.json`), where FOR_S1 pays both alike and both increasing; so what is learned in the practice (heavy shape, low is good) is wrong in FOR,
and the hints say only that "shape and/or color determine how many points you get". **Mechanism:** the Controls screen, then popups fired by what the participant does (`UI/TutorialHints.cs`, a hints text file), each a pause popup that
fades in and out; every one carries a small blue "Tutorial" label (`SessionConfig.sessionLabel`). The popups, in order:

| When | Title | Text |
|---|---|---|
| 1 s after the session starts (the game held) | Controls | In this study, you gather **points** by harvesting fruit from bushes / Walk up to a bush and hold [Space] to harvest it |
| the first harvest ends (`@bout 1`) | Harvesting | Harvesting this bush earned {points} points. / You can **stop** harvesting a bush anytime, or **return** to a bush later / Try harvesting a different bush |
| the second harvest ends (`@bout 2`) | Features | Harvesting this bush earned {points} points. / A bush's **shape** and/or **color** determine how many points you get / Try harvesting a few more bushes, then move to a new area |
| 0.25 s after the first ranking's bushes have grown (`@ranking_start 1`) | Ranking | **Rank** these imaginary bushes based on what you learned / Do this by harvesting bushes from **most** to **least** valuable |
| the first ranking ends (`@ranking_end 1`) | Ranking | You earn **points** for ranking bushes correctly / These **hidden** points are added at the end of the session |
| the first moment 60 s or fewer of foraging time are left (`@time_left 60`; the session clock pulses yellow while the hint is up) | Scoring | You have a limited **time** in each session / Try to learn and harvest efficiently |
| the first moment 30 s or fewer of foraging time are left (`@time_left 30`, after Scoring at 60) | Pausing | You can **pause** the game at any time / The timer stops while you are paused / Press [Escape] to pause (the hint ends when the participant has paused and, in a browser, clicked back in; the pause screen says "[Click] to continue") |

A controls bar (`design/TUT.py` `CONTROLS_REMINDER`, "Mouse: look. W / S: walk. Space: hold to harvest. Escape: pause", drawn as "Key: action" pairs by `InstructionsPanel`; `SessionConfig.controlsReminder`) stays at the bottom of the screen for the whole tutorial; FOR sets none. The ranking's own helper text (on screen during a set) is "Rank these bushes from most to least valuable". **End screen** ("Tutorial complete"): the total in the middle, the foraging points (green title) and the ranking points (orange
title) on either side with the captions "points earned from harvesting bushes" and "points earned from ranking bushes", and centred under the total the note "**Payment** is based on total points earned"; the three numbers count up
together from zero. The ranking set's outcome is sealed during play (a centred, larger "+???" and a chime, `DECISIONS`, "Ranking feedback sealed"). **Not built:** hint triggers other than the five above (`bout`, `patch_switch` (unused since 2026-11-18), `ranking_start`, `ranking_end`, `time_left`; the rest were removed, DECISIONS 2026-11-16; a resumed tutorial skips the hints already shown),
non-modal hints, any guarantee that a participant sees a ranking (it comes at a patch switch); the wording is the PI's and still open to change. See DECISIONS ("The tutorial" and its addenda) for the reasoning.

### Reward complexity ladder (PI, 2026-11-17)

The reward function of a session is a **value map** R(shape, colour) over the unit plane, and its complexity is a position on a ladder of three rungs, all one **Gaussian bump** (a placeable, stretchable, rotatable primitive; `scripts/value_maps.py`). Rationale and rejected alternatives: `docs/DECISIONS.md` ("Reward complexity ladder"); how it plugs into the session factors: `docs/SESSION_FACTORS_PLAN.md`.

| Rung | The map | interaction | log interaction | nonlinearity | Gini | shape share |
|---|---|---|---|---|---|---|
| additive | a **wide corner Gaussian** (corner (1, 1), spreads 0.63 along shape, 0.78 along colour); a ramp pair is not a primitive | 0.03 | 0.00 | 0.05 | 0.24 | 0.58 |
| multiplicative | an **axis-aligned, stretched** Gaussian (centre (0.55, 0.45), width 0.15, aspect 1.5, angle 0) | 0.20 | 0.00 | 0.97 | 0.63 | 0.39 |
| non-separable | the same Gaussian **rotated** and more stretched (aspect 3, angle 45 degrees) | 0.61 | 0.84 | 0.94 | 0.50 | 0.50 |

Figure: `docs/value_map_examples.png` (made by `scripts/value_map_examples.py`; the parameters above are a proposal for a reference guide, not a design). **How separability is measured** (computed on a 101 x 101 grid of the map): `interaction` is 1 - R^2 of the best additive fit f(shape) + g(colour) to the map (0 = a sum of a function of each feature); `log_interaction` is the same fit to log R where R is at least 1 percent of the maximum (0 = a product of a function of each feature: exactly 0 for any axis-aligned Gaussian, wherever it lies and however stretched, and growing with rotation); `nonlinearity` is 1 - R^2 of the best plane. Read together: additive = interaction near 0; multiplicative = log interaction 0 and interaction above 0; non-separable = both above 0. Separability falls up the ladder (interaction 0.03, 0.20, 0.61).

**The additive rung in the design** (PI, 2026-11-17): the Gaussian sits exactly on a corner and is round or stretched 2:1 or 3:1 along shape or colour (a nuisance, with the corner), its width solved for the Gini; the interaction that results is 0.06 / 0.16 / 0.29 round at Gini 0.3 / 0.5 / 0.7, 0.02 / 0.07 / 0.20 at 2:1, 0.005 / 0.02 / 0.10 at 3:1, and the shape share 0.5, about 0.25 or 0.75, about 0.15 or 0.85 (`docs/DECISIONS.md`, "The additive rung is a corner Gaussian stretched").

**Caveats to keep in mind.** Sparsity (Gini) and separability are entangled through the widths: a wide corner bump is near a plane (Gini 0.24), a narrow one sparse, so the Gini is not matched across these three examples and a comparison of the rungs is confounded with sparsity until the sparsity step of the calibration (plan, M3) equalises it. A stretched axis-aligned Gaussian loses interaction as it lengthens (width 0.2: raw interaction 0.19 round, 0.04 at aspect 2, 0.01 at aspect 3: a bump that long crosses the whole range of one feature and is nearly a one-feature rule), so the multiplicative rung that differs most from additive is the round or mildly stretched one. A corner Gaussian is near additive only when wide (spreads of about 0.5 or more; raw interaction below 0.03 with a range of 3.3 to 3.6 instead of 4); wide along an edge it is a one-feature rule. The additive, multiplicative and non-separable maps are built by `value_maps.additive`, `multiplicative`, `nonseparable`, each with the nuisance (corner or centre, tilt, which feature has the long axis) drawn from a seed.


### Pilot experiments (PI, 2026-11-18)

Short pilots calibrate what participants can tell apart along one knob: **PCX** "Pilot: Complexity", **PSP** "Pilot: Sparsity", **PSC** "Pilot: Spacing" (the travel time between patches, 3, 6 and 9 s, with a different round bump in each session, longer sessions and a larger gain for the longer travel; the participants are not told what varies). Each is three sessions of the foraging task, low, medium and high of the knob, in that fixed order (fatigue is taken to be minimal in a short pilot), after TUT, 180 s (PSC 180, 200 and 220 s), rankings after every patch transition as in FOR, travel time 5 s (PCX, PSP), a world seed per session, balanced patches (`tilePlacement` balanced, `tileSumTol` 1). Designed with `scripts/pilot_report.py` (`preview` and `report`; the figure and the span-and-hold check are in `docs/pilots/PCX.png` and `PCX.txt`), tables in `scripts/design/tables/`, realised cells in `scripts/design/realized/`. PSP is realised (`docs/pilots/PSP.txt`): round Gaussians at unique centres, Gini 0.4, 0.5 and 0.6, travel 5 s. PSC is realised (`docs/pilots/PSC.png`, `PSC.txt`, `agents.md`; redesigned 2026-11-23, DECISIONS, "Pilot Spacing (PSC): a fresh round bump per session, longer sessions, per-session gains"): a round Gaussian at Gini 0.5 (interaction 0.13 to 0.15, nonlinearity 0.38 to 0.41) centred at (0.71, 0.71), (0.21, 0.58) and (0.58, 0.21), the corners of a triangle of radius 0.3 around the middle, rotated 60 degrees from PSP's, so each session needs fresh learning; travel 3, 6 and 9 s (79, 33 and 18 tiles), sessions of 180, 200 and 220 s so that the number of bushes harvested stays about equal, gains 1.31 (the calibrated one), 1.42 and 1.51 (the learner's points equal), worlds 9610, 9714 and 9805 (picked from 20 candidates per session so the optimal bushes per patch rise evenly). On 20 unselected worlds the learner earns 1133, 1131 and 1134 points and harvests 46.6, 47.8 and 47.7 bushes, 5.7, 6.8 and 6.9 per patch; the mvt benchmark earns 1423, 1382 and 1346 points at 2.56, 2.90 and 3.30 bushes per patch (2.89, 3.08 and 3.62 when it believes a 1.0 s step inside a patch, as participants take it). The mean bush value rises with the gain (1.75, 1.87, 1.98), which `pilot_report.py` flags by design. The best bush may pay at most 9 (`factors.MAX_PEAK`; a few fruits of the best bushes can pay over 9: measured, none in PCX).

**PCX (Complexity): Gini 0.55, travel time 5 s, 43 tiles.** The value maps (a Gaussian bump over (shape, colour), height 4 times the gain; `width` along shape, `widthColor` along colour; realised 2026-11-18):

| Session | Rung | Centre (shape, colour) | Width (shape, colour) | Angle | Gain | Peak | Gini | Interaction | Log interaction | Nonlinearity | Shape share |
|---|---|---|---|---|---|---|---|---|---|---|---|
| PCX_S1 | additive: corner (1, 1), stretched 2:1 along shape | (1.00, 1.00) | (0.621, 0.310) | 0 | 1.666 | 6.7 | 0.55 | 0.09 | 0.00 | 0.14 | 0.29 |
| PCX_S2 | multiplicative: axis-aligned, centre limited to shape 0.12 to 0.30 and colour 0.65 to 0.85, interaction asked 0.18 | (0.120, 0.650) | (0.341, 0.219) | 0 | 1.722 | 6.9 | 0.55 | 0.18 | 0.00 | 0.43 | 0.36 |
| PCX_S3 | non-separable: rotated, centre limited to 0.4 to 0.6, interaction asked 0.40 | (0.498, 0.585) | (0.809, 0.137) | 21.2 | 1.632 | 6.5 | 0.55 | 0.40 | 0.51 | 0.92 | 0.28 |

World seeds 9201, 9202 and 9203 (tile radius 49.8, 5 s travel); feedback maximum 7; fruit noise 0.6. The knob (interaction) rises 0.09, 0.18, 0.40 and nonlinearity 0.14, 0.43, 0.92; Gini, travel time and the patch totals are held, the mean bush value is not (1.79, 1.93, 2.23; the gain holds the learner's points, 1094, 1133 and 1194 on the cells' own worlds, 1118, 1145 and 1131 on the 40 check worlds, against the anchor 1125). The patch-foraging benchmarks (`scripts/patch_foraging.py`, known values, average costs) on the cells' own worlds: dp_finite 1375, 1495, 1721 points, dp_average and mvt 1344, 1502, 1691, mvt_running 1342, 1469, 1683 (nearest 843, 930, 1082; learner 1094, 1133, 1194; oracle 1347, 1452, 1659); they take about 2.3 to 2.8 bushes of the 9 per patch (dp_finite 2.38, 2.46, 2.83; mvt_running a little more, 2.58, 2.67, 3.09), and over 20 worlds of each cell they are within about 1 percent of the best simple threshold policy. The beam planner scored 25 to 35 percent below these and is no benchmark. The earlier trials: at Gini 0.4 the additive and multiplicative maps had the same interaction (0.10); at Gini 0.5 the multiplicative bump sat at an edge; an axis-aligned Gaussian with an interior centre has little interaction at Gini 0.5 (at most 0.16), so the Gini went to 0.55 and the multiplicative centre toward an edge.

---

## Task design

- **Session:** a fixed duration per session (FOR and the pilots 180 s, TUT 120 s), the
  second part of a day cycle: the session starts when the sun is `sunStartElevation` (30°) above the horizon on the morning
  side and ends at dusk, when it is `sunEndElevation` (10°) on the afternoon side (same calculation for both; the mountain
  skyline is about 3–22° from the valley, median 9°; the 30°/10° pair is a tuned-by-eye trial, since equal values did not look symmetric). The sun follows a real solar path (`sunLatitude` 40°,
  `sunDeclination` +12°: a start at 30° elevation, a peak of about 62°, rising toward the east-south-east and
  setting toward the west-north-west, moving faster near the horizon; `sunAzimuthOffset` rotates the path). Every session
  plays this same path, mapped onto its length, so a shorter session plays it faster; a ranking break holds the clock (and the sun). Light and sky take hue from
  physics (the sun's colour is its transmittance through the atmosphere, warm white at noon and orange near the horizon; the procedural
  sky reddens from the sun's direction with a constant neutral tint) and brightness from curves of the sun's elevation (light intensity,
  ambient-probe multiplier, sky exposure), plus an exposure ramp (post-exposure, in stops) that darkens everything on screen toward
  dusk. Important:
  the terrain and fruit shaders ignore the sun's colour and intensity (terrain lighting is `0.15 + 0.85 * shadow * N.L`, with white light
  and a black ambient term; fruit has an ambient floor), so the hue and intensity curves act on the canopy, the sky and the ambient
  probe, and the terrain darkens through the sun's direction plus the exposure ramp. Movement costs time (fixed player speed 11.25, the same in every session);
  harvesting costs `fruitHarvestDuration` seconds per fruit (0.2 s, so 10 fruits = 2 s per bush; the harvest rule is in "Current design"). Goal: maximize total points (harvest plus ranking bonus).
- **Harvest presentation:** the rim-light glow grows as you approach a bush, in proportion to horizontal distance from the canopy edge (glow begins 20 units out,
  full at the range 7) and to how directly it is in front of you (full within 25° of straight ahead, none past 45°; yaw only, after subtracting the bush's angular radius); the numbers are those of the
  cone-era build and the crosshair rule may have replaced them (see the glow fields of `SessionConfig`). The glow never reveals reward. +X popups appear in a central row of slots (a fixed
  cycle, so concurrent popups never overlap), and the score updates per fruit. Optional `harvestLookResistance`
  (default 0, off) slows mouse yaw to zero as you turn away from the bush.
- **Camera (all sessions):** first person — mouse looks (yaw + pitch), W/S walk
  forward/back along the view direction, no strafing. Eye height, vertical
  field of view, and mouse sensitivity are `SessionConfig` fields; the
  metadata JSON records the camera's FOV, pose, and clip planes. See DECISIONS.
- **Instructions:** the file shown before a session is `SessionConfig.instructionsFile` (a path under StreamingAssets, `Experiments/<code>/instructions_S<n>.txt`; placeholders `{part}` `{total}`); the tutorial's popups come from its `hintsFile`. The wording never says "higher is better" and does not describe the structure of the mapping.

### Reward feedback (HUD and audio)

Each harvested fruit gives: a "+X" popup in a fixed central band of the screen (pale gold with a dark outline, pops in
with an overshoot and wobble, rises and fades); the score counts up with a brief flash and punch; a short
synthesized blip whose pitch rises with the reward; and a small burst of spheres in the fruit's own color. An
exhausted bush plays a soft two-note chime. The timer sits in a matching plate; it has no bar and no end-of-session warning
(deliberately kept plain).

Reward-dependent salience is a **scientific parameter**, not decoration: the number is always shown, but popup
size/brightness (`rewardSizeScaling`, `popupExtraScale`) and pitch (`pitchSemitoneRange`) can scale with the
per-fruit reward, up to `rewardFeedbackMax`. This adds a second, graded cue next to the number; set the scaling
to 0 (and the pitch range to 0) for identical feedback on every fruit. Feedback colors are pale and near-neutral
so they do not read as part of the fruit hue axis. Defaults (full scaling, an octave of 12 semitones since 2026-11-17: DECISIONS "Reward scale per session") are untuned starting
values; record the values used when collecting data (they live in `SessionConfig`).

Popups never overlap: `HarvestUI` has `popupSlotCount` (5) side-by-side slots, `popupSlotSpacing` (120 px) apart, fanned out
around `popupOffset` (order: centre, right, left, farther right, farther left). Each new popup takes the next free slot in
that fixed cycle; a slot is busy until its popup fades, so it holds for any per-fruit time or popup duration. Slot choice
is deterministic and independent of the reward and the bush, so position is not an information channel.

### Ambient audio

Passive, always on, and identical in every session: footsteps while walking (one step per
`footstepStride` world units actually walked, so none when blocked or while harvesting; five recorded grass
steps chosen at random with small pitch/volume jitter), a very quiet constant cicada bed, and occasional
birdsong (three synthesized whistle/trill patterns at random gaps and stereo pan). Volumes and timing are
`SessionConfig` fields (`footstepVolume` 0.06, `bedVolume` 0.0165, `birdVolume` 0.03, `footstepStride`,
`birdIntervalMin/Max`; 0 disables a layer). History: the first version was too loud (all cut 70%, then birds a
further 50% and footsteps 25%), a synthesized wind bed was dropped (it sounded awkward, and wind with nothing
visibly moving felt disembodied), and a night-cricket loop was replaced by daytime cicadas.

**Sources.** Both recorded layers are CC0 (public domain); the licence text and a source note are kept beside the
files in `Assets/Audio/Ambient/`.
- Footsteps: the five `footstep_grass_000–004.ogg` recordings from Kenney's **Impact Sounds** pack
  (https://kenney.nl/assets/impact-sounds), unmodified. If no clips are assigned, synthesized steps are used.
- Cicada bed: **"Cicadas" (ID 3002)** by Clarisse on BigSoundBank
  (https://bigsoundbank.com/cicadas-s3002.html, CC0 / public domain, "free and royalty-free"). Changes: resampled to
  44.1 kHz, the last 3 s crossfaded into the start for a seamless loop (45.5 s), normalized to a 0.7 peak, encoded as
  Ogg Vorbis (579 KB; the 14 MB source WAV is deliberately not in the repository). Two copies play at once (pitch 1.0
  and 0.965, offset by half a loop). Measured: energy 4–12 kHz (peak ~7 kHz), stationary level (±15%), uncorrelated
  left/right channels. That is above the reward blip (660–1980 Hz) and the birds' band (2.6–4.2 kHz), so it should not
  mask either; it is, however, tonal-hissy and potentially fatiguing, and laptop speakers reproduce 8–12 kHz poorly.
- Birds are synthesized in code at startup (`AmbientAudio`) and use no external files.

Ambient sound must stay **uninformative about reward**: it does not vary with bush attributes, moisture,
elevation, terrain, proximity to bushes or time of day, and the bird positions are random. The cicadas are constant
and played in every session regardless of the sun's position. All ambient volumes sit below the reward cues
(`sfxVolume`).

### Attributes and their visual channels

Each bush has three attributes in [0, 1], each on its own visual channel. **Moisture is not a reward feature in any current session** (since 2026-11-05): the ground colour and elevation are
decoration that makes the world look natural; shape and fruit colour are the two reward features.

| Attribute | Visual channel | Ecological level | Prior strength |
|---|---|---|---|
| **Shape** | Canopy aspect ratio (squat/wide → tall/narrow) | Tree | Weak |
| **Color** | Fruit colour (plasma ramp: blue-purple → magenta → orange → yellow, equal perceptual steps) | Fruit | Weak |
| **Moisture** | Ground color + terrain elevation | Environment | Weak–moderate |

- `shape` and `color` of a bush are the pool's point of the plane (an even cover, scrambled Halton; "Current design"), independent of position until a placement deals them to tiles.
- `moisture` is **not** drawn per bush: it is the terrain's moisture at the bush's position, and the tiles' plateaus set it (`tileMoistureLevels` 4: four ground colours and four heights, maximum elevation 9), so bushes on a higher plateau sit on higher ground (elevation is
  `(1 − moisture) × terrainMaxElevation`). It earns nothing.
- Options that default on: `shapeVaries` / `colorVaries`. The default shape axis is the canopy's aspect ratio (an ellipsoid, squat/wide to tall/narrow) and the default colour
  ramp plasma (an alternating-feature-set design, ABAB, was tried and archived in `archive/abab/`; see DECISIONS).
- **Prior management:** fruit count is constant across bushes (no count-based
  prior); fruit colour uses the plasma ramp (blue-purple, magenta, orange, yellow; no green, and it passes through pink and coral, so the red ripeness association is not
  avoided, see DECISIONS, "Fruit colour ramp: plasma"). Fruits are unlit so hue is always readable;
  canopy and terrain respond to the day/night lighting.
- Fruits are distributed over the canopy with a Fibonacci/sunflower spiral
  with per-tree seeded jitter.

### Reward system

`R_bush` is the session's **value map** over (shape, colour): the sum of its Gaussian bumps (`RewardBump`; a centre, a spread along each axis, an angle that turns it, a height), with **no
normalization** (a deliberate research decision, not an oversight). The bump is the one primitive; the reward complexity ladder (additive, multiplicative, non-separable) is positions in its parameters ("Reward complexity ladder" above; specification and descriptors in `scripts/value_maps.py`). Moisture never pays. (Until 2026-11-17 the reward was also a sum of per-feature components (Linear, InvertedLinear, GaussianPeak, InvertedGaussian, Constant), product terms, two-factor terms and a random per-bush value; they were removed, `docs/DECISIONS.md`, "Reward function: the Gaussian bump is the only term".) Each fruit's reward is an independent draw,
`max(0, round(N(R_bush, rewardStd)))`; the harvest pays the sum over the
tree's fruits, shown as floating numbers rising from each fruit and a
running score.

---

## Data

The logs are designed so that a participant's session can be **replayed exactly** (path, camera angle, every
harvest) in the world they played, and fed to mathematical or neural agents as trajectories. Online participants' data go to a
Supabase (Postgres) database through five Edge Functions (participant-start, run-start, append, run-finish and the optional end-screen feedback; one run per participant and experiment); every run also writes a local copy under
`ForagingData/<run id>/<session:00>/`, the same tables as files. The schema, the upload protocol and the resume rules are in
`docs/ONLINE_DATA_PLAN.md`; the tables are:

| Table (local file) | Content |
|---|---|
| `trajectory` (`trajectory.csv`) | One row per rendered frame: `t` (unpaused session seconds; it runs through ranking breaks, whose clock is held), `x, z`, `yaw`, `pitch` (degrees), `keys` (bitfield: 1 W, 2 S, 4 Space held), quantized (time 1 microsecond, position 0.01, angles 0.02 degrees) and stored as compressed chunks. Height is the terrain's at (x, z) (a ranking stage's bushes log their own ground height `y`); eye height is in the config. The pose is what `HarvestManager` reads that frame (interpolated player position, camera yaw). |
| `events` (`events.csv`) | `seq, t, real, type, tree_id, k, reward, running_total, payload` (JSON; `tree_id` is the bush's id). `real` is unscaled seconds. Types: `session_start`/`session_end`, `pause`/`resume` (payload `reason`: instructions, upload or pointer, joined by `+`), `focus_lost`/`focus_gained`, `harvest_press`, `harvest_pause`/`harvest_resume` (the target left/re-entered the range-and-crosshair rule mid-bout), `fruit` (one per fruit: bush, `k` = its index among the fruits taken from that bush, reward, running total), `harvest_release`, `instructions_shown`/`instructions_dismissed`, `hint_shown`/`hint_dismissed` (tutorial hints: id `trigger:n`), the ranking events `rank_leaving`, `rank_break_start`/`rank_break_end`, `rank_set`, `rank_set_start`, `rank_go`, `rank_pick`, `rank_set_end`, `session_resume` (the participant came back to an interrupted session) and `run_modes` (a reduced development run). |
| `ranking_sets` (`ranking_sets.csv`) | One row per ranking set (the bushes as JSON in the last column, its pairs and `points`). |
| `sessions` (`session.json`) | The full `SessionConfig`, world file and sha256, build commit and a `dirty` flag, camera, display, frame statistics, the design (`designJson`: the value map and its descriptors), `foraging_points` and `ranking_points` (the total is their sum), `completed`. |
| `runs`, `participants`, `pid_registry`, `consents`, `experiments`, `release_experiments` | The run (experiment, platform, build commits, status), the participant, the participant's ID (kept apart from every analysis table), the signed consent (once per participant and text version) and the experiments (title, prerequisites, completion code) a build offers. |

Harvest bouts are derived (`scripts/replay.py`), not stored. The format from before the online system (`harvests.csv`, `manifest.json`, `interlude.csv`)
is no longer readable; no data of it exists. (The Interlude's tables and events, removed 2026-11-14, are in DECISIONS, "Historical: the Interlude's data tables ...".)

**Why this set is sufficient.** Harvest outcomes are a deterministic function of (trajectory, world): the fruit timer,
range and crosshair rule and per-bush carry-over use only position, yaw, pitch and `t`, and each fruit's reward is the pre-drawn
`fruit_reward[bush][k]` in the world file. The world is pinned by sha256 and archived by the logger in
`ForagingData/_worlds/` (and registered on the server). `scripts/replay.py` re-derives every `fruit` event from the trajectory and checks it against
the log (`./venv/bin/python scripts/replay.py <folder or id>`); it also resamples a session to a uniform time grid
(`steps`) for agents. Logging state per frame rather than inputs avoids having to reproduce Unity's physics. **Reward-noise stream (resolved):** the noise a fruit pays is a fixed property of
the world, so a participant's draws can be reproduced from the file; the remaining uses of the global
`UnityEngine.Random` are cosmetic (the fruit-colour bursts in `Tree.cs`) and a fallback in `HarvestManager` for a
bush with no stored rewards; ambient audio uses its own `System.Random` so it never touches that stream. **What the participant could see**
is derived, not logged: `scripts/visibility.py` (`visible_bushes(log, dt=0.1)`, or the CLI) rebuilds it per step from the trajectory,
the world's terrain and the camera (eye = terrain + `eyeHeight`, FOV and clip planes from the manifest, aspect from the logged display
size). A bush counts as visible when part of its camera-facing upper canopy (a half-buried ellipsoid; height from the shape attribute)
is inside the view frustum and the line of sight clears the terrain. Per visible bush it returns `visible_fraction`, egocentric
`azimuth` (+ right) and `elevation` (+ up), `distance` and angular `width`/`height` (threshold on those for resolvability; there is no
built-in distance cutoff beyond the far clip). Not modelled: bushes hiding other bushes, fruit visibility, fog; a ranking stage's bushes are drawn by an overlay camera over the world, so the terrain and bush occlusion `visibility.py` applies to them under-reports them.
World files are written by `scripts/world.py`, so regenerating them gives a new hash; old logs keep their archived copy.
Format notes live in `docs/ONLINE_DATA_PLAN.md` ("Data logging (as built)") and `docs/DECISIONS.md`. `scripts/validate_run.py` recomputes the scoring and checks the integrity of a logged run.

State of the data: no participant data has been collected. The live database holds only test runs (builds being tried in a
browser), and `ForagingData/` only holds debugging output and worlds archived by hashes. Once real collection begins, this section should say which runs are
real. **No analyses of human data are recorded in this repo;** the only results are the simulated agents' (below; code in `scripts/`).

---

## Agent ladder for calibrating the task (framework, learners and exploration policies built; results provisional)

Goal: find a task design where, in every session, learning pays and strategy pays, using simulated agents as a screen before (and
alongside) a human pilot. The old S-session results and the Interlude evaluation of agents are history (DECISIONS, "Historical: recorded simulation runs ...", "... the Interlude parts of the agent ladder ..."); results are re-recorded only on request (CLAUDE.md, "Results database"). **Built:** the component framework in `scripts/agents.py` and the engine in `scripts/sim.py` (heading, view cone, Harvest / Explore / Look /
Stop actions; checkpoints of an agent during a session); `nearest`, `greedy_*` and `plan_*` rebuilt on it with the oracle critic; the assessment battery (`scripts/battery.py`: the labels T1 to T4 of the frozen tiles session `FIX_T0`, reward only); and, for the pilots, the patch-foraging benchmarks (`scripts/patch_foraging.py`: `dp_finite`, `dp_average`, `mvt`, `mvt_running`, known values and average costs; the beam planner scored 25 to 35 percent below them and is no benchmark) and `scripts/agent_benchmark.py` (`docs/pilots/agents.md`). The design, defaults and first numbers of the learners and exploration policies are in `docs/DECISIONS.md`; the results are provisional dirty-tree runs and are not summarised here until they are re-recorded on a clean tree.
- **Critics** (value representation and learning rule): `DeltaRuleCritic` (TD(0) on additive RBF features with a swappable `Prior` and an optional swappable
  `Replay`: `FullSweeps`, `SampledReplay`, `PrioritizedReplay`, which re-present stored bushes during the session) and `GPCritic` (Gaussian-process
  regression with a swappable `Kernel`: additive or joint RBF, or `FeatureKernel`, the delta rule's own feature similarity, which makes it Bayesian
  linear regression on the same features; prior mean, prior spread and noise estimated from the memory, each switchable to a fixed value; it reports
  a posterior sd and can draw a joint sample). The two can be made to differ only in the update rule (exact fit against online steps).
- **Actors** (policy): the rate utility within a 15 s walking window, which is the standard; random exploration (`SoftmaxActor`, with an optional horizon
  that shrinks the temperature with the time left); attribute-space curiosity and peek-and-leave (`CuriousActor`); area-restricted search in attribute
  space (`AreaRestrictedActor`); and the posterior-based UCB, Thompson sampling and hybrid (`PosteriorActor`, which need the GP critic's uncertainty).
- **Not built:** SSP features, a recency-weighted replay (it needs the memory to record the order of visits), limited or forgetful memories, a ranking evaluation of agents, and the agent list.
- **Ladder:** `nearest` (floor, learns nothing) < simple learner < ideal learner < full-information `greedy`/`plan_beam` (and the patch-foraging oracles). The full-information
  agents are not reachable by any learner; they are a benchmark, and the gap to them is the unavoidable cost of learning, not a tuning target.
  Sweet spot: a wide floor-to-learner gap (learning pays) and a clear gap between weak and strong policies on the *same* learner (strategy pays).
- **Agent = actor x critic x memory**, each a separate component in `agents.py`, mixed and matched. **Actor** = the policy: choice rule
  (hard-max or softmax, returned as probabilities so likelihoods can later be fit to human choices), utility (value or rate, optional exploration
  bonus), leave/peek rule, and exploration (walk or look to see more bushes, or pick a bush to peek at). **Critic** = the value representation and
  its learning rule, from per-fruit rewards (full knowledge of the true reward function is the `oracle` critic). **Memory** = constraints on what
  the other two may use: the bushes seen so far (map: positions, attributes, spent or not) for the actor, and the (attributes, reward)
  experiences for the critic; full memory accumulates everything seen, full knowledge is preloaded with the whole map. `greedy` and `plan`
  are actors with the oracle critic and full-knowledge memory (the `greedy_*` entries; `nearest` is the same actor with a view-cone memory since the standard agents
  were redefined, so older tags hold a different `nearest`: pass an agent id, not the alias, to `analysis.py` for them). The **percept** is not a component: it belongs to the environment (`scripts/perception.py`),
  the sensor the engine applies: a view cone with an angle and distance and a heading, exact attributes, no terrain occlusion by default (the opt-in `OccludedConePercept` adds terrain and bush occlusion). By default it is
  as wide as the session camera (107.5 deg horizontal for 75 deg vertical at 16:9) with no distance limit; a run can replace it (`run_n(..., percept=)`,
  `sim.py --percept ANGLE,DISTANCE`) and an agent may carry its own override. Further constraints (resolvability by angular
  size, attribute noise) become new percept classes, calibrated against participants' logged visible sets. Walking, exploring and looking are actions of the
  actor, with time costs from `scripts/costs.py`: turning the view (`0.17 s + angle / 480 deg/s`, before a walk to face the way, before a harvest to bring the bush into the harvest cone, the view then ending at the cone's edge, not facing the bush; under 5 degrees it is free), pressing W to walk (0.2 s) and Space to harvest (0.3 s). The values are provisional, fitted to the developer's debug sessions (91 turns, 58 Space presses; the W press is a guess) and to be recalibrated from participants' logs. Every action costs time and a no-op (`Look(0)`, `Explore` of 0) is refused. These costs change every simulated total, so earlier totals are stale.
- **What the critic and actor components are for (questions, not results):** the learners separate three sources of improvement that a human
  comparison can tell apart: the *representation* (what generalises across attributes: additive against joint, the kernel width), the *update rule*
  (an online step against an exact or replayed fit; how many passes over what is stored), and *exploration* (random noise, an attribute-space novelty
  bonus, a posterior-based bonus or sample, a leave rule). Their human signatures, all derivable from the logs: generalisation (attribute distance
  between consecutive harvests and the previous reward, and the rankings by pair type), learning dynamics and order or recency effects (the
  amount of replay as a fitted quantity), choice noise against uncertainty (the bias and slope of the choice curve, directed against random
  exploration), the effect of time left on choices, leaving times against the average rate, and revisits. No model comparison in the literature covers
  continuous navigation with travel cost, a view cone and occlusion, which is where participants' data would be new.
- **Robustness:** the ordering of agents must hold across a variety of agents (learner and policy parameter sweeps), worlds and reward functions,
  not for one tuned learner.
- **TODO(PI): design a good agent/human performance metric** (candidate: (score - nearest) / (oracle - nearest) per session, plus choice-quality
  measures such as the rank correlation of chosen bushes with true value and reward rate over time) before tuning anything against it.
- The pilot will move these numbers; the simulation screens designs, it does not replace calibration on people.

---

## Open questions and known limitations

- **Exploration and learning (agents).** (a) Peek-and-leave has no valid result yet: the first version walked back to the bush it had left, so its recorded results measured that loop and are invalid (DECISIONS, "Exploration policies"); re-run every peek-and-leave result (`peek`, `curious_peek`, `gp_peek`, `gp_curious_peek`, the `scan-peek` and `scan-delta-peek-margin` populations) on the fixed code, and re-record the roster, the scans and the matched-critic comparison on a clean tree before any result goes into this file. (b) Whether any exploration policy helps once the critic
  fits the data well is open: the first runs show little benefit beyond an attribute-space curiosity bonus, and the learner with the most headroom was
  tested only at a few parameter values. (c) Replay amount, kernel width and the GP's regularisation are free parameters that should be fitted to people, not
  tuned for reward. (d) The learning curves of an agent that depends on the session's length (a horizon softmax, a planner) are within-session curves,
  not what a shorter session would give. (e) A recency-weighted replay and a forgetful memory need the memory to keep the order of visits. (f) The
  simulated observer sees every bush in its cone; `OccludedConePercept` (terrain and bush occlusion) exists but no result is recorded with it.
- **The ranking design is provisional:** the bonus rule and its scale (`rankingBonusPerPair` 4, the pair weighting), the size and number of sets, the wording for the first break, and whether a ranking after every transition is too many (a PCX run at 3 s travel had 8 to 12 rankings of 5.8 to 8.5 s each; DECISIONS, "The menu's time counts foraging time only"). The menu's time quote undershoots the true time and is set by hand until pilot data exist.
- **Patch contrast and within-patch variance** are held at near zero and the map's own (balanced placement); the advanced placements are to be built ("Current design"). The tile-leaving calibration is of oracle top-k and threshold policies, a lower bound on the optimum; the pilots' benchmarks (`patch_foraging.py`) are the upper bounds in use.
- **The pilots** (PCX, PSP, PSC) are designs, not results: the knobs' spans, the held factors and the gains are checked by `pilot_report.py`, but what participants can tell apart along each knob is what the pilots are for. The participants are not told what varies.
- **Tutorial wording** is the PI's and still open; there is no guarantee that a participant sees a ranking before the tutorial's Ranking hints are due (it comes at a patch switch).
- **Weak-to-moderate prior on moisture** (ground color) — acknowledged in the
  attribute table; no mitigation. The tiles' plateaus make ground colour and height a regional cue, but they pay nothing, so it is a possible distractor (and a possible confound for anyone who treats it as a choice regressor), not a reward feature.
- Terrain doesn't self-shadow (URP limitation at landscape scale). Shadow bias artifacts at low sun angles used to be
  hidden by flooring the light at 25° (`minSunElevation`); with the real sun path the light now ends at 10°, so the last
  stretch of each session is **untested** for artifacts and for readability (the shadow and ambient behaviour were deliberately not
  changed). If problems appear, raise `minSunElevation`, fade shadows/intensity near the horizon, or end the path higher.
- Player capsule/model may visually overlap wide canopies slightly.
- `FruitMaterialManager`'s cache persists across Play-mode sessions in the
  Editor (intentional).
- Custom shaders must be in Always Included Shaders or standalone builds
  break (this bit the project once; fixed in `51fa98b`).

---

## Retired designs (moved to docs/DECISIONS.md)

These headings are kept so older citations still resolve. Each text is in `docs/DECISIONS.md` under "Historical: ... (moved from SCIENCE.md, 2026-11-19)".

### Interlude: moved to docs/DECISIONS.md, "Historical: the Interlude, the between-session forced choice"
### Session structure: moved to docs/DECISIONS.md, "Historical: session structure of the Complex Features ladder P, S1 to S7"
### Terrain by session: moved to docs/DECISIONS.md, "Historical: terrain by session (S1-S7 era)"
### Planned experiments: moved to docs/DECISIONS.md, "Historical: planned experiments FN, RW, FI, PL, PA"
### Earlier session configurations and progression: moved to docs/DECISIONS.md, "Historical: earlier session configurations P to S4" and "... earlier session progression P to S5"
### Findings and simulated baselines: moved to docs/DECISIONS.md, "Historical: recorded simulation runs on the S1-S4 environments" and "Historical: simulated agent baselines (preliminary, STALE) ..."

---

## References

Verification level: **[text]** = I read substantial portions of the paper;
**[abstract]** = abstract/metadata and secondary descriptions only — check the
paper before leaning on specifics. Direct quotes in the rationale come only
from [text] sources.

**Naturalistic learning and decision making**
- Wise, T., Emery, K., & Radulescu, A. (2024). Naturalistic reinforcement
  learning. *Trends in Cognitive Sciences, 28*(2), 144–158.
  doi:10.1016/j.tics.2023.08.016 (PMC10878983) **[text]**
- Mobbs, D., Trimmer, P. C., Blumstein, D. T., & Dayan, P. (2018). Foraging
  for foundations in decision neuroscience: insights from ethology. *Nature
  Reviews Neuroscience, 19*(7), 419–427. doi:10.1038/s41583-018-0010-7
  (PMC6786488) **[text]**
- Yoo, S. B. M., Hayden, B. Y., & Pearson, J. M. (2021). Continuous
  decisions. *Philosophical Transactions of the Royal Society B, 376*(1819),
  20190664. (PMC7815426) **[text]**
- Gordon, J., Maselli, A., Lancia, G. L., Thiery, T., Cisek, P., & Pezzulo, G.
  (2021). The road towards understanding embodied decisions. *Neuroscience &
  Biobehavioral Reviews, 131*, 722–736. doi:10.1016/j.neubiorev.2021.09.034
  (PMC7614807) **[abstract]**
- Krakauer, J. W., Ghazanfar, A. A., Gomez-Marin, A., MacIver, M. A., &
  Poeppel, D. (2017). Neuroscience needs behavior: correcting a reductionist
  bias. *Neuron, 93*(3), 480–490. doi:10.1016/j.neuron.2016.12.041
  **[abstract]**

**Foraging**
- Hayden, B. Y. (2018). Economic choice: the foraging perspective. *Current
  Opinion in Behavioral Sciences, 24*, 1–6. **[abstract]**
- Hills, T. T., Todd, P. M., & Goldstone, R. L. (2008). Search in external and
  internal spaces: evidence for generalized cognitive search processes.
  *Psychological Science, 19*. doi:10.1111/j.1467-9280.2008.02160.x
  **[abstract]**
- Hills, T. T., Todd, P. M., Lazer, D., Redish, A. D., & Couzin, I. D. (2015).
  Exploration versus exploitation in space, mind, and society. *Trends in
  Cognitive Sciences, 19*(1), 46–54. doi:10.1016/j.tics.2014.10.004
  (PMC4410143) **[abstract]**
- Kolling, N., Behrens, T. E. J., Mars, R. B., & Rushworth, M. F. S. (2012).
  Neural mechanisms of foraging. *Science, 336*, 95–98.
  doi:10.1126/science.1216930 **[abstract]**
- Constantino, S. M., & Daw, N. D. (2015). Learning the opportunity cost of
  time in a patch-foraging task. *Cognitive, Affective, & Behavioral
  Neuroscience, 15*, 837–853. doi:10.3758/s13415-015-0350-y **[abstract]**

**Feature-based and function learning; exploration**
- Farashahi, S., Rowe, K., Aslami, Z., Lee, D., & Soltani, A. (2017).
  Feature-based learning improves adaptability without compromising
  precision. *Nature Communications, 8*, 1768.
  doi:10.1038/s41467-017-01874-w (PMC5700946) **[abstract]**
- Niv, Y. (2019). Learning task-state representations. *Nature Neuroscience*
  (Perspective). **[abstract]**
- Schulz, E., Konstantinidis, E., & Speekenbrink, M. (2018). Putting bandits
  into context: how function learning supports decision making. *Journal of
  Experimental Psychology: Learning, Memory, and Cognition, 44*(6), 927–943.
  doi:10.1037/xlm0000463 **[abstract]**
- Wu, C. M., Schulz, E., Speekenbrink, M., Nelson, J. D., & Meder, B. (2018).
  Generalization guides human exploration in vast decision spaces. *Nature
  Human Behaviour, 2*(12), 915–924. doi:10.1038/s41562-018-0467-4 (a 2021
  correction exists) **[abstract]**

**Exploration strategies (computational and behavioural), added with the exploration-policy work.** Marks: **[read]** = full text read, **[abstract]** =
abstract or metadata only (the two literature reviews are in the session notes; only Gershman 2018, Hills et al. 2013 and Wu et al. 2018 were read in full)
- Auer, P., Cesa-Bianchi, N., & Fischer, P. (2002). Finite-time analysis of the multiarmed bandit problem. *Machine Learning, 47*, 235–256.
  doi:10.1023/A:1013689704352 **[abstract]**
- Srinivas, N., Krause, A., Kakade, S., & Seeger, M. (2010). Gaussian process optimization in the bandit setting: no regret and experimental design.
  *ICML*. arXiv:0912.3995 **[abstract]**
- Chowdhury, S. R., & Gopalan, A. (2017). On kernelized multi-armed bandits. *ICML*. arXiv:1704.00445 **[abstract]**
- Li, L., Chu, W., Langford, J., & Schapire, R. E. (2010). A contextual-bandit approach to personalized news article recommendation. *WWW*.
  arXiv:1003.0146 **[abstract]**
- Russo, D., Van Roy, B., Kazerouni, A., Osband, I., & Wen, Z. (2018). A tutorial on Thompson sampling. *Foundations and Trends in Machine
  Learning, 11*(1). arXiv:1707.02038 **[abstract]**
- Agrawal, S., & Goyal, N. (2012). Analysis of Thompson sampling for the multi-armed bandit problem. *COLT / PMLR 23*. arXiv:1111.1797 **[abstract]**
- Frazier, P. I., Powell, W. B., & Dayanik, S. (2008). A knowledge-gradient policy for sequential information collection. *SIAM Journal on Control
  and Optimization, 47*(5), 2410–2439. **[abstract]**
- Russo, D., & Van Roy, B. (2014). Learning to optimize via information-directed sampling. *NIPS*. arXiv:1403.5556 **[abstract]**
- Bubeck, S., Munos, R., & Stoltz, G. (2009). Pure exploration in multi-armed bandits problems. *ALT*. arXiv:0802.2655 **[abstract]** (explore to
  earn against explore to learn)
- Lam, R., Willcox, K., & Wolpert, D. H. (2016). Bayesian optimization with a finite budget: an approximate dynamic programming approach. *NIPS*.
  **[abstract]** (finite horizons)
- Guez, A., Silver, D., & Dayan, P. (2012). Efficient Bayes-adaptive reinforcement learning using sample-based search. *NIPS*. arXiv:1205.3109 **[abstract]**
- Houlsby, N., Huszár, F., Ghahramani, Z., & Lengyel, M. (2011). Bayesian active learning for classification and preference learning. arXiv:1112.5745
  **[abstract]**
- Osband, I., Blundell, C., Pritzel, A., & Van Roy, B. (2016). Deep exploration via bootstrapped DQN. *NIPS*. arXiv:1602.04621 **[abstract]**
- Bellemare, M., et al. (2016). Unifying count-based exploration and intrinsic motivation. *NIPS*. arXiv:1606.01868 **[abstract]**
- Burda, Y., Edwards, H., Pathak, D., Storkey, A., Darrell, T., & Efros, A. A. (2019). Large-scale study of curiosity-driven learning. *ICLR*.
  arXiv:1808.04355 **[abstract]** (the noisy-TV problem)
- Wilson, R. C., Geana, A., White, J. M., Ludvig, E. A., & Cohen, J. D. (2014). Humans use directed and random exploration to solve the
  explore–exploit dilemma. *Journal of Experimental Psychology: General, 143*(6), 2074–2081. **[abstract]**
- Wilson, R. C., Bonawitz, E., Costa, V. D., & Ebitz, R. B. (2021). Balancing exploration and exploitation with information and randomization.
  *Current Opinion in Behavioral Sciences, 38*, 49–56. **[abstract]**
- Gershman, S. J. (2018). Deconstructing the human algorithms for exploration. *Cognition, 173*, 34–42. PMC5801139 **[read]** (a hybrid of UCB and
  Thompson sampling fits two-armed bandit choices best)
- Gershman, S. J., & Niv, Y. (2015). Novelty and inductive generalization in human reinforcement learning. *Topics in Cognitive Science, 7*(3),
  391–415. PMC4537661 **[abstract]**
- Wu, C. M., Schulz, E., Speekenbrink, M., Nelson, J. D., & Meder, B. (2018): the main text and the CogSci 2017 version were read in full (a Gaussian
  process with an upper-confidence-bound rule, locality, fitted length scales below the true ones); the Nature supplementary information could not
  be accessed, so the per-condition parameter table was taken from the authors' code **[read, supplement not]**
- Schulz, E., Wu, C. M., Ruggeri, A., & Meder, B. (2019). Searching for rewards like a child means less generalization and more directed
  exploration. *Psychological Science, 30*(11), 1561–1572. doi:10.1177/0956797619863663 **[abstract]**
- Giron, A. P., et al. (2023). Developmental changes in exploration resemble stochastic optimization. *Nature Human Behaviour, 7*(11), 1955–1967.
  **[abstract]**
- Wu, C. M., Schulz, E., Pleskac, T. J., & Speekenbrink, M. (2022). Time pressure changes how people explore and respond to uncertainty. *Scientific
  Reports*. PMC8904509 **[abstract]**
- Mehlhorn, K., et al. (2015). Unpacking the exploration–exploitation tradeoff: a synthesis of human and animal literatures. *Decision, 2*(3),
  191–215. doi:10.1037/dec0000033 **[abstract]**
- Constantino, S. M., & Daw, N. D. (2015). *Cognitive, Affective, & Behavioral Neuroscience, 15*, 837–853 (already cited above) and Hayden, B. Y.,
  Pearson, J. M., & Platt, M. L. (2011). Neuronal basis of sequential foraging decisions in a patchy environment. *Nature Neuroscience, 14*,
  933–939. **[abstract]**
- Hills, T. T., Kalff, C., & Wiener, J. M. (2013). Adaptive Lévy processes and area-restricted search in human foraging. *PLoS ONE, 8*, e60488.
  PMC3618454 **[read]** (post-find turning in a virtual patchy world; step lengths are not diagnostic)
- Edwards, A. M., et al. (2007). Revisiting Lévy flight search patterns of wandering albatrosses, bumblebees and deer. *Nature, 449*, 1044–1048;
  Raichlen, D. A., et al. (2014). Evidence of Lévy walk foraging patterns in human hunter-gatherers. *PNAS, 111*, 728–733. **[abstract]**
- Sharma, S., Curtis, A., Kryven, M., Tenenbaum, J., & Fiete, I. (2022). *ICLR*. arXiv:2110.12301 (an information-seeking account of human
  exploration of a 3D environment; title not recorded in the review notes) **[abstract]**
- Kidd, C., & Hayden, B. Y. (2015). The psychology and neuroscience of curiosity. *Neuron, 88*, 449–460. PMC4635443 **[abstract]**
**Related naturalistic paradigms — identified, not read**
- "A naturalistic reinforcement learning task uncovers historical neural
  representations" (bioRxiv, 2025), doi:10.1101/2025.07.17.665306
- Kalliste Decision Task (ecological assessment of decision-making under risk
  and ambiguity; PMC11161587)

