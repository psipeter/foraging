# docs/EXPERIMENTS.md — the planned experiments

The designs for the experiments that replace and extend the single Complex Features (`CF`) ladder. **Status (2026-11-06): a plan.
Nothing here is built**; the game still plays `TUT` and `CF` (`docs/SCIENCE.md`, "Session structure"). `docs/SCIENCE.md` ("Planned
experiments") has the summary; the reasoning and the rejected alternatives are in `docs/DECISIONS.md` ("Experiments split by question
(2026-11-06)"). Entries marked **TODO** are decisions still open.

## Why the experiments are separate

The `CF` ladder (S1 to S7) changes three things at once: the number of rewarded features, the nonlinearity of the mapping, and the
interaction between features, and it changes duration and practice along with them. Each experiment below varies one family of
things and holds the rest fixed, and the later two ask different questions altogether (scarce reward, foraging policy).

| Experiment | Code (planned) | Question | Reward functions |
|---|---|---|---|
| Learning with more rewarded features | FN | How do visible and rewarded feature numbers, and weak weights, change learning? | linear, one to three features |
| Learning with sparse rewards | RW | How do narrow peaks, and a local against a global maximum, change exploration? | Gaussian bumps in one or two features |
| Learning with feature interactions | FI | How does non-additive structure change learning? | additive, sigmoid products, tilted bump |
| Patch leaving | PL | Do people leave clusters of bushes efficiently, given travel and contrast? | easy: linear in one feature |
| Patch assessment | PA | How do people judge a cluster's value and decide when to leave? | additive, two features |

Codes are provisional (the assets, folders and database keys use them; renaming one means renaming those, see DECISIONS,
"Experiments"). The existing `CF` ladder maps onto the first three: S1 to S3 and S5 are cases of FN, S1, S2 and S4 to S7 are cases of RW
(single peak) and FI (S6, S7).

## Conventions shared by the experiments

- **Instances.** A session is an instance drawn from a pool: its own world seed and its own draw of the reward function's features,
  directions, positions and weights, so a participant never replays an answer. A pool is generated in Python (`scripts/world.py`,
  `scripts/interlude.py`) like today's worlds. The size of a pool, and how many instances each participant sees, are open in each
  experiment.
- **Order.** A short ease-in first (the simplest cases, simple to complex), then the later instances intermixed in random order, so
  complexity jumps around and participants cannot assume the next session is harder. Counterbalancing across participants is not settled.
- **Hints.** Where a hint is used it says which features matter in the early sessions; later sessions have no hint about the structure
  (what is discovered is part of what is measured). The patch experiments give no hint about the reward function.
- **Sparsity** (RW, FI): the fraction of the feature interval (one feature) or plane (two features) whose reward is in the top x% of
  the reward range (x to be decided). It puts sessions of different dimension on one scale. The bushes are assigned so that they cover
  the feature space evenly, so it carries over to the bushes. FI matches it across types.
- **Matching.** The best bush's reward and the per-fruit noise (`rewardStd`) are matched across the types that are compared, unless
  the noise is the variable.
- **Moisture** is decoration (weight 0) except where FN makes it the third feature (an open question there). Elevation and moisture
  mark tiles in the patch experiments.
- **Knowledge state** (PL, PA): never told. It is inferred from the progression of a participant's bush choices (when they begin to
  track the true values).
- **Efficiency** is the reward collected relative to an oracle that knows the reward function and follows the marginal value theorem
  in the same world.
- **Simulated agents** (`scripts/agents.py`, the battery) screen instances for difficulty and calibrate durations before any
  participant plays.

Open items that cross experiments: the Interlude today picks pairs by reward gap, and FN, RW and FI each need typed or per-feature
pairs (below); `spatialBalance` evens the reward over the map, which the patch experiments need off (or applied inside tiles) and
a moisture-paying reward does not support; session durations and Interlude trial counts wait for measured Interlude timing; the
bonus design for sparse sessions.

---

## Learning with more rewarded features (FN)

1. **Display name:** feature number (FN)
2. **Hypothesis:**
   1. Visibly varying features that do not influence reward slow the discovery of the relevant features slightly.
   2. Increasing the number of rewarded features slows learning much more and lowers the probability of learning the true value function.
   3. The probability of learning to evaluate a rewarded feature (at a nonzero value) is proportional to its weight in the reward function
      (relative to the other feature weights and the per-fruit noise).
3. **Experiment:**
   1. *Features and terms.* Shape, color and moisture are the three attributes a bush can vary in. A feature is *visible* if it varies
      across bushes, and *rewarded* if its weight is nonzero. All mappings are linear. The direction of each feature's mapping (which end
      pays) and which features pay are drawn per instance. Bushes sit on a hexagonal lattice, and reward density is roughly uniform in space.
   2. *Instances.* Each session is an instance drawn from a pool, with its own world seed and its own draw of weights and directions, so a
      participant never replays the same world.
   3. *Baseline sessions: one feature pays, one to three features are visible.* The hint names the features.
      * One visible feature, and it pays. Goal: find the better end of the spectrum. Hint: feature X determines reward.
      * Two visible features, one pays. Goal: find which one, and the better end. Hint: one of feature X or Y determines reward.
      * Three visible features, one pays. Goal: find which one, and the better end. Hint: one of X, Y or Z determines reward.

      These are short, with few repeats and few Interlude trials. They measure the cost of perceptual variance when only one feature pays.
   3a. *Intermediate sessions: at least two features are visible and two of them pay, with equal weight.* These are of intermediate length and
      measure more complicated hypothesis testing and search.
      * Two visible features, both pay. Goal: find both better ends at once. Hint: both of the features X and Y determine reward.
      * Three visible features, two pay. Goal: find which feature does not pay, and the better ends of the other two. Hint: two of the three features determine reward.
   4. *Weighted sessions: three visible features, all of which can pay.* These are long, with more repeats and more Interlude trials.
      * Three randomized weights sum to one, and a variety of weight breakdowns across the three features is simulated to get broad coverage
        of the complexity and threshold space.
      * Goal: find the relative weights. Hint: all three features matter, but some matter more than others.
      * **TODO:** how to distribute the normalized weights so that they cover the weight space in a way that makes hypothesis testing
        straightforward. Considerations so far: express a weak feature's strength in noise units (its weight times its range of values, over
        `rewardStd`); joint sampling of the two weak weights over a grid including zeros against a one-parameter family such as (1, r, r²); a
        fixed strongest weight against a fixed total; how many instances a participant sees from a larger pool; whether to adapt the weights
        to a participant's previous Interlude.
   5. *Order (PI, 2026-11-09).* One pass through the cells in order: row 1 (one rewarded feature; one, two, three visible), row 2 (two rewarded;
      two, three visible), then the first weighted session. The remaining iterations of every cell follow in a random order across the whole set.
      Within a cell the iterations are counterbalanced over the features (each feature pays, or is the idle one, once; each visible pair once).
   6. *Status (2026-11-09).* Built as `scripts/design/FN.py` with provisional numbers: each of the five baseline cells (V visible, R rewarded:
      (1,1), (2,1), (3,1), (2,2), (3,2)) is played 3 times, plus 6 weighted sessions (3,3), 21 sessions in all. The weak weights use the stand-in family
      (1, r, r²) for r = 1, 0.7, 0.5, 0.35, 0.2, 0.1 over a random ranking of the features (the tiling of the weight space is still the TODO above).
      Duration (PI): 60 s at (1,1) plus 15 s per extra visible feature and 30 s per extra rewarded one, so 60, 75, 90, 105 and 120 s for the baseline cells and 150 s
      for the weighted sessions (about 37 minutes of play, Interludes not counted). Interlude trials (PI): 5, 10 and 20 for one, two and three rewarded features (20 = 2 repeats, 2 per-feature trials) for weighted.
      Durations and trial counts wait for measured Interlude timing. Moisture is the third feature (flat, single-coloured ground where it is not
      visible). See DECISIONS, "FN built on the new generators".
