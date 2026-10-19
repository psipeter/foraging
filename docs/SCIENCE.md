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

- **Session:** fixed duration (S1–S3: 60 s), the second part of a day cycle:
  the session starts `dayStartFraction` (S1–S3: 0.3) of the way from sunrise to
  sunset and ends at sunset. Movement costs time (fixed player speed); harvesting costs
  `fruitHarvestDuration` seconds per fruit (S1–S3: 0.5 s; 10 fruits = 5 s per bush).
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
  in hand is kept on the bush. An exhausted bush shrinks away and disappears (it no longer
  blocks movement, and is dropped from `visible_tree_ids`).
  Looks (`highlightStyle`): *RimLight* — a soft glow on the bush's edge that grows
  as you approach, plus a thin crisp edge line on the selected bush, in a slightly different rim color once
  selected; or
  *EmissionWash* — whole-canopy glow, pulsing when selected. Holding Space collects one fruit every `fruitHarvestDuration` (the fruit
  nearest the camera first); walking is locked while Space is held, looking stays free.
  Looking more than 35° away pauses the harvest (hint: look back); releasing Space
  ends the bout, and a fresh press starts the next one. +X popups appear at a fixed
  screen slot, and the score updates per fruit. Optional `harvestLookResistance`
  (default 0, off) slows mouse yaw to zero as you turn away from the bush.
- **World:** 147 trees (S1–S3) placed by seeded random placement with a
  minimum spacing, on Perlin-noise terrain, in a valley enclosed by an
  unclimbable rocky/snowy mountain band built into the terrain (no trees on it).
  A per-session `worldSeed` fixes the terrain, the mountain skyline, and the tree
  layout/attributes.
- **A participant plays a sequence of sessions** (`S1`, `S2`, `S3`), each with
  a different world seed and reward function. Between sessions the player
  sees a score screen and continues with Space.
- **Camera (S1–S3):** first person — mouse looks (yaw + pitch), W/S walk
  forward/back along the view direction, no strafing. Eye height, vertical
  field of view, and mouse sensitivity are `SessionConfig` fields; the
  metadata JSON records the camera's FOV, pose, and clip planes. See DECISIONS.

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

### Session configurations (current)

All three: 60 s, 147 trees, 10 fruit/tree, `rewardStd` 0.3, speed 5,
first-person camera. Weights apply to (shape, color, moisture).

| Session | Seed | Shape | Color | Moisture | Character |
|---|---|---|---|---|---|
| S1 | 1 | Linear, w=3 | w=0 | w=0 | one feature, linear |
| S2 | 2 | Linear, w=1 | Linear, w=3 | Linear, w=2 | three features, all linear |
| S3 | 3 | Linear, w=1 | GaussianPeak, w=3, peak 0.5, width 0.2 | Linear, w=1 | three features, mixed linear/nonlinear |

(Read from `Assets/ScriptableObjects/SessionConfig/S1–S3.asset`; the assets
are the source of truth and may have moved on — re-check before citing.)

Earlier designs explored five configs (single-feature linear, single-feature
Gaussian, three-linear, mixed, all-nonlinear), later replaced by S1–S3; see
DECISIONS.

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

**No analyses or results are recorded in this repo.** There is no analysis
code and no results section yet.

The project is at the platform-building stage: hypotheses are unwritten, no
pilot has been run, and no analyses exist. When analyses exist, reference
them here (path to code/notebooks; abandoned analyses with a pointer to an
`archive/HISTORY_*.md`-style entry, as in evidence_integration).

Planned/next engineering work, from the last README: participant-ID screen,
sound, font polish.

---

## Open questions and known limitations

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
