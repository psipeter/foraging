# docs/SCIENCE.md — scientific goals, task design, and results

This is the scientific record: what the project is trying to show, how the
task operationalizes it, and what has been found. For code conventions see
`CLAUDE.md`; for the reasoning behind past design choices see
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

The first study within that program asks how people learn a reward function
defined over continuous tree attributes (see "Task design"). Participants
harvest trees whose reward depends on three attributes; the
researcher-defined reward function is the independent variable, and the
dependent variable is which trees participants harvest and in what order
(plus movement/visibility data from the logs). The platform is meant to
outlast any single question.

**Hypotheses have not been written down yet.** When they are, they go here.

Key constraint: attributes must be clearly visible and perceptually
independent, and reward feedback must be unambiguous.

### Four features of "naturalistic" we care about

| # | Feature | How the current build realizes it |
|---|---|---|
| 1 | **Multidimensional, continuous-valued features** | Each tree has three continuous attributes (shape, fruit color, moisture), each on its own visual channel; reward is a function over all three |
| 2 | **Multiple potential actions at every timestep** | ~150 trees in the world at all times; the participant can approach any, harvest any in range, or keep exploring |
| 3 | **Continuous time and space** | Free movement in a continuous 3D world; a continuous sunrise→sunset clock; travel and harvesting both cost time; no trial structure |
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
  attributes (linear and Gaussian-peak basis functions over one to three
  features) sits directly in this line, moved into an embodied,
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
chosen to carry weak priors (constant fruit count; blue→orange rather than
red/green), so learning of the reward function is attributable to experience.
That trades some naturalism for interpretability — a deliberate position, not
an oversight.

---

## Task design