4. **Analysis:**
   1. Point trajectories of reward against time in each session. The rate and curvature of increase show performance and periods of learning.
   2. Interlude choices can be analyzed to estimate a participant's feature weights, and hence how well they learned the true value function.
   3. A detection curve: the probability that a weak feature is learned, against its strength in noise units, as a mixed model with a
      random effect per participant.
   4. Baseline sessions compared with each other for the effect of perceptual variance on learning speed and top performance.
   5. Weighted sessions compared with the baselines for the effect of the rewarded-feature breakdown on learning speed and top performance.

---

## Learning with sparse rewards (RW)

1. **Display name:** reward sparsity (RW)
2. **Hypothesis:**
   1. When the feature-to-reward mapping is sparse (only a narrow range of feature values pays well), people explore longer and earn
      fewer points.
   2. With two peaks, a local and a global maximum, people are more likely to settle on the local one. This should be more likely when the
      peaks are narrow, far apart or close in height, or when per-fruit noise hides the difference between them.
3. **Experiment:**
   1. *Features and terms.* Shape and color always vary across bushes. In every session the reward is a Gaussian bump, or a sum of two bumps,
      over the features that pay. The other feature, if any, is decoration. Bushes sit on a hexagonal lattice, and reward density is roughly
      uniform in space. A *peak* is one bump of the reward function. The *global maximum* is the higher peak and the *local maximum* is the
      lower one.
   2. *Sparsity* is defined in feature space (see "Conventions"): the fraction of the feature interval or plane whose reward is in the top x%
      of the reward range. The value of x is to be decided. A narrow 2D bump with the same width as a 1D bump covers far less of its space,
      so width alone is not comparable across the two.
   3. *Instances.* Each session is an instance from a pool, with its own world seed and draw of parameters. Peak positions are drawn away
      from the ends of the feature range, since a peak at an edge behaves like a linear mapping. Which feature pays in the one-feature
      sessions is drawn per instance.
   4. *Session types, from simple to complex.* The number of peaks and the number of features that pay together set the difficulty, so
      session length grows with it.
      * One peak, one feature pays (the other feature is decoration). Short. Goal: find the best spot on the spectrum.
      * One peak, both features pay (one 2D bump). Medium. Goal: find the best spot in the plane.
      * Two peaks, one feature pays (two 1D bumps with a local and a global maximum). Medium to long. Goal: find the best peak, not just a
        good one.
      * Two peaks, both features pay (two 2D bumps with a local and a global maximum). Quite long, to encourage continued exploration.
        Goal: find the best peak in the plane.
   5. *Parameters that vary across instances* in the two-peak sessions: the sparsity (peak width), the separation between peaks (in units of
      width), the height ratio of global to local, and the per-fruit noise (`rewardStd`). The two-peak sessions have more repeats and more
      Interlude trials than the one-peak sessions.
   6. *Order and intermixing.* The two one-peak sessions come first, from simple to complex. The two-peak sessions follow, in a random order
      of their parameters, with the one-feature and two-feature types mixed.
   7. *Hints.* The hints of the one-peak sessions say which features matter. The first two-peak session of each type (one with one feature
      paying, one with both) says that there are two types of valuable bushes. Later two-peak sessions have no hint about the structure.
      Participants then cannot count on the hint, and what they carry over from the hinted sessions is part of what we measure.
   8. **TODO, distribution of the peak parameters.** This needs careful thought to cover the parameter space evenly and to give differences
      we can analyze: sparsity, separation in width units, height ratio and noise; how many instances each participant sees from the pool;
      and how to separate the effect of the parameters from the effect of fading the hint.
   9. *Other open items.*
      * Session durations and Interlude trial counts for each of the four session types (these depend on measured timing).
      * Bounds on the width. The narrowest peak must still hold enough bushes, and be wide enough that neighbouring feature values are visibly
        distinguishable. The world generator needs to guarantee a minimum number of bushes near each peak.
      * Earnings. Sparse sessions pay little to a participant who never finds a peak, so the bonus design needs a check.
      * Typed Interlude trials. The Interlude today picks pairs by reward gap. This experiment needs typed pairs: global against local, local
        against the median bush, global against the median, and a valley bush, so we can read the preference order.
      * Screening instances with the simulated agents, to check that a greedy agent really is trapped by the local peak and an exploring one
        is not.
4. **Analysis:**
   1. Point trajectories of reward against time in each session. The slope and curvature show learning, and the time of leaving a peak shows
      the explore/exploit trade-off.
   2. Interlude performance by trial type and by parameters: does accuracy on global against local depend on sparsity, separation, height
      ratio and noise? Read the learned preference order across the median, local and global bushes.
   3. Dynamics of the explore/exploit transition: change points in the visit sequence, the spread of visited feature values over time, and
      the time and rate of settling.
   4. Trapping: the share of late harvests in the local peak's neighbourhood, and whether participants who visited both peaks ended on the
      global one.
   5. Per-fruit noise: how the noise level changes exploration and trapping, in a mixed model with the other parameters and a random effect
      per participant.
   6. Hinted against unhinted sessions, and the instance index as a covariate, to see whether people learn to expect more than one peak.

