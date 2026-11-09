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
   4. *Weighted sessions: three visible features, all of which can pay.* These are long, with more repeats and more Interlude trials.
      * Three randomized weights sum to one, and a variety of weight breakdowns across the three features is simulated to get broad coverage
        of the complexity and threshold space.
      * Goal: find the relative weights. Hint: all three features matter, but some matter more than others.
      * **TODO:** how to distribute the normalized weights so that they cover the weight space in a way that makes hypothesis testing
        straightforward. Considerations so far: express a weak feature's strength in noise units (its weight times its range of values, over
        `rewardStd`); joint sampling of the two weak weights over a grid including zeros against a one-parameter family such as (1, r, r²); a
        fixed strongest weight against a fixed total; how many instances a participant sees from a larger pool; whether to adapt the weights
        to a participant's previous Interlude.
   5. *Order.* The three baseline sessions come first, from simple to complex; the weighted sessions follow in a random order of their weights.
   6. *Status (2026-11-09).* Built as `scripts/design/FN.py` with provisional numbers: the weak weights use the stand-in family (1, r, r²)
      for r = 1, 0.7, 0.5, 0.35, 0.2, 0.1 over a random ranking of the features; baselines last 60, 75 and 90 s with 8 Interlude trials;
      weighted sessions last 150 s with 24 trials (2 repeats, 2 per-feature trials for each feature that pays enough to show). Durations
      and trial counts wait for measured Interlude timing. Moisture is the third feature (flat, single-coloured ground where it is not
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