- **Session:** fixed duration per session (P 60 s, S1 90 s, S2/S3 120 s, S4 150 s), the
  second part of a day cycle: the session starts `dayStartFraction` (0.3) of the way from
  sunrise to sunset and ends at sunset. Movement costs time (fixed player speed); harvesting costs
  `fruitHarvestDuration` seconds per fruit (0.25 s; 10 fruits = 2.5 s per bush); player speed 7.5.
  Goal: maximize total reward.
  **Harvesting (first person):** bushes glow gradually as you approach them, in
  proportion to horizontal distance from the canopy edge (glow begins 20 units out,
  full at 7) and to how directly they are in front of you (full within 25° of straight
  ahead, none past 45°; yaw only, after subtracting the bush's angular radius). The glow
  never reveals reward. A bush becomes harvestable within 7 units of its
  canopy edge and within 35° of straight ahead; the best such bush (closest to
  center) is shown as selected, and a "Hold SPACE to harvest" hint appears.
  A clock-style progress ring floats above every bush in harvest range (constant
  apparent size, camera-facing): a faint full track with the bright arc erased clockwise
  from 12 o'clock as fruits are collected, so you can see how much is left even if
  the fruits are on the far side, or on returning to a bush; progress through the fruit
  in hand is kept on the bush. An exhausted bush stays as a landmark and obstacle but
  eases into a "spent" look (uniformly shrunk to 70%, drab canopy tint), so depleted bushes are
  distinguishable from afar; there is no external record of which bushes are left beyond that.
  Highlight: a soft glow on the bush's edge that grows as you approach, plus a thin crisp edge line on the
  selected bush, in a slightly different rim color once selected. Holding Space collects one fruit every `fruitHarvestDuration` (the fruit
  nearest the camera first); walking is locked while Space is held, looking stays free.
  Looking more than 35° away pauses the harvest (hint: look back); releasing Space
  ends the bout, and a fresh press starts the next one. +X popups appear at a fixed
  screen slot, and the score updates per fruit. Optional `harvestLookResistance`
  (default 0, off) slows mouse yaw to zero as you turn away from the bush.
- **World:** ~685–695 trees (P, S1–S4; the count follows from the valley area; `worldHalfExtent` 350, valley
  about 580 units across) placed on a
  jittered hexagonal lattice (`treeSpacing` 23, `placementJitter` 0.5; nearest-neighbour
  distance ≈ 18.6, CV ≈ 0.13, no pair closer than 11.5, so ≈ 2.5 s walk to the
  nearest bush at speed 7.5), on Perlin-noise terrain, in a valley enclosed by an
  unclimbable rocky/snowy mountain band built into the terrain (no trees on it).
  A per-session `worldSeed` fixes the terrain, the mountain skyline, the tree
  layout/attributes, and every per-fruit reward (all generated by `scripts/world.py`
  and loaded by Unity from `StreamingAssets/Worlds`).
- **A participant plays a sequence of sessions** (`P`, `S1`–`S4`), each with
  a different world seed and reward function. `P` is an unanalyzed practice
  session (`SessionConfig.isPractice`): its end screen says "Practice Complete" and it
  is not counted in "Session x/4". Between sessions the player sees a score screen and
  continues with Enter (Space is reserved for harvesting).
- **Instructions:** the file shown before each session is `SessionConfig.instructionsFile`
  (`{session}`/`{total}` placeholders count non-practice sessions). Practice
  (`instructions.txt`) gives the goal and controls ("different bushes give different points";
  walk next to a bush and hold SPACE), keeps a faint controls reminder on screen all session
  (`controlsReminder`, `controlsReminderOpacity`), and after the first harvest that collects fruit
  pauses on a one-time message (`firstHarvestMessage`: "Harvesting this bush earned X points ...
  explore which tree features earn points by harvesting different bushes"; Enter resumes).
  S1–S4 each have their own file (`instructions_S1.txt`–`instructions_S4.txt`): "This is a new
  world. The features that determine reward are now different (S1) / more complicated (S2) /
  even more complicated (S3, S4). Continue to explore and collect as many points as you can."
  The wording never says "higher is better" and does not describe the structure of the
  mapping. Note S3 and S4 use identical text, and S1 says "different" (not "more complicated")
  because S1's complexity equals the practice session's.
- **Camera (all sessions):** first person — mouse looks (yaw + pitch), W/S walk
  forward/back along the view direction, no strafing. Eye height, vertical
  field of view, and mouse sensitivity are `SessionConfig` fields; the
  metadata JSON records the camera's FOV, pose, and clip planes. See DECISIONS.

### Reward feedback (HUD and audio)

Each harvested fruit gives: a "+X" popup at a fixed screen position (pale gold with a dark outline, pops in
with an overshoot and wobble, rises and fades); the score counts up with a brief flash and punch; a short
synthesized blip whose pitch rises with the reward; and a small burst of spheres in the fruit's own color. An
exhausted bush plays a soft two-note chime. The timer sits in a matching plate; it has no bar and no end-of-session warning
(deliberately kept plain).

Reward-dependent salience is a **scientific parameter**, not decoration: the number is always shown, but popup
size/brightness (`rewardSizeScaling`, `popupExtraScale`) and pitch (`pitchSemitoneRange`) can scale with the
per-fruit reward, up to `rewardFeedbackMax`. This adds a second, graded cue next to the number; set the scaling
to 0 (and the pitch range to 0) for identical feedback on every fruit. Feedback colors are pale and near-neutral
so they do not read as part of the fruit hue axis. Defaults (full scaling, 7 semitones) are untuned starting
values; record the values used when collecting data (they live in `SessionConfig`).

### Attributes and their visual channels

Each tree has three attributes in [0, 1], each on its own visual channel:

| Attribute | Visual channel | Ecological level | Prior strength |
|---|---|---|---|
| **Shape** | Canopy aspect ratio (squat/wide → tall/narrow) | Tree | Weak |
| **Color** | Fruit hue (blue → orange, abstract axis) | Fruit | Weak |
| **Moisture** | Ground color + terrain elevation | Environment | Weak–moderate |

- `shape` and `color` are drawn independently and uniformly per tree.
- `moisture` is **not** drawn per tree: it is sampled from the terrain's
  moisture field at the tree's position (so it is spatially autocorrelated,
  and trees in wetter areas sit on lower ground — elevation is
  `(1 − moisture) × maxElevation`).
- **Prior management:** fruit count is constant across bushes (no count-based
  prior); fruit color uses an abstract blue→orange axis (avoids red/green
  ripeness associations). Fruits are unlit so hue is always readable;
  canopy and terrain respond to the day/night lighting.
- Fruits are distributed over the canopy with a Fibonacci/sunflower spiral
  with per-tree seeded jitter.

### Reward system

`R_bush = w₁·f₁(shape) + w₂·f₂(color) + w₃·f₃(moisture)` with **no
normalization** (a deliberate research decision, not an oversight).
Basis functions `f`: Linear, InvertedLinear, GaussianPeak (peak, width),
InvertedGaussian, Constant. Each fruit's reward is an independent draw,
`max(0, round(N(R_bush, rewardStd)))`; the harvest pays the sum over the
tree's fruits, shown as floating numbers rising from each fruit and a
running score.

### Session configurations

All five: `rewardStd` 0.3, 10 fruit/tree, speed 7.5, `fruitHarvestDuration` 0.25, first-person camera, `worldHalfExtent` 350,
`terrainMeshResolution` 449, ~685–695 trees
(seed-dependent: P 686, S1 694, S2 688, S3 685, S4 695). Weights apply to (shape, color, moisture).

| Session | Seed | Duration | Shape | Color | Moisture | Character |
|---|---|---|---|---|---|---|
| P (practice) | 100 | 60 s | Linear, w=3 | w=0 | w=0 | one feature, linear (mechanics) |
| S1 | 1 | 90 s | w=0 | Linear, w=3 | w=0 | one relevant feature of three |
| S2 | 2 | 120 s | GaussianPeak, w=3, peak 0.65, width 0.2 | w=0 | w=0 | one feature, non-monotonic |
| S3 | 3 | 120 s | w=0 | Linear, w=3 | Linear, w=1.5 | two features, linear |
| S4 | 4 | 150 s | InvertedLinear, w=2 | Linear, w=3 | Linear, w=1.5 | all three, additive, monotonic, one inverted |

(Read from `Assets/ScriptableObjects/SessionConfig/*.asset`; the assets are the source of
truth and may have moved on — re-check before citing.) The relevant feature rotates
across sessions so a "it's always shape" rule can't carry over. The S2 peak is off-centre
(0.65) so it is not just "avoid the extremes". Earlier designs explored five configs, then
a 60 s S1–S3 (one linear; three linear; mixed), replaced by this progression; see DECISIONS.

### Session progression (P–S4 implemented; S5 is a TODO)

Goal: each session is long enough for a participant to sample many bushes and
learn the reward mapping, but not so long that most of it is spent exploiting a
fully learned rule; and complexity increases across sessions so learning takes
progressively more stops. Rationale and rejected alternatives: DECISIONS
("Session progression").

**Time budget logic.** The first sizing assumed player speed 5 and 0.5 s per fruit:
~9 s per full-harvest stop (5 s harvest + ~3.7 s walk), so 60 s held only ~7 stops, too few to
learn and then exploit anything beyond one feature. Speed was then raised to 7.5 and harvesting
doubled to 0.25 s per fruit, so a stop is now ~5 s (2.5 s harvest + ~2.5 s walk): roughly 1.8×
the stops per session at the same duration (about 12 / 18 / 24 / 24 / 30 stops for
P / S1 / S2 / S3 / S4 if full-harvesting). **The durations in the table below were sized for the old
~9 s stop and have not been retuned: TODO(PI) shorten them (≈ 50 / 70 / 70 / 85 s keeps the
original stop counts) or keep them and accept longer exploitation phases.**
Because `rewardStd` is 0.3 and a bush has 10 fruits, a bush's value is known almost exactly after
1–2 fruits: **each visited bush is roughly one clean (attributes → reward) data point**, and the
difficulty is credit assignment, not noise. A one-fruit "peek" now costs ~0.25 s + walk (~2.5 s)
versus ~5 s for a full-harvest stop, so peeking is cheaper in absolute terms but saves about half
a stop rather than ~90%; whether participants discover this is itself a measurable behavior.
Session lengths target learning taking ~35–50% of the stops.

| Session | Reward structure (shape, color, moisture) | New concept | Duration (~stops) | Expected learn point (stops) |
|---|---|---|---|---|
| P (practice, unanalyzed) | shape linear, others 0 | controls, harvest mechanic | 60–90 s | n/a |
| S1 | one feature linear, two distractors | credit assignment | 90 s (~10) | 4–6 |
| S2 | one feature Gaussian peak, others 0 | non-monotonic value | 120 s (~13) | 7–10 |
| S3 | two features linear, third irrelevant | integrating two features, relative weights | 120 s (~13) | 7–10 |
| S4 | all three non-zero, additive, monotonic, unequal weights, at least one inverted | integration over all three; "higher is better" is not a safe default | 150 s (~16) | 10–14 |
| S5 | **TODO(PI)** — one interacting pair plus one additive feature (provisional) | feature-wise learning fails; interactions, non-monotonic | 210–240 s (~24–27) | 15–22 |

Stops-to-learn figures are guesses, to be calibrated by a model-based learner
agent and then by pilots. Durations are likewise provisional. P–S4 are implemented as
the table above (P is 60 s); S5 is not built.

- **S2 before S3.** S2 isolates one new idea (non-monotonic value) while one
  feature is relevant. It also tests whether the linear prior built in S1
  carries over (choosing extreme attribute values). S3 → S4 then adds one
  feature at a time, with no step back in function complexity.
- **S4 is the first all-three-relevant session** and is deliberately additive
  and monotonic. It may already be hard enough; S5 should not be committed until
  S4 pilot data exist.
- **S5 is a TODO.** The code supports only additive rewards today
  (`R = Σ wᵢ·fᵢ(attrᵢ)`); interactions (product term, 2D Gaussian ridge, pairwise
  term plus additive terms) are a scientific and code change touching
  `RewardFunction`/`RewardComponent`, `scripts/world.py` (which mirrors the reward
  rules) and the metadata JSON. Provisional plan: one interacting pair plus one
  additive feature, not a fully arbitrary 3D function (probably unlearnable in
  ~25 stops, and a null result would be uninterpretable). Prediction to test:
  feature-based learners (Farashahi et al., 2017) do well in S1–S4 and fail on
  the interacting pair.
- **Instructions must not imply monotonicity** ("reward depends on the tree's
  features", not "higher is better").
- **Extra difficulty knobs:** raising `rewardStd` (≈1.0) in later sessions slows
  per-bush estimates without touching the visual channels; a moisture-driven
  reward adds regional structure (and the spatial-autocorrelation confound
  noted under open questions).
- **Calibration metrics for pilots:** predicted R of the bush chosen at stop k
  vs. k; the stop where choices first exceed a rank-correlation threshold with
  true R; fraction of the session left after that stop (target median ≈ 50%).
- **Alternative left open:** counterbalancing S2/S3 across participants (similar
  expected difficulty; would allow comparing learning a nonlinearity with
  learning feature integration, at the cost of sample size and an order factor).

---

## Data

Per session, `ForagingData/<sessionId>/`: `movement.csv` (0.1 s samples),
`harvests.csv`, `session_metadata.json` (config, reward function, camera,
full tree registry with true rewards). Format details live in `CLAUDE.md`
("Data logging").

State of the data: everything currently in `ForagingData/` (~395 session
folders) is **debugging output**. No dev or participant data has been
collected, and collection is a long way off. There is no participant-ID entry
yet (planned). Once real collection begins, this section should say which
sessions are real and how they map to participants.

---

## Findings and current thread

**No analyses of human data are recorded in this repo.** The only results are
the simulated agent baselines below (code in `scripts/`).

### Simulated agent baselines (preliminary, STALE)

**These numbers were computed before the speed, harvest-rate and map-size changes** (speed 5,
0.5 s per fruit, `worldHalfExtent` 200 with ~140 trees; session durations as in the table below). Player speed is
now 7.5, fruit harvest 0.25 s, and the map ~5× larger in tree count, so the table, the
percentages and the "stops per session" notes do not describe the current build. Baselines are
re-run on request only, not after every change.

Reward per session for three reference agents with a known map, run on
the same worlds (seeds 0–99, `python scripts/sim.py <S> --seeds 0-99 --agents
nearest,greedy_rate_15,plan_beam --baseline nearest`) at each session's own
duration. Mean ± standard deviation across seeds; "vs nearest" is the paired
difference ± SE. Rewards include the fruit noise (`rewardStd` 0.3).

| Agent | What it knows / does | P (60 s) | S1 (90 s) | S2 (120 s) | S3 (120 s) | S4 (150 s) |
|---|---|---|---|---|---|---|
| `nearest` | nothing about value; walks to the quickest-to-reach bush, harvests it empty, repeats | 95.4 ± 25.0 | 167.7 ± 32.8 | 202.8 ± 42.4 | 332.3 ± 38.9 | 608.9 ± 48.9 |
| `greedy_rate_15` | full map and true `R_bush`; goes to the bush with the best expected reward per second (walk + harvest) among those within 15 s of walking; no planning | 152.4 ± 12.8 (+57.0 ± 2.8) | 231.3 ± 16.2 (+63.6 ± 3.5) | 328.5 ± 22.6 (+125.8 ± 4.6) | 402.9 ± 25.1 (+70.6 ± 3.8) | 687.6 ± 38.3 (+78.7 ± 5.7) |
| `plan_beam` | full map and true `R_bush`; plans the whole route (beam search, width 300), whole-bush harvesting, no reward noise in the plan | 166.5 ± 9.1 (+71.1 ± 2.6) | 251.3 ± 12.1 (+83.5 ± 3.3) | 354.5 ± 15.9 (+151.7 ± 4.4) | 438.3 ± 17.6 (+106.0 ± 3.8) | 748.4 ± 29.9 (+139.5 ± 4.9) |

Relative to `plan_beam`: greedy gets 91.5% / 92.0% / 92.7% / 91.9% / 91.9%
(P/S1/S2/S3/S4) and nearest gets 57% / 67% / 57% / 76% / 81%. **The value of
knowing the reward function shrinks in S3 and S4**: with more relevant features
and larger summed weights, even a blind nearest-bush forager reaches 76–81% of
the ceiling, so the incentive to learn the mapping is weakest in the sessions
that are hardest to learn. Worth watching in pilots (a lower-weight or
higher-contrast design, or steeper reward dependence, would restore it).

Notes for reading these numbers:
- **`plan_beam` is a near-optimal ceiling for expected reward, not the strict
  optimum.** The exact branch-and-bound planner (`plan_exact`, 11–28 s per
  world, 1.3–3.0M search nodes) proved optimality in 23 of 24 worlds tested
  (12 seeds each of the earlier 60 s S1 and S2 — the former S1 is now P; the other hit its 3M-node cap). The beam planner
  was within 0.05% (S1) and 0.13% (S2) of the exact planner's expected reward,
  found the exact optimum in 19 of those 24 worlds, and never beat it. Neither
  uses partial harvesting (leaving a bush early) or the realized fruit rewards,
  so a clairvoyant agent could still do slightly better.
- **Stops per session.** In the 60 s practice session the best route visits 6–7
  bushes (5 s to harvest each, ~3.4 s average walk between neighbours), so the
  choice is which few bushes to spend the session on, not a long tour; the
  longer sessions scale roughly with duration (~10 stops at 90 s, ~16 at 150 s).
- **Greedy is sensitive to its scoring rule.** Value-only greedy (best
  expected reward within a walking-time radius, ignoring harvest and travel
  time) beat `nearest` at a 5–10 s radius but fell below it at 20–30 s;
  rate scoring is insensitive to the radius from 10 s up (it is worse at 5 s).
- **These are full-information agents.** None learns the reward function, so
  they bound what a learner could earn but are not models of participants.
- **Engine assumptions** (see `docs/DECISIONS.md`): straight-line walking to
  the edge of harvest range, no regrowth, facing time and canopy collisions
  ignored, decisions at fruit boundaries, per-fruit rewards pre-drawn from the
  seed. Re-run the baselines after changing spacing, jitter, speed, session
  length, fruit count or reward weights; all of these move them.

The project is at the platform-building stage: hypotheses are unwritten, no
pilot has been run, and no analyses exist. When analyses exist, reference
them here (path to code/notebooks; abandoned analyses with a pointer to an
`archive/HISTORY_*.md`-style entry, as in evidence_integration).

Planned/next engineering work, from the last README: participant-ID screen,
sound, font polish.

---

## Open questions and known limitations

- **TODO(PI): rebalance so `nearest` stays clearly worse than `greedy`/`plan_beam` in every
  session.** In the baselines below the blind nearest-bush forager reaches a large share
  of the planner's score in S3 and S4 (76% / 81% at the original speed and harvest rate), so the
  payoff for learning the mapping is smallest in the sessions that are hardest to learn.
  Levers: reward weights/contrast (including making the optimum steeper), world attributes
  (spacing, bush density, attribute distributions), session timing, harvest rate and
  movement speed. Re-run the baselines after each change. Deferred: not yet decided.
- **S5 reward structure** (interacting pair + additive feature, provisional) and
  its code support are undecided; see "Planned session progression".
- **Participant identity:** sessions are keyed only by a generated
  `sessionId`; no participant ID is collected yet (planned).
- **Reward-noise stream:** `HarvestManager` draws per-fruit noise from the
  global `UnityEngine.Random`, which `TreeGenerator` seeds with `worldSeed`
  once at world generation. The same stream is also consumed by cosmetic UI
  jitter (`HarvestUI` floating-text spread), so the noise a given fruit
  receives depends on harvest order and timing — world layout is
  reproducible from `worldSeed`, realized reward noise is not a fixed
  per-tree property. Realized rewards are logged per fruit, so analyses are
  unaffected, but a replay or simulation can't reproduce a participant's
  exact draws. Whether noise should come from a dedicated seeded RNG is an
  open design question.
- **Moisture is spatially structured**, so moisture-based reward creates
  location-dependent reward gradients (foraging by region, not just by
  inspection) — possibly a feature, possibly a confound for S2/S3. Likewise
  shape and color are independent of position, moisture is not.
- **Weak-to-moderate prior on moisture** (ground color) — acknowledged in the
  attribute table; no mitigation.
- Terrain doesn't self-shadow (URP limitation at landscape scale); shadow
  bias artifacts at low sun angles are mitigated by `minSunElevation`.
- Player capsule/model may visually overlap wide canopies slightly.
- `FruitMaterialManager`'s cache persists across Play-mode sessions in the
  Editor (intentional).
- Custom shaders must be in Always Included Shaders or standalone builds
  break (this bit the project once; fixed in `51fa98b`).

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

**Related naturalistic paradigms — identified, not read**
- "A naturalistic reinforcement learning task uncovers historical neural
  representations" (bioRxiv, 2025), doi:10.1101/2025.07.17.665306
- Kalliste Decision Task (ecological assessment of decision-making under risk
  and ambiguity; PMC11161587)