5. **Build plan (2026-11-10).** RW is built the way FN was: a design module `scripts/design/RW.py` (instances, hints, durations, texts) that `build_experiment.py RW` turns
   into session and Interlude assets, worlds, Interlude files and instruction texts, with FN's conventions (a `design` record per instance, with the `iteration` of an instance so
   that the reduced-run `repeats` knob works, bold phrases in the hints, the menu row from `ExperimentConfig`). What exists and what does not:
   * *Exists:* Gaussian bumps in the reward function (`bumps`: a centre in (shape, color), a height, a spread along shape and, optionally, along color; a one-feature peak is a bump
     with a very wide spread on the decoration axis) in the generator, the game and the simulator; the Instance contract and the build pipeline; typed Interlude trials in the
     Interlude file (a trial is an explicit pair with a free-text `type`, so the game needs no change); per-feature balancing; the simulated agents and the battery for screening.
   * *Does not exist:* the sparsity measure and the peak parameterisation (width, separation in widths, height ratio, positions away from the ends); a draw of the features that
     covers the feature *plane* evenly (per-feature balancing only evens each feature on its own, and reward-based balancing leaks which feature pays); the typed Interlude trials
     (global against local, local against the median, global against the median, a valley bush); a check that a built world shows the peaks its design record states.
   * *Phases, in order, each ending in tests and a decisions entry:*
     1. **Decisions** (below). Nothing is built before the sparsity level `x`, the pool and the per-participant counts are chosen.
     2. **Peak model** (`scripts/rw_peaks.py`, **built 2026-11-10**: see DECISIONS "RW peak model"): from (type, width, separation, height ratio, noise, seed) to the `bumps` of the reward function; the sparsity measure
        (the fraction of the interval or plane in the top x% of the reward range); positions kept a margin from the ends. Tests: the measure on known bumps, the separation in
        widths and the height ratio as stated, no peak at an edge, the one-feature case flat along the decoration axis. Size: small.
     3. **Plane coverage** (**built 2026-11-10**: see DECISIONS "RW plane coverage"): a new assignment stage in `world.py` that deals (shape, color) to the lattice positions stratified over the plane (so the marginals are even too) and
        independent of the reward, with a guaranteed number of bushes inside the narrowest peak's half-width. Tests: coverage statistics, the guarantee for the narrowest width,
        no relation between a bush's position and its features. Size: medium (the leak problem of `spatialBalance` is the thing to avoid).
     4. **Screen the parameter space with the simulated agents** (**run 2026-11-10** as tag rw2, 38,340 instances: `scripts/rw_screen.py`, `scripts/rw_screen_analysis.py`; results in DECISIONS "RW screening results (rw2)") before any asset exists: a greedy and an exploring agent on candidate instances, to see that the local peak traps
        the greedy one and not the exploring one across the width, separation, height-ratio and noise ranges, and to set the ranges and the sessions' durations. Size: small to
        medium, mostly computing time (run when asked: new conditions, not re-run baselines).
     5. **Typed Interlude trials** in `interlude.py` (like `feature_trials`): the pair types, their counts per session type, their order, tests that each pair is what its type says
        (the real reward means, the gap in noise units). Size: medium.
     6. **The design module and the build**: the instance pool, the order (the two one-peak sessions first, then the two-peak sessions mixed), the hints (one-peak hints name the
        features; the first two-peak session of each type says there are two kinds of valuable bush; the later ones say nothing), durations, Interlude trial counts, the assets and
        worlds (about 0.8 MB each), the catalog entry; `test_rw_design.py` like FN's, and `test_realization.py` extended to peak designs. Size: medium.
     7. **Publish and pilot**: `server_admin.py publish` registers the experiment (set its completion code), a development build, then pilots on friends and labmates with the reduced
        runs (`repeats = 1` is one instance of each type); the pilots measure the time per session and per Interlude trial, which sets the durations and the menu's minutes.
   * *Decisions (PI, 2026-11-10):*
     * The sparsity measure is taken at x = 10, 20 and 30 (the fraction of the feature interval or plane whose reward is in the top 10%, 20% and 30% of the reward range); an
       instance reports all three. **TODO (confirm): whether the three x are three thresholds at which every instance is measured, or three target sparsity levels of the pool.**
     * The pool: one instance of each session type for now; how many instances in all, and how many of each type a participant sees, are decided later.
     * The margin from the ends of the feature range: wide enough that the reward visibly declines between a peak and the feature extreme. Confirmed, as operationalised: a peak's
       centre is at least about 1.5 spreads from each end, so the reward at the nearer extreme is at most a third of the peak's height.
     * The prerequisite is the tutorial, for now.
     * `rewardStd` is constant (the same in every RW instance), for now.
     * Decided in phase 3: every peak of a built world holds at least 5 bushes in its top-10% region, and the narrowest peak is expected to hold 10 (the draw then gave at least 7 in 300 placements). In spread that is 0.016 for a one-feature peak and 0.147 for a two-feature one at 700 bushes; the one-feature figure is far below what a person can tell apart, so the perceptual bound on the width (phase 4) will be the binding one there.
     * The bonus rule is the same as everywhere else (bonus per point, a fixed payment for the time). A participant who never finds a peak earns almost no bonus; that is accepted
       for now. Considered and not chosen: a guaranteed minimum bonus per session, a bonus on the share of the best possible points, a small baseline reward everywhere (it would change
       the sparsity design).
   * *No change to the data format is expected:* the world files, the session rows and the database tables stay as they are; the Interlude trial `type` strings are new values of an
     existing text column.

6. **Session plan, draft v8 (2026-11-10; nothing here is built; v7 plus the rw4 crossing screen).** Built like FN: cells with an `iteration` index in their `design` record (so the reduced-run `repeats` knob works), a first pass
   through the baseline cells in order, then the rest in a random order, one world seed and one random draw of the peaks per instance (which feature pays in a one-feature session alternates over the
   instances), hints per cell type, Interlude trial counts by type. **Sparsity is the share of all the bushes that pay at least 70% of the best bush** (about 7 good bushes per percent in a world of 700);
   **in a two-peak session it is the total, split equally over the two peaks**. A peak's spread follows from its share (share / 1.69 for one feature, sqrt(share / pi) / 0.844 for two). FN covers the number
   of features, so the sparsity scan (S) and the separation crossing (T) use two features only; the one-feature sessions are only in the baseline (B). **Discovery is reported strict** (PI, 2026-11-10): a
   fruit from a bush in the global peak's top-10% region, at least 90% of the best bush's value; **lenient** is the top-30% region (at least 70%). A **person** is taken to be 2 to 3 times slower than the
   agents: the proxy is the agents' discovery at (session length) / 2 and / 3 (`rw_screen_analysis.human_proxy`).
   * *The design (16 sessions with 2 iterations of S and T; B once, the teaching sessions):* **B** (baseline, 120 s, fixed order): one and two features by one and two peaks at 15%, the two-peak ones at the
     nearest separation. **S** (one peak, two features, 180 s): 15% and 5%, 2 iterations. **T** (two peaks, two features, 180 s): **proposed (rw4): sparsity 15% and 10% crossed with the height ratio, 0.3 and 0.75, at one separation of 4.5 spreads, with the margin relaxed to 1.0 spread (the 15% cell does not fit with 1.48); 2 iterations** (v7 had 10% and 5% crossed with the separation, 3 and 4.5, at ratio 0.75). Hints: one-peak sessions name the feature(s) that pay; the first two-peak session of each feature count (B3, B4) says there are two kinds of valuable
     bush. Order: B in order, then S and T in a seeded random order. Interludes: 5 trials (one feature) and 10 (two) for one peak, 20 typed pairs for two peaks (phase 5). Every peak holds at least 3 bushes
     in its top-30% region (the guarantee replacing 5 in the top-10%; no instance needed a replacement world in rw3). Time: 44 minutes of play, at most 84 with the Interludes (trials at their 7 s cap,
     20 s per instruction screen); a participant may stop between sessions.
   * *The agents on the ladder (rw3: nearest, learner, softmax, curious; 100 worlds per cell; learner, softmax and curious pooled, 300 worlds; strict):*

     | id | features | peaks | sparsity total (per peak) | spread | length | separation | found: agents | person k = 2 | k = 3 | trapped: agents | k = 2 | k = 3 | lenient found k = 2 | k = 3 | points (agents) |
     |---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
     | B1 | one | 1 | 15% | 0.089 | 120 s | | 99% | 88% | 71% | 0 | 0 | 0 | 99% | 92% | 399 |
     | B2 | two | 1 | 15% | 0.259 | 120 s | | 90% | 63% | 46% | 0 | 0 | 0 | 99% | 89% | 530 |
     | B3 | one | 2 | 15% (7.5%) | 0.044 | 120 s | 3 | 87% | 54% | 38% | 11% | 24% | 26% | 80% | 61% | 361 |
     | B4 | two | 2 | 15% (7.5%) | 0.183 | 120 s | 3 | 61% | 35% | 20% | 17% | 16% | 13% | 75% | 65% | 437 |
     | S2F-15 | two | 1 | 15% | 0.259 | 180 s | | 97% | 81% | 64% | 0 | 0 | 0 | 100% | 98% | 805 |
     | S2F-5 | two | 1 | 5% | 0.149 | 180 s | | 72% | 41% | 24% | 0 | 0 | 0 | 90% | 73% | 431 |
     | T2F-10-near | two | 2 | 10% (5%) | 0.149 | 180 s | 3 | 65% | 37% | 27% | 24% | 27% | 24% | 73% | 55% | 560 |
     | T2F-10-far | two | 2 | 10% (5%) | 0.149 | 180 s | 4.5 | 45% | 28% | 20% | 35% | 26% | 18% | 56% | 52% | 449 |
     | T2F-5-near | two | 2 | 5% (2.5%) | 0.106 | 180 s | 3 | 50% | 25% | 14% | 22% | 14% | 12% | 61% | 42% | 385 |
     | T2F-5-far | two | 2 | 5% (2.5%) | 0.106 | 180 s | 4.5 | 40% | 22% | 17% | 23% | 13% | 9% | 48% | 32% | 331 |

     (The score of a B session is at 120 s; S2F-15 at 120 s scores 528, the same as B2, which has the same parameters.)
   * *What rw3 shows.* (1) **The discovery model holds for the one-peak cells** (agents, strict: B1 99% observed against 97% predicted, B2 90 against 93, S2F-15 97 against 98, S2F-5 72 against 74, a
     two-feature extrapolation to 5%); the **two-peak cells are lower than the model** (B4 61% against 74, T2F-10-far 45 against 74), by the trapped fraction. (2) **The three learners are
     indistinguishable again; `nearest` (blind to values) finds less when sparse (S2F-5 48% against 68 to 75) and is trapped less in the far cell** (global found 54% against 42 to 44). (3) **Trapping is
     large wherever there are two peaks** (11% to 35% for the agents) and zero for one peak. (4) **The separation matters at 10% for the agents (trapped 24% near, 35% far; global found 65% against 45%)
     but little at the people proxy** (k = 2: trapped 27% against 26%, global found 37% against 28%; k = 3: 24% against 18%, 27% against 20%; a proportion of 300 worlds has a 95% half-width of about 5
     points) **and not at all at 5%** (22% against 23%). (5) **Sparsity matters a lot for points and discovery**: S2F-15 against S2F-5, 805 against 431 points (-46%), strict discovery 81% against 41% (k = 2).
     (6) **Under the strict definition no cell reaches 85% for a person except B1** (88% at k = 2, 71% at k = 3), and the hardest cells are 14% to 28%.
   * *The crossing screen (rw4: T at 15% and 10%, separation 3 and 4.5 at ratio 0.75, ratio 0.3, 0.75 and 0.9 at separation 4.5; margin 1.0 spread; the same four agents, 100 worlds per cell; 800 instances, none needed a
     replacement; the 10% cells reproduce rw3's).* Strict, learners pooled (300 worlds, a 95% half-width of about 7 to 8 points). Trapped fraction, **agents / person k = 2 / k = 3**: 15% sep 3 ratio .75: 15 / 21 / 24%;
     sep 4.5 ratio .75: 43 / 34 / 29%; sep 4.5 ratio .3: 20 / 20 / 20%; sep 4.5 ratio .9: 46 / 37 / 28%; 10% sep 3: 16 / 19 / 16%; sep 4.5 ratio .75: 36 / 24 / 20%; ratio .3: 6 / 8 / 8%; ratio .9: 32 / 22 / 15%.
     Found the global peak, same order: 15%: 80 / 53 / 33, 49 / 34 / 25, 76 / 51 / 37, 49 / 32 / 22; 10%: 70 / 45 / 33, 46 / 29 / 20, 76 / 46 / 29, 50 / 32 / 24. Points at 180 s: 15%: 708, 553, 535, 603; 10%: 586, 466, 451, 506.
     **The effect on trapping of separation 3 to 4.5 and of ratio 0.3 to 0.9** (points of the trapped fraction, agents / k = 2 / k = 3): 15%: +28 / +13 / +5 and +26 / +16 / +8; 10%: +20 / +5 / +4 and +26 / +14 / +7. So **the
     ratio is the more robust crossing factor at the person proxy** (the separation at 10% is within the noise); **the ratio effect is all between 0.3 and 0.75** (0.75 to 0.9: +3 and -4, nothing), so 0.9 is wasted; the
     separation costs points (-155 at 15%, -120 at 10%) while a higher ratio gains them (+68, +56: the local peak one is stuck on pays more); 15% and 10% carry more trapping signal than 10% and 5% (k = 2: 20 to 37% against
     13 to 14%); `nearest` (value-blind) is trapped 16% to 28% whatever the ratio and separation, so the learners' effects are learning, not geometry.
   * *Open (PI):* **the baselines' target** (the 85% was set on the lenient definition: B1 and B2 meet it at k = 2, B3 80% and B4 75%; B4 cannot be easier, two two-feature peaks above about 8.7% each do
     not fit the plane); **the T sparsity**: at the people proxy T at 10% has the most trapping (26% to 27%), at 5% it is 13% to 14% with global discovery of 22% to 25%, so 5% is mostly "nobody finds
     it"; a T pair of 15% and 10% (the 15% far cell needs the margin relaxed from 1.48 to 1.0 spread) or 12% and 8% would keep more signal; **the separation** has a small effect at the people proxy, so the
     height ratio (0.3 against 0.9 at one separation, which was as strong in rw2) is worth screening as T's crossing factor before deciding.

   * *Proposal v9 (PI, 2026-11-10; replaces the T crossing of v8, which is too much to characterise sparsity).* **S and T both take three sparsities, 15%, 10% and 5%, 3 iterations each; T's height ratio (0.5) and
     separation (4.5 spreads) are fixed, the margin 1.0 spread** (S 3 x 3 = 9 sessions, T 9, B 4: 22 sessions). Screen rw5 (`rw_screen.py run --tag rw5 --design sparsity`, 150 worlds per cell; learner, softmax, curious pooled, 450 episodes; strict):

     | cell | spread | found: agents | k = 2 | k = 3 | trapped: agents | k = 2 | k = 3 | lenient found k = 2 | points (agents) |
     |---|---|---|---|---|---|---|---|---|---|
     | S2F-15 | 0.259 | 98% | 81% | 65% | 0 | 0 | 0 | 100% | 810 |
     | S2F-10 | 0.211 | 92% | 71% | 54% | 0 | 0 | 0 | 99% | 655 |
     | S2F-5 | 0.149 | 78% | 42% | 32% | 0 | 0 | 0 | 87% | 438 |
     | T2F-15 | 0.183 | 64% | 43% | 27% | 32% | 27% | 23% | 65% | 526 |
     | T2F-10 | 0.149 | 69% | 37% | 26% | 16% | 16% | 12% | 75% | 447 |
     | T2F-5 | 0.106 | 49% | 22% | 14% | 14% | 13% | 8% | 62% | 311 |

     Discovery falls steadily with sparsity in both stages (S: 81, 71, 42% at k = 2), so three levels give a usable dose-response. T's trapping falls with sparsity (27, 16, 13% at k = 2), and T2F-15 is hardest to
     get right because its two peaks are wide and close in absolute terms; the T2F-15 global discovery is below T2F-10 at the agents' pace, so T is not monotone in discovery (fewer bushes outside the two peaks to
     be distracted by, but the margin of 1.0 packs them together). The ratio 0.5 is a new value, untested before rw5.
     **Power of v9** (`rw_power_sparsity.py`; 3 iterations x 3 sparsities per stage per participant, participant random intercept sd 0.8, cluster-robust t-test at 0.05, 400 reps; the agents' person-proxy
     slopes, or half as strong). Power to detect the sparsity slope of discovery:

     | person slowdown, effect | S, N = 20 / 40 / 60 | T, N = 20 / 40 / 60 / 100 | stage x sparsity, N = 60 / 100 |
     |---|---|---|---|
     | 2x, as agents | 99 / 100 / 100% | 57 / 89 / 99 / 100% | 68 / 88% |
     | 2x, half as strong | 54 / 84 / 96% | 21 / 33 / 54 / 75% | 20 / 33% |
     | 3x, as agents | 91 / 99 / 100% | 46 / 76 / 91 / 99% | 67 / 87% |
     | 3x, half as strong | 32 / 70 / 84% | 14 / 28 / 36 / 56% | 21 / 37% |

     T's trapping slope over sparsity is about as detectable (2x as agents: 46 / 75 / 90 / 99%; half: 21 / 29 / 42 / 60%). S is well powered at N = 40; **T needs about 60 for the full-strength effect and more than 100
     if people show half the agents' slope**, because T's discovery is low at every level; the stage-by-sparsity contrast is weakest.
   * *v9.1 (PI, 2026-11-10): T's sparsities become 15%, 11% and 7%* (S stays 15, 10, 5%). Screen rw6 (`--design tsweep`, T at 15, 13, 11, 9, 7, 5%, 200 worlds per cell, strict, 180 s): global found at a person 2x slower
     48, 43, 42, 38, 26, 22% (3x: 34, 31, 28, 23, 17, 13%); trapped at 2x 24, 20, 16, 13, 15, 13%. 5% is at the floor (22% found), so it is dropped from T; 15/11/7 keeps the range of discovery (49 to 26% at 2x)
     and raises its level. Power of the T slope of discovery at N = 40 / 60 / 100: 89 / 97 / 100% (2x, as agents), 36 / 59 / 79% (2x, half as strong), 86 / 96 / 100% (3x); that of trapping falls to
     40 / 57 / 75% (2x), because trapping is flat between 11% and 7%. The cost: S and T no longer share sparsity levels, so the stage-by-sparsity contrast compares slopes, not matched cells. **The levels, lengths, ratio and
     separation are plain entries of the design table, so the pilot (about 8 to 10 people, to measure the slowdown k) sets the final ladder: fixed in advance, the middle T cell aimed at about 50% global discovery.**
   * *Built (2026-11-10 and 11; `scripts/design/RW.py`, `scripts/test_rw_design.py`; development build deployed).* 22 sessions: B1 to B4 (120 s), then the nine S and nine T sessions (180 s: S at 15, 10, 5%, T at 15, 11, 7%
     total, 3 iterations each, the first iteration of each of the six cells in a seeded random order before the later ones), T at the ratio 0.5 and the separation 4.5 spreads. Every number the pilot may move is a constant of the module;
     rebuild with `build_experiment.py RW`. **Where it differs from the plan above:**
     * *Interludes: 20 trials in every session, 17 distinct pairs plus 3 exact repeats* (PI), so the count gives nothing away (FN's baseline had 5 and 10). Two peaks: 6 global against local, 6 global against off, 5 local against off,
       one repeat of each type; one peak: 17 peak-against-off pairs and 3 repeats. Reward gaps are spread evenly within a type (0.25 up to the 95th percentile of what the type offers), bushes of different trials differ by more than
       0.07 in shape or colour where the pool allows, repeats are at least 8 trials from their source and alternate the correct side. A peak bush is one that pays at least 70% of its peak (the sparsity definition; the first build used
       90%, and its peak bushes looked alike from trial to trial). `interludePeakTrials` in `SessionConfig`; the fingerprint leaves it out at 0, so no stored result hash moved.
     * *The margin is 0.7 spreads for every cell* (was 1.48, and 1.0 for T): the smallest at which no instance's realised sparsity falls more than 10% below the untruncated peak's (600 draws per cell; 0.65 gives 11%). Peaks can sit
       near an extreme, so extreme feature values are no longer always poor.
     * *The ground varies* (`moistureVaries` on, `moistureIsFeature` off, weight 0): the screens ran on a flat valley and the first build copied that. The power and screening results above are for a flat valley and the old margins; not re-run.
     * *Hints:* both features or one feature; B1 and B2 add "most bushes give few points", B3 and B4 add "two kinds of valuable bush"; S and T say only which features matter. The two sentences are on separate lines.
     * *Time:* about 62 minutes of play, plus the Interludes: at most 20 trials of 7 s per session at the cap (51 minutes over 22 sessions); the one test run showed a median response of 2.3 s, so expect well under that. Not measured end to end.
     * *Checked:* the built Interlude files of all 11 two-peak sessions (counts, repeats, sides, gaps); a logged run showed the one-peak Interludes (B1, B2) playing and logging as type `peak`. A two-peak Interlude (B3) also played and logged: 10 trials in a `short=0.5` run, type `peak`, all three pair types (`0>1` 5, `0>off` 3, `1>off` 2), no timeouts; its repeats were not in the shortened half. A run resumed across two deployed builds mixes their world files (`pull` warns).

---

## Learning with feature interactions (FI)

1. **Display name:** feature interaction (FI)
2. **Hypothesis:**
   1. Learning is slower and the performance ceiling is lower the more the reward depends on the combination of shape and color rather than
      on each feature separately.
   2. The cost grows from rules that are monotone in both features, to rules with a peak in one feature, to rules that are not separable by
      feature (a tilted peak).
   3. At a given sparsity, sharper sigmoids make the high-reward region harder to find, because the reward gives no gradient outside it.
3. **Experiment:**
   1. *Features and terms.* Only shape and color are used (no moisture). Both vary, and both always matter. Write x and y for the two features
      scaled from 0 to 1, with roles and direction (which end pays) drawn per instance. Bushes sit on a hexagonal lattice, with reward density
      roughly uniform. Sparsity is as defined in "Conventions", and is matched across types, so a harder type is not simply a sparser one. The
      maximum reward and per-fruit noise are matched too.
   2. *Session types, from simple to complex:*
      * Additive. Reward is w₁·x + w₂·y. No interaction; the baseline.
      * Sigmoid × sigmoid. Reward is sigmoid(x) · sigmoid(y), with the steepness and inflection point of each set per instance. Both features
        must be high, and the maximum is at one corner of the feature space. Shallow sigmoids approximate the product x · y.
      * Sigmoid × Gaussian. Reward is sigmoid(x) · Gaussian(y). One feature gates the reward and the other has a peak, so the optimum is at an
        interior value of y and a high value of x.
      * Tilted bump. A 2D Gaussian that is elongated and rotated, so the reward depends on a combination of the two features. It is not
        separable, so searching one feature at a time stalls, and the optimum is in the interior.
   3. *Parameters.* For sigmoid × sigmoid: the steepness and inflection point of each sigmoid. For sigmoid × Gaussian: the sigmoid's steepness
      and inflection point, and the Gaussian's center and width. For the tilted bump: the tilt angle, the elongation and the widths. These are
      set to match sparsity across types, and the remaining freedom is used to vary the steepness at fixed sparsity.
   4. *Instances.* Each session is an instance from a pool with its own world seed and draw of roles, directions and positions.
   5. *Order and intermixing.* The additive session comes first, then a first pass of the other types from simple to complex. Later instances
      of each type are intermixed in random order.
   6. *Hints.* The additive session says both features matter independently. The first pass of interaction sessions says the combination of the
      two features matters. Later sessions have no hint about the structure.
   7. **TODO, how many instances of each type and the session length.** Harder types need longer sessions. How to choose the steepness values so
      that shallow and steep sigmoids differ clearly at matched sparsity.
   8. *Other open items.*
      * Interlude trials. With steep sigmoids the reward is nearly flat in each region, so two bushes in the same region have no correct side.
        Informative pairs are across the boundary (high region against low region), and pairs near it. The tilted bump needs pairs along and
        across its long axis. Ties need a rule.
      * The generator must populate every region (the high corner, the transition, the far low region, the ends of the bump) and assign the
        (shape, color) records evenly (`spatialBalance`).
      * How well the simulated agents' critics learn each type (additive against joint features), to screen the types and calibrate the lengths.
4. **Analysis:**
   1. Point trajectories of reward against time in each session and type.
   2. Interlude choices fitted by a ladder of models: additive, multiplicative (additive in the log of the reward), and a full joint model.
      The best model per participant and type shows what kind of rule was learned and how far the learned value function is from the true one.
      (Three of the four types are products of a function of each feature, so a multiplicative model is needed to tell "learned a product
      rule" from "learned a joint rule".)
   3. For the sigmoid types: how long it takes to find the high region, and how that depends on steepness at matched sparsity.
   4. Direct comparison of types at matched sparsity.
   5. Instance index as a covariate, to see whether people learn to look for interactions.

9. **Implementation plan, proposal v1 (PI, 2026-11-11; nothing here is built).** **The linear additive session is replaced by a sum of sigmoids** (PI): the separable baseline with the same marginal terms as sigmoid x sigmoid, so the two differ only in the combination rule (a sum of linear terms against a sigmoid product would differ in the nonlinearity as well); a shallow sum is nearly the old additive rule. Phases, in order; the agent screen comes after the experiment is built and playable.
   1. *New reward terms* (C# and the Python mirrors, `world.bush_value`, `terms_relevance`, the fingerprint with new fields omitted at default, the builder's array paths; C# against Python compared on a grid): `angle` on `RewardBump` (0 = today's bump, so RW and stored hashes
      do not move), and one new term of two factors, each a sigmoid (centre, steepness, direction; normalised to 1 at its paying end, so the maximum is `height`) or a Gaussian (centre, width).
   2. *Instance generator `fi_terms.py`:* per type (sum of sigmoids, sigmoid x sigmoid, sigmoid x Gaussian, tilted bump) a class with the interface `Peaks` has (`value`, `dims`, `paying`, `reward_function`, `session_fields`), so `rw_peaks.sparsity`, the region
      counts and `rw_screen.session_params` serve it unchanged. The shared pieces of RW's design module (the seeded play order, the world-seed search with a guarantee check, the instruction pages) move into `design/common.py`, RW's instance list verified
      identical before and after; FN stays as it is. Roles (which feature is x), directions and positions are drawn per instance as in FN (direction 0 higher pays, 1 lower) and RW. **Sparsity is matched across the types** by solving each type's free
      parameter (the sigmoids' inflection point, the Gaussian's width, the bump's scale) to land within 10% of the target; the target and the region definition `x` are table constants. **Measured on the plane (top-x% region):** linear additive reward (no longer a session; the sum of sigmoids is) with both features
      mattering is at x = 30 only 0.18 to 0.24 (weight ratio 1 to 0.3; 0.29 needs one feature to carry 5%), at x = 40 0.32 to 0.37, at x = 50 0.50; sigmoid x sigmoid reaches any of these at any steepness (k = 30, c = 0.4: 0.32 at x = 30), and the sum of sigmoids can be matched to the product by shifting its inflection point (k = 10: the product at c = 0.4 has 0.25 / 0.29 at x = 30 / 40, the sum at c = 0.5 has 0.25 / 0.33). So a
      matched 30% needs x = 40 (the best bush's 60%, not RW's 70%) for the linear rule, which the sum of sigmoids makes unnecessary; **x and the target are to be decided by playing.** Additive and shallow-sigmoid rewards pay nonzero over 98% of the plane, a steep sigmoid product only inside its high region
      (0.32 at c = 0.5; the steep sum 0.80, since a bush with one feature high pays about half): that difference is the steepness effect (hypothesis 3) and the sum-against-product contrast, and the target is chosen high enough that finding a nonzero bush is not what the session measures.
   3. *Interlude trials (typed, like RW):* 20 in every session, 17 distinct pairs plus 3 exact repeats (one per class), so the count gives no hint of the type; a new count field `interludeInteractionTrials`. **Tie rule:** no pair is shown with a true gap under
      0.25 (five times the tie tolerance), so two bushes in one flat region never meet and every trial has a correct side. Classes by the true reward level (high: at least 70% of the maximum; low: at most 25%; the rest transition), with a per-type table of counts:
      sum of sigmoids: one-feature-only pairs for each feature, trade-off pairs, one feature high against both mid (ordered differently by the sum and the product), high against low; sigmoid x sigmoid: high/low, high/transition, transition/low, graded within the transition; sigmoid x Gaussian: the same plus gate-only and peak-only pairs; tilted bump: centre against along the
      long axis, centre against across the short axis, along against far. Gaps spread evenly within a class, look-alike bushes avoided, repeats at least 8 trials from their source (as RW). A steep sigmoid has a thin transition band: the build checks that every class
      has candidates and fails loudly otherwise. **Reversal pairs** (the best additive fit to the true reward orders the pair the wrong way; they separate the additive, multiplicative and joint models of the analysis) are a class the table can hold at 0 trials; their share
      among the other classes' pairs is computed from the built files, and agent tests decide whether a class of their own is needed.
   4. *`design/FI.py`, table-driven:* for the sum of sigmoids, sigmoid x sigmoid and sigmoid x Gaussian two levels each (shallow k about 4, steep k about 30), for the tilted bump one (elongation about 3.5, tilt 20 to 70 degrees off an axis), 3 iterations each:
      **21 sessions** (6 + 6 + 6 + 3) (reduced runs by the `short` and `repeats` knobs as in FN and RW). Order: the shallow sum first, then one pass of the other cells from simple to complex (sum steep, sigmoid x sigmoid, sigmoid x Gaussian, tilted bump; shallow before steep), then the rest shuffled by the master seed. Lengths 120 s (sum of sigmoids)
      and 150 s (the others), provisional; about 51 minutes of play plus the Interludes (at most 49 minutes at the 7 s cap), so the lengths are the first thing to trim. The ground varies and pays nothing (`moistureVaries` on). Hints (concise): the sum of sigmoids, "Shape and color **add up**:
      each one adds its own part to the reward."; the first pass of the other three, "The reward depends on the **combination** of **bush shape** and **fruit color**, not on each alone."; later sessions none. Build, check the generated files, development build, play check.
   5. *Agent screen after the experiment is built* (`fi_screen.py` on the `rw_screen.py` pattern, with an `AdditiveFeatures` critic beside the joint RBF one, to see whether a separable learner copes with the sum and fails on the products): calibrates lengths and iteration counts, tests whether reversal pairs are redundant, and gives the power analysis.
   6. *Later:* the analysis model ladder (additive, multiplicative, joint), recovery tests on agents, the pilot.

---

## Patch leaving (PL)

1. **Display name:** patch leaving (PL)
2. **Hypothesis:** when valuable bushes are unevenly distributed in clusters, people learn to take a cluster down and then go to another good
   one, even if they give up immediate reward on a longer walk. The longer the walk, the longer they stay in a cluster, and the richer the
   other clusters, the sooner they leave. Efficiency relative to the optimal policy improves over sessions.
3. **Experiment:**
   1. *Features and terms.* A *tile* is a cluster of bushes (a hexagonal tile with several bushes near its center), and tiles are far apart. The
      *travel cost* τ is the walking time between tile centers divided by the time to harvest one bush. The *patch contrast* ρ is the difference
      in mean reward between tiles divided by the spread of reward within a tile. The *marginal value theorem* says to leave a patch when the
      instantaneous reward rate falls below the average rate of the whole environment, including travel. Elevation and moisture distinguish tiles
      visually and do not pay.
   2. *Reward function.* Easy to learn: linear in one feature (shape or color), with the direction and the feature drawn per instance, so each
      session starts without knowledge. Bushes within a tile are similar in that feature (low diversity), and tiles differ in it, so the value
      of a tile is readable once the rule is known.
   3. *Layout.* The number of tiles and bushes per tile are fixed in this experiment. The tile distance varies across sessions, in a way that
      keeps the number of tiles fixed (**TODO**: how, given the bounded terrain).
   4. *Time scarcity.* The session is always too short to harvest every tile, so a participant must choose between exhausting the current tile
      and travelling. The session time is set relative to the time to exhaust one tile and walk to another, and is held at the same ratio in
      every session.
   5. *Sessions.* Each session combines a level of travel cost (short, medium, long) and a level of patch contrast (low, high). Each cell has
      several instances with different tile layouts and feature draws.
   6. *Order and intermixing.* The first session has short travel and high contrast, where the right policy is clearest. Later sessions are
      intermixed in random order, so participants cannot predict the cost.
   7. *Knowledge state.* Not told to participants. The hint says only what the controls and the timer do. Knowledge of the reward function is
      inferred from the progression of each participant's bush choices.
   8. **TODO, the design:** the number of levels of each axis and the instances per cell, the session length, how to keep the number of tiles
      fixed as distance grows, the hint wording, and whether to add a short Interlude after each session to check the learned function.
   9. *Other open items.* `spatialBalance` evens the reward across the map, the opposite of what this experiment needs, so it must be off or
      applied only within tiles. Clustered tiles need a new placement mode in `scripts/world.py`.
4. **Analysis:**
   1. Once the reward function is learned (inferred from choices) and tile value is easy to read, how efficient is the patch-switching policy?
      Efficiency is the reward collected relative to an oracle that knows the function and follows the marginal value theorem in the same world.
   2. Leaving gap: the instantaneous reward rate at the time of leaving a tile, minus the environment's average rate. The theorem predicts zero.
      How does it depend on travel cost and patch contrast?
   3. Before the function is learned, how does exploration split between bushes within the current tile and new tiles?
   4. Which tile do participants go to next: the richest, the nearest, or a trade-off between them?
   5. The time from the start of the session to the point where choices track value, and whether it changes over instances.

---

## Patch assessment (PA)

1. **Display name:** patch assessment (PA)
2. **Hypothesis:**
   1. When the value of a patch is hard to judge at a glance, people are less efficient at leaving patches, but they learn how to explore and
      exploit over time and across sessions.
   2. When the learning rule and the diversity of bushes within a patch are complex enough, people develop moderately efficient heuristics but
      never explore enough to approach the optimal behavior.
3. **Experiment:**
   1. *Features and terms.* A tile is a cluster of bushes. The *patch size* is the number of bushes in a tile. The *diversity* is the spread of
      bush values within a tile. The patch contrast is the difference in mean reward between tiles divided by the spread within a tile.
      *Glanceability* is how many of a tile's bushes can be seen at once from its edge, which the view cone and terrain occlusion limit.
      Elevation and moisture distinguish tiles visually and do not pay.
   2. *Reward function.* An additive linear function of shape and color with unequal weights, so the value of a tile needs several bushes to
      judge. The features and directions are re-drawn per instance, so each session starts without knowledge.
   3. *Sessions.* Each session combines a patch size (for example few, medium, many bushes) and a diversity level (low, high). Sessions are much
      longer than in patch leaving, to allow time for the transition from exploring to exploiting. Because a larger tile is richer in total and
      takes longer to exhaust, the time scarcity ratio (session time relative to the time to exhaust one tile plus a walk) is held constant
      across sizes. The session is always too short to harvest every tile.
   4. *Patch contrast across sessions.* Contrast is high in early sessions and low in later ones. When contrast is high, looking around to get
      a quick sense of the other patches' mean values pays off, so early sessions favor that kind of exploration. When contrast is low it does
      not, so later sessions test whether people adapt how much they look around. (Contrast is then confounded with practice; a second group
      with the reverse or a random order would separate them, at the cost of more participants.)
   5. *Order.* The first session has few bushes and low diversity. The order of the later cells is random within each contrast stage.
   6. *Knowledge state.* Inferred from the progression of each participant's bush choices, as in patch leaving, not given by a hint.
   7. **TODO, the design:** the levels, instances per cell, session length at constant scarcity, the hint wording, how to hold the mean bush value
      fixed across sizes, and where the contrast switches from high to low.
   8. *Other open items.* The same placement mode and `spatialBalance` points as in patch leaving. How to set glanceability, which depends on the
      placement and the terrain, so it is partly confounded with size.
4. **Analysis:**
   1. Efficiency (reward collected relative to an oracle that knows the function and follows the marginal value theorem in the same world)
      against the number of bushes per tile and the diversity within a tile.
   2. Meta-learning: how efficiency and the leaving gap (the reward rate at leaving minus the environment's average rate) change within a session
      and across sessions. Do people reach the transition from exploring to exploiting sooner in later sessions?
   3. Heuristics: fit candidate rules to the logs. Leave after a fixed number of bushes, leave after a run of low rewards (giving-up time),
      leave when the last reward is below a threshold, leave by an estimate of the tile's mean from the bushes sampled, and the marginal-value
      rule with the true value. Which fits best, and does it change over sessions?
   4. Exploration shortfall: how many tiles are sampled before settling, compared with how many the optimal policy would sample. A shortfall
      that persists is what the second hypothesis predicts.
   5. Looking around: how much of a participant's early time in a tile or on arrival is spent sweeping the view (yaw changes, peeks at
      neighbouring tiles) without harvesting, and how it differs between high-contrast and low-contrast sessions.
   6. Before the function is learned, how does exploration split within and between tiles?
