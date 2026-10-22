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

- **Session:** fixed duration per session (design values P 60 s, S1 90 s, S2/S3 120 s, S4 150 s; **temporarily 15 s for
  testing**, see "Session configurations"), the
  second part of a day cycle: the session starts when the sun is `sunStartElevation` (30°) above the horizon on the morning
  side and ends at dusk, when it is `sunEndElevation` (10°) on the afternoon side (same calculation for both; the mountain
  skyline is about 3–22° from the valley, median 9°; the 30°/10° pair is a tuned-by-eye trial, since equal values did not look symmetric). The sun follows a real solar path (`sunLatitude` 40°,
  `sunDeclination` +12°: a start at 30° elevation, a peak of about 62°, rising toward the east-south-east and
  setting toward the west-north-west, moving faster near the horizon; `sunAzimuthOffset` rotates the path). Every session
  plays this same path, mapped onto its length, so a shorter session plays it faster; Interludes hold the sun still
  (at noon, from the south). Light and sky take hue from
  physics (the sun's colour is its transmittance through the atmosphere, warm white at noon and orange near the horizon; the procedural
  sky reddens from the sun's direction with a constant neutral tint) and brightness from curves of the sun's elevation (light intensity,
  ambient-probe multiplier, sky exposure), plus an exposure ramp (post-exposure, in stops) that darkens everything on screen toward
  dusk. Important:
  the terrain and fruit shaders ignore the sun's colour and intensity (terrain lighting is `0.15 + 0.85 * shadow * N.L`, with white light
  and a black ambient term; fruit has an ambient floor), so the hue and intensity curves act on the canopy, the sky and the ambient
  probe, and the terrain darkens through the sun's direction plus the exposure ramp. Movement costs time (fixed player speed); harvesting costs
  `fruitHarvestDuration` seconds per fruit (0.2 s in sessions, so 10 fruits = 2 s per bush; 0.05 s in Interludes,
  0.5 s per bush); player speed 7.5. The progress ring is computed from this value, so it adapts.
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
  ends the bout, and a fresh press starts the next one. +X popups appear in a central row of slots (a fixed
  cycle, so concurrent popups never overlap), and the score updates per fruit. Optional `harvestLookResistance`
  (default 0, off) slows mouse yaw to zero as you turn away from the bush.
- **World:** ~685–695 trees (P, S1–S4; the count follows from the valley area; `worldHalfExtent` 350, valley
  about 580 units across) placed on a
  jittered hexagonal lattice (`treeSpacing` 23, `placementJitter` 0.5; nearest-neighbour
  distance ≈ 18.6, CV ≈ 0.13, no pair closer than 11.5, so ≈ 2.5 s walk to the
  nearest bush at speed 7.5; `startClearingRadius` 8 keeps only the spawn point itself clear, so the nearest bush at the start is
  17–23 away), on Perlin-noise terrain, in a valley enclosed by an
  unclimbable rocky/snowy mountain band built into the terrain (no trees on it).
  A per-session `worldSeed` fixes the terrain, the mountain skyline, the tree
  layout/attributes, and every per-fruit reward (all generated by `scripts/world.py`
  and loaded by Unity from `StreamingAssets/Worlds`).
- **A participant plays a sequence of sessions** (`P`, `S1`–`S4`, each followed by its Interlude), each with
  a different world seed and reward function. `P` is an unanalyzed practice
  session (`SessionConfig.isPractice`): its end screen says "Practice Complete" and it
  is not counted in "Session x/4". Between sessions the player sees a score screen and
  continues with Enter (Space is reserved for harvesting). After every session, including the practice
  one, comes its Interlude, a short forced-choice block (see "Interlude" below).
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

Each harvested fruit gives: a "+X" popup in a fixed central band of the screen (pale gold with a dark outline, pops in
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

Popups never overlap: `HarvestUI` has `popupSlotCount` (5) side-by-side slots, `popupSlotSpacing` (120 px) apart, fanned out
around `popupOffset` (order: centre, right, left, farther right, farther left). Each new popup takes the next free slot in
that fixed cycle; a slot is busy until its popup fades, so it holds for any per-fruit time or popup duration. Slot choice
is deterministic and independent of the reward and the bush, so position is not an information channel.

### Interlude (between-session forced choice)

A short block after every session that reads out what the participant learned, separated from how well they
explored and planned. Flow: P → Interlude (practice) → S1 → Interlude 1 → … → S4 → Interlude 4 → final screen.

- **It looks like the session.** An Interlude runs in the probed session's own world: the same terrain (plateaus,
  ground colour, mountains), sun and fog, loaded from that session's world file. Only two bushes are present at a
  time, so there are only two choices; the participant is teleported to a different part of the valley for each trial.
- **Trial:** the two bushes are on opposite sides of the starting heading, equal in the terms the harvest rules use
  (see Geometry): the same distance from the spawn point to each canopy's edge, and the same bearing of each canopy's
  inner edge from the heading. The participant turns toward the bush they think pays more, walks to it and harvests it: same
  fruit-pop animation as the main task but a faster per-fruit speed (0.05 s, versus 0.2 s in sessions), whole bush
  (10 fruits, `interludeHarvestFruits`), so the harvest takes about 0.5 s on top of a walk of about 2 s. **Commitment:** the bush whose harvest the participant starts is the choice from that
  moment, and the other bush shrinks away (`interludeSwitchPolicy`, default Hide; Exhaust gives it the spent look, Lock leaves it untouched but unharvestable,
  Allow keeps the old behavior where the bush whose last fruit is taken first is the choice), so there is no switching. The participant still holds Space until the
  chosen bush is finished and the trial ends then; releasing mid-bush just pauses on that bush. No instruction sentence announces the rule.
  Controls are the main task's. No outcome is shown: no +X popups and no score (the score slot shows trial progress).
  The exhaustion chime still plays. Each fruit makes a different, neutral pick sound (a very short, soft, low falling
  "bloop") instead of the main task's pick blip, whose pitch rises with the reward: reusing that blip, even at a fixed
  pitch, would pair the harvest with the low-versus-high-reward cue. The reward is still logged. The practice session's
  "Harvesting this bush earned X points" message never appears in an Interlude.
- **Timer and progress:** a 10 s countdown (`interludeTrialSeconds`, was 7 s) in the upper left (the session-timer slot); when it runs out the trial ends
  with no choice. Progress "X/n" sits in the upper right (the score slot). Trials are separated by a short fade to black.
  Presentation order is shuffled per participant; each trial's placement, and so which bush is on which side, is fixed
  in the file, with the correct side balanced across trials.
- **View at each trial start:** the player is placed at the stage spawn facing the pair (yaw from the trial file) with the pitch
  set at run time so the middle of the two bushes' visible canopies (a quarter of each canopy's height above its base, averaged)
  is on the view's horizontal centre line, instead of looking level at the horizon (which showed mostly sky). Pitch is clamped to
  `lookPitchLimit`; the teleport event in `events.csv` records it.
- **Length:** 3 trials in the practice Interlude, 5 in each of the four others (was 10).
- **Stimulus types** (generated by `scripts/interlude.py` from the probed session's reward function; the same set
  for every participant):

  | Type | What it is | S1–S2 (one relevant feature) | S3–S4 (several) |
  |---|---|---|---|
  | contrast | two bushes differing in one feature, others equal | 3: every relevant feature (cycled) plus one ignored-feature check | 3: one per feature (S3 includes the irrelevant shape) |
  | graded | two bushes with a chosen true-reward difference (0.15–1.2 × the spread of R across typical bushes, geometric steps) | 6 | 4 |
  | extrapolation | extreme-valued bushes: with several relevant features a genuine trade-off (each bush wins a feature by ≥ 20% of its weight) with a moderate reward difference; with one, opposed tails | 1 | 3 |

  The table's counts are for 10 trials. At the current 5 trials the mix is S1–S2: 2 contrasts (the relevant feature plus the
  ignored-feature check), 2 graded, 1 extrapolation; S3–S4: 2 contrasts, 1 graded, 2 extrapolation. So S3 (relevant color +
  moisture) loses its ignored-shape check, and S4 (all three relevant) has no moisture contrast (shape and color only).
  Moisture still enters through the extrapolation trade-offs.

  The practice Interlude has 2 easy contrasts on the relevant feature and 1 large graded pair. Which exact stimuli to
  show per session is still to be refined.
- **Random mode** (`interludeMode: Random`; the field's default is Designed, but **all five Interlude assets are currently set to Random for
  testing with people**, so the committed `.interlude.json` files are random trials and the Designed description above is the alternative:
  set `interludeMode` back to Designed and regenerate). The practice Interlude is then three random pairs, not easy contrasts. Instead of the three designed stimulus types, every
  trial is a pair of bushes with independent uniform random shape and colour (moisture is still the terrain's at the final positions, so
  relevant-moisture sessions still see moisture differences; roughly a quarter to a half of random pairs differ by more than 0.2). Pairs whose
  true rewards are within the tie tolerance are redrawn, so every trial has a definite correct side, half of them on the left; the geometry
  rules (equal edge distance and bearing, clear view, no hump) are unchanged. All trials have type `random` in `interlude.csv`; scoring
  is accuracy only (small gaps are hard on purpose: they probe the resolution of the learned value function). The trial count is
  `interludeTrialCount`: the human assets keep their small counts, and the simulator can use another (`interlude_trial_count=50` as a
  session override, recorded in the environment) because 50 trials is a measurement of a model, not a block a person sits through.
  Generation takes about 1 s per world (a 40 000-placement pool; designed mode searches 500 000). Both modes are generated by
  the same function, so what an agent is scored on is what a human could be shown.
- **Moisture comes from the terrain.** There is no Interlude-specific terrain logic: a bush's moisture and elevation are
  those of the session's terrain where it stands, as in the main task. The generator therefore searches half a million
  (spawn point, heading) placements for ones where the two bush positions have the moisture relation a trial needs, then
  chooses shape and colour: *same* (|Δ| ≤ 0.02, used for contrasts on shape and colour), *one plateau level apart*
  (0.20–0.34), or *two or more levels apart* (≥ 0.45, used for the moisture contrast). Placements also must not let the
  terrain hide a bush: the eye line from the spawn point clears the ground to a point 1 unit above each bush's base, and the ground
  does not rise and then fall (by more than 0.5 units) on the way to either bush; the spawn slope is gentle, and trial spawn
  points are at least 80 units apart (relaxed if the pool is thin). In the generated files the largest rise-then-fall is 0.4 units.
  With bushes 28 apart, two-level pairs are about 0.5% of placements and the full 0.1-versus-0.9 range is essentially
  unavailable (terrace levels change one step at a time), so the largest moisture contrast is about 0.5 (about 10 units
  of height). In S1/S2/P (moisture irrelevant) moisture is whatever the placement gives, matched only in contrasts.
- **Geometry:** the harvest rules refer to the canopy edge (the range is the distance to the edge, and the cone uses the
  bearing minus the canopy's angular radius), and canopy radius depends on shape (0.5–3 units), so placing the bush
  *centres* symmetrically made the bushes unequal: the wide one was closer by its edge and looked closer, and the tall narrow
  one looked further (size cue). Each bush is now placed from its own radius so that **its edge is `interludeBushDistance`
  (22.6) from the spawn point and its inner edge is `interludeBushBearing` (31.5°) off the heading, on opposite sides**:
  the heading bisects the pair (it points at the midpoint between the two inner edges, not exactly between the centres, which
  differ when the radii differ), and the turn and walk to start harvesting either bush are the same by the game's own rules.
  The generator checks this exactly in every trial. What cannot be equalized: apparent size (a narrow canopy looks smaller, part
  of the shape channel), the 3D distance when the bushes stand at different elevations (up to about 4 units), and, because
  each bush's final position shifts a little with its radius, the terrain moisture under it (the design re-checks the
  moisture relation at the final positions). The lateral clearance must stay ≥ the harvest range (7) + the canopy radius, otherwise a bush
  could be harvested by walking straight ahead and the game's selection (smallest bearing) would default to the widest canopy,
  biasing the choice by shape. The wide separation (bushes about 28 apart, a walk of about 2 s) is what makes two-level
  moisture differences available.
- **Scoring:** a choice is correct if it is the bush with the higher true reward, or if the true rewards are
  within 0.05 (either answer). Each correct choice adds a hidden bonus (`interludeBonusPerCorrect`, 5 points); trials with no
  commitment before the time limit, and practice-Interlude trials, earn none (a committed choice still counts if the limit runs out before the bush is finished). After each (non-practice) Interlude the end panel shows that Interlude's own
  "x / n correct" and "Bonus: +y" (never which trials, nor anything about the reward function; the practice Interlude shows no
  score); the final screen adds the totals ("Total Score" = sessions + Interlude bonus, with n correct). Practice sessions are
  excluded from the total. Instruction text: `instructions_interlude_P.txt` (practice) and `instructions_interlude.txt` (1-4), terse, mentioning that good choices earn a bonus.
- **Data:** `interlude.csv` in the Interlude's own folder (it also writes trajectory.csv, events.csv, harvests.csv and
  manifest.json like any session, with `trial_start`/`teleport`/`trial_end`/`trial_go` events (`trial_go` ends the harvest block that starts at `trial_end`: no bout can start in between), with `sessionName` e.g. `S1_Interlude` and `isInterlude`; `world.file` in the manifest is the
  session world file whose terrain was used): one row per trial with presented order, the design id, type, varied feature,
  both bushes' attributes and true reward, the correct side, choice (left/right/none), correct, timed_out, response_time
  (to the last fruit), first_harvest_time and side (first bush started), fruits taken from each bush, the bonus, and `locked_at` (appended: the trial
  clock when the commitment happened; empty under Allow or with no commitment). The matching `choice_lock` event in `events.csv` names the committed and the locked bush and the policy.
- **Generating the files:** `./venv/bin/python scripts/interlude.py P_Interlude S1_Interlude S2_Interlude S3_Interlude S4_Interlude`
  writes one small `<name>_seed<N>.interlude.json` each (3–9 KB: the bush table and trial list; no terrain). Each Interlude is a
  `SessionConfig` copy of the session it probes with `isInterlude` on, `interludeFor`, `interludeTrialCount`, a `worldSeed` equal to
  that session's, and the bush geometry; the script checks that its reward function and terrain parameters match the session's.
  Re-run it after changing the session's terrain, reward function or the Interlude geometry. The instructions are
  `instructions_interlude_P.txt` and `instructions_interlude.txt` (first drafts; the 1–4 text no longer mentions the time limit, the countdown shows it; a
  `{trial_seconds}` placeholder, filled from `interludeTrialSeconds`, is still supported).
- **Not built:** the prediction (reward-estimate) mode, analysis code, and a simulated learner. Design rationale and
  rejected alternatives: DECISIONS ("Interlude").

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
  `(1 − moisture) × terrainMaxElevation`). The field's character depends on
  the session (see "Terrain by session"): a smooth continuum with ~50-unit
  hills and almost no relief in P/S1/S2, where moisture earns nothing; terraced
  plateaus and valleys in S3/S4, where it does.
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

**TEMPORARY (testing): `sessionDuration` is 15 s on P and S1–S4. The design values are P 60, S1 90, S2 120, S3 120, S4 150
(as in the table below); restore them before piloting.** The Interlude assets' `sessionDuration` is only a cap (they end when the
trials are done; 150 s, 60 s for the practice one).

All five sessions: `rewardStd` 0.3, 10 fruit/tree, speed 7.5, `fruitHarvestDuration` 0.2 (0.05 in the Interludes), first-person camera, `worldHalfExtent` 350,
`terrainMeshResolution` 449, ~685–695 trees
(seed-dependent: P 686, S1 694, S2 688, S3 685, S4 695). Weights apply to (shape, color, moisture).

| Session | Seed | Duration | Shape | Color | Moisture | Character |
|---|---|---|---|---|---|---|
| P (practice) | 100 | 60 s | Linear, w=3 | w=0 | w=0 | one feature, linear (mechanics) |
| S1 | 1 | 90 s | w=0 | Linear, w=3 | w=0 | one relevant feature of three |
| S2 | 2 | 120 s | GaussianPeak, w=3, peak 0.65, width 0.2 | w=0 | w=0 | one feature, non-monotonic |
| S3 | 3 | 120 s | w=0 | Linear, w=1.5 | Linear, w=3 | two features, linear; moisture (terrain) dominant |
| S4 | 4 | 150 s | InvertedLinear, w=2 | Linear, w=3 | Linear, w=1.5 | all three, additive, monotonic, one inverted |

(Read from `Assets/ScriptableObjects/SessionConfig/*.asset`; the assets are the source of
truth and may have moved on — re-check before citing.) The relevant feature rotates
across sessions so a "it's always shape" rule can't carry over. The S2 peak is off-centre
(0.65) so it is not just "avoid the extremes". Earlier designs explored five configs, then
a 60 s S1–S3 (one linear; three linear; mixed), replaced by this progression; see DECISIONS.

### Terrain by session

Terrain only matters for reward in S3 (moisture weight 3, the dominant feature) and S4 (weight 1.5), so it is deliberately
different there. All values are `SessionConfig` fields; the field is built in `scripts/world.py`.

| Sessions | `terrainMaxElevation` | Moisture field |
|---|---|---|
| P, S1, S2 (moisture irrelevant) | 12 (snow line kept by `snowLineFraction` 0.564) | continuous, wavelength ~50 units (`terrainNoiseFrequency` 2), range up to ≈ 12 units of relief (bushes span about 0–12) |
| S3, S4 (moisture rewarded) | 20 | **terraced**: `moistureTerraceLevels` 4, `moistureTerraceSharpness` 0.3, `moistureTerraceResidual` 0.1, `terrainNoiseFrequency` 0.6 (wavelength ~165 units) |

Terracing: the continuous field is rank-normalised over the valley (so each level covers about the
same area), snapped to 4 evenly spaced moisture levels with ramps between plateaus, and given a small
undulation (±0.1) on plateau tops; levels are inset by that amplitude so the full 0–1 range is used
without clipping. Elevation and ground colour follow moisture, so there are 4 ground colours and
4 height tiers. On the seeds used (S3, S4): ~165–180 bushes per level, ~6–7 large patches holding
~80% of bushes (median ~65 bushes per patch), p99 slope ≈ 31° (the old terrain: 27°), bush moisture
std ≈ 0.30 (old continuum: 0.16, so moisture's reward spread is ≈ 0.44 at weight 1.5 (S4) and ≈ 0.89 at weight 3 (S3), vs 0.24 at 1.5 on the old terrain; in S3 colour's spread is 0.43, so moisture contributes about twice as much).
In the S3 world the start region has few of the wettest (level 3) bushes nearby (16 within 160
units against 72 of level 0), so reaching them takes travel. The moisture–height coupling is
likely to be revisited (TODO below). Design decision and alternatives: DECISIONS ("Terraced moisture").

### Session progression (P–S4 implemented; S5 is a TODO)

Goal: each session is long enough for a participant to sample many bushes and
learn the reward mapping, but not so long that most of it is spent exploiting a
fully learned rule; and complexity increases across sessions so learning takes
progressively more stops. Rationale and rejected alternatives: DECISIONS
("Session progression").

**Time budget logic.** The first sizing assumed player speed 5 and 0.5 s per fruit:
~9 s per full-harvest stop (5 s harvest + ~3.7 s walk), so 60 s held only ~7 stops, too few to
learn and then exploit anything beyond one feature. Speed was then raised to 7.5 and harvesting
doubled to 0.25 s per fruit (later 0.2 s in sessions and 0.05 s in Interludes), so a stop was ~5 s (2.5 s harvest + ~2.5 s walk): roughly 1.8×
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

The logs are designed so that a participant's session can be **replayed exactly** (path, camera angle, every
harvest) in the world they played, and fed to mathematical or neural agents as trajectories. Per session,
`ForagingData/<sessionId>/` holds:

| File | Content |
|---|---|
| `trajectory.csv` | One row per rendered frame: `t` (unpaused session seconds), `x, z`, `yaw`, `pitch` (degrees), `keys` (bitfield: 1 W, 2 S, 4 Space held). Height is the terrain's at (x, z); eye height is in the config. The pose is what `HarvestManager` reads that frame (interpolated player position, camera yaw). |
| `events.csv` | `t, real, type, tree_id, k, reward, running_total, note`. `real` is unscaled seconds (so pauses, such as reading the instructions, have a duration). Types: `session_start` (start pose in `note`), `pause`/`resume`, `focus_lost`/`focus_gained`, `harvest_press`, `harvest_pause`/`harvest_resume` (target left/re-entered the range-and-cone mid-bout, which stops/restarts the fruit timer), `fruit` (one per fruit: bush, `k` = its index among the fruits taken from that bush, reward, running total), `harvest_release` (`note`: fruits, remaining, exhausted), `teleport` (Interlude trial change; new pose in `note`), `trial_start`/`trial_end`, `trial_go` (the between-trial harvest block lifts; presses from `trial_end` up to this frame are discarded), `choice_lock` (Interlude commitment: `note` has `committed`, `locked` and `policy`), `session_end`. |
| `harvests.csv` | One row per harvest bout (summary of the events plus the bush's attributes and true reward); times are `t_start`, `t_end` on the same clock. |
| `manifest.json` | The full `SessionConfig` (`config`, every serialized field), `world` (file, seed, sha256; for an Interlude also `interludeFile` and `interludeSha256`, the name and hash of its bush-table file), `build` (git commit and a `dirty` flag for logic-relevant files), `display`, `frames` (count, mean/max frame ms), `finalScore`, `completed`, and a `participantId` placeholder (null until participant IDs are collected). |
| `interlude.csv` | Interlude sessions only (columns in the "Interlude" section). |

**Why this set is sufficient.** Harvest outcomes are a deterministic function of (trajectory, world): the fruit timer,
range/bearing cone and per-bush carry-over use only position, yaw and `t`, and each fruit's reward is the pre-drawn
`fruit_reward[bush][k]` in the world file. The world is pinned by sha256 and archived by the logger in
`ForagingData/_worlds/`. `scripts/replay.py` re-derives every `fruit` event from the trajectory and checks it against
the log (`./venv/bin/python scripts/replay.py <folder or id>`); it also resamples a session to a uniform time grid
(`steps`) for agents. Logging state per frame rather than inputs avoids having to reproduce Unity's physics. **What the participant could see**
is derived, not logged: `scripts/visibility.py` (`visible_bushes(log, dt=0.1)`, or the CLI) rebuilds it per step from the trajectory,
the world's terrain and the camera (eye = terrain + `eyeHeight`, FOV and clip planes from the manifest, aspect from the logged display
size). A bush counts as visible when part of its camera-facing upper canopy (a half-buried ellipsoid; height from the shape attribute)
is inside the view frustum and the line of sight clears the terrain. Per visible bush it returns `visible_fraction`, egocentric
`azimuth` (+ right) and `elevation` (+ up), `distance` and angular `width`/`height` (threshold on those for resolvability; there is no
built-in distance cutoff beyond the far clip). Not modelled: bushes hiding other bushes, fruit visibility, fog. In an Interlude only
the trial's pair exists.
World files are written by `scripts/world.py`, so regenerating them gives a new hash; old logs keep their archived copy.
Format notes live in `CLAUDE.md` ("Data logging") and `docs/DECISIONS.md`.

State of the data: everything currently in `ForagingData/` (~395 session
folders) is **debugging output**. No dev or participant data has been
collected, and collection is a long way off. There is no participant-ID entry
yet (planned). Once real collection begins, this section should say which
sessions are real and how they map to participants.

---

## Findings and current thread

**No analyses of human data are recorded in this repo.** The only results are
the simulated agent baselines below (code in `scripts/`).

### Recorded simulation runs (results database)

Runs are recorded in `results/results.sqlite` (gitignored; conventions in CLAUDE.md, "Results database") and queried with
`scripts/analysis.py`. They supersede the stale table below as it is re-run.

**`s1-90s-learning`** (first 100-seed run on a clean tree: commit `f3f5606`, engine `282a3fe3d692`; S1 at its design 90 s, motor costs on,
default view cone, seeds 0-99; random Interlude with 50 trials and 20 samples per trial; Interlude scored on copies of each agent at
0, 10, 20, 30, 45, 60, 75 and 90 s). Total reward, mean ± se, paired difference to `nearest` ± se, and Interlude accuracy at the end of the session:

| Agent | Total | vs nearest | Interlude accuracy at 90 s |
|---|---|---|---|
| `nearest` | 289.6 ± 3.7 | , | 0.50 |
| `delta_rate_10` (delta-rule critic, additive RBF features, neutral prior, full memory) | 335.2 ± 3.4 | +45.6 ± 4.1 | 0.91 |
| `greedy_rate_10` (oracle) | 399.8 ± 2.3 | +110.2 ± 3.9 | 1.00 |

Learning curve (Interlude accuracy of the learner against training time; the 95% interval is about ±0.01 to ±0.03): 0.50 at 0 s, 0.62 at 10 s,
0.76 at 20 s, 0.82 at 30 s, 0.86 at 45 s, 0.89 at 60 s, 0.90 at 75 s, 0.91 at 90 s; `nearest` stays at chance and the oracle at 1.00 throughout.
The learner closes 0.39 ± 0.04 of the nearest-to-oracle gap per seed in total reward. Its reward lead over `nearest` (cumulative-reward advantage)
is about zero until roughly 28 s and then grows at close to the oracle's slope, so the Interlude shows it knowing the value function (0.76 at 20 s)
before the reward shows it. Figures:
`results/s1-90s-learning_{learning,cumulative,advantage}.png` (gitignored). With one relevant feature (S1) a good learner
should reach the oracle's accuracy, so 0.91 leaves room for stronger critics. The earlier 10-seed and dirty-tree trials (`first-s1-90s`,
`rate-trial`, `learning-trial`) are superseded by this run.

### Simulated agent baselines (preliminary, STALE)

**These numbers were computed before the speed, harvest-rate and map-size changes** (speed 5,
0.5 s per fruit, `worldHalfExtent` 200 with ~140 trees; session durations as in the table below). Player speed is
now 7.5, fruit harvest 0.25 s (since 0.2 s; 0.05 s in Interludes), and the map ~5× larger in tree count, so the table, the
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

Next steps and open TODOs (details in the sections they live in): restore the design session durations
(temporarily 15 s) and retune them for the faster pace; rebalance rewards/world/timing so the blind `nearest` agent stays
clearly worse than `greedy`/`plan_beam` in S3–S4; re-run the agent baselines (stale); revisit the moisture-to-height
coupling; decide and build S5 (interacting pair plus additive feature); for the Interlude, the prediction (reward-estimate)
mode, analysis code, a simulated-learner agent to calibrate stops-to-learn and Interlude length, and a freshness check on
its generated files; a participant-ID screen; and writing the hypotheses down.

---

## Agent ladder for calibrating the task (framework built; learning agents not yet)

Goal: find a task design where, in every session, learning pays and strategy pays, using simulated agents as a screen before (and
alongside) a human pilot. **Built (v1):** the component framework in `scripts/agents.py` and the engine in `scripts/sim.py` (heading, view cone,
Harvest / Explore / Look / Stop actions, Interlude evaluation with a frozen critic); `nearest`, `greedy_*` and `plan_*` are rebuilt on it
with the oracle critic and full-knowledge memory and reproduce their pre-refactor results exactly. **First learner built:** `DeltaRuleCritic`
(`delta_value_10`, `delta_rate_10` in the registry; see DECISIONS, "The first learner"). **Not built:** the kernel-regression (B) and Gaussian-process (E) critics, SSP features, exploring actors, limited memories, and the agent list. Agreed design:

- **Ladder:** `nearest` (floor, learns nothing) < simple learner < ideal learner < full-information `greedy`/`plan_beam`. The full-information
  agents are not reachable by any learner; they are a benchmark, and the gap to them is the unavoidable cost of learning, not a tuning target.
  Sweet spot: a wide floor-to-learner gap (learning pays) and a clear gap between weak and strong policies on the *same* learner (strategy pays).
  Planning may start to matter if bushes are spaced farther apart or clustered; check that when the map changes.
- **Agent = actor x critic x memory**, each a separate component in `agents.py`, mixed and matched. **Actor** = the policy: choice rule
  (hard-max or softmax, returned as probabilities so likelihoods can later be fit to human choices), utility (value or rate, optional exploration
  bonus), leave/peek rule, and exploration (walk or look to see more bushes, or pick a bush to peek at). **Critic** = the value representation and
  its learning rule, from per-fruit rewards (full knowledge of the true reward function is the `oracle` critic). **Memory** = constraints on what
  the other two may use: the bushes seen so far (map: positions, attributes, spent or not) for the actor, and the (attributes, reward)
  experiences for the critic; full memory accumulates everything seen, full knowledge is preloaded with the whole map. `nearest`, `greedy` and `plan`
  are actors with the oracle critic and full-knowledge memory. The **percept** is not a component: it belongs to the environment (`scripts/perception.py`),
  the sensor the engine applies: a view cone with an angle and distance and a heading, exact attributes, no terrain occlusion at first. By default it is
  as wide as the session camera (107.5 deg horizontal for 75 deg vertical at 16:9) with no distance limit; a run can replace it (`run_n(..., percept=)`,
  `sim.py --percept ANGLE,DISTANCE`) and an agent may carry its own override. Realistic constraints (terrain occlusion, resolvability by angular
  size, attribute noise) become new percept classes, calibrated against participants' logged visible sets. Walking, exploring and looking are actions of the
  actor, with time costs from `scripts/costs.py`: turning the view (`0.17 s + angle / 480 deg/s`, before a walk to face the way, before a harvest to bring the bush into the harvest cone; under 5 degrees it is free), pressing W to walk (0.2 s) and Space to harvest (0.3 s). The values are provisional, fitted to the developer's debug sessions (91 turns, 58 Space presses; the W press is a guess) and to be recalibrated from participants' logs. Every action costs time and a no-op (`Look(0)`, `Explore` of 0) is refused. These costs change every simulated total: the agent baselines below were computed without them and are stale.
- **Interludes:** after a session the critic is frozen and carried over (no outcomes are shown in an Interlude, so humans do not learn there either), the
  agent starts a fresh memory for the Interlude's own bushes, and both bushes of each trial are shown to it as observed, whatever its sensor (the trials are
  built so both are in view; the Interlude tests what was learned, not perception). The actor's choice rule then picks between them, repeated enough times to
  estimate accuracy; scored by a separate function (correct choices
  overall and by trial type, and the hidden bonus). The Interlude an agent faces is generated by `scripts/interlude.py` for the same world seed
  (`generate_interlude(..., seed=)`), with the same search and trials the game uses, so it is what a human sees on that world; if more or different
  trials are needed to separate agents, the change belongs in the human Interludes as well, not in a simulation-only variant.
- **Robustness:** the ordering of agents must hold across a variety of agents (learner and policy parameter sweeps), worlds and reward functions,
  not for one tuned learner.
- **TODO(PI): design a good agent/human performance metric** (candidate: (score - nearest) / (oracle - nearest) per session, plus choice-quality
  measures such as the rank correlation of chosen bushes with true value and reward rate over time) before tuning anything against it.
- The pilot will move these numbers; the simulation screens designs, it does not replace calibration on people.

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
- **Reward-noise stream (resolved, kept for context):** per-fruit rewards are pre-drawn in the world file
  (the k-th fruit taken from a bush pays `fruit_reward[bush][k]`), so the noise a fruit pays is a fixed property of
  the world and a participant's draws can be reproduced from the file. The remaining uses of the global
  `UnityEngine.Random` are cosmetic (the fruit-colour bursts in `Tree.cs`) and a fallback in `HarvestManager` for a
  bush with no stored rewards; ambient audio uses its own `System.Random` so it never touches that stream.
- **Interlude files can go stale (now caught by a test).** Unity warns when a *session's* world file no longer matches its
  `SessionConfig`, but not for an Interlude's `*.interlude.json`. `scripts/test_interlude.py::test_committed_interlude_file_is_fresh`
  regenerates each Interlude from the current assets and fails when the committed file differs (re-run `scripts/interlude.py`);
  `run_tests.py` runs it whenever a session or Interlude asset or an `.interlude.json` changes. Unity itself still gives no warning, and
  the session `.world` files have no such test (Unity's startup check covers them).
- **Interlude parameters are untuned:** trial counts (3 practice, 5 otherwise), the 5-point bonus, the 10 s limit (with a
  ~2 s walk and 0.5 s harvest), the bush distance/bearing, and the stimulus mix. The Interlude uses the session's own
  terrain, so participants may recognise regions (a spatial-memory confound); the harvested bushes are gone and the
  pairs straddle elevation boundaries, which should limit it. The instruction texts are first drafts.
- **TODO(PI): revisit how moisture maps to height** (and ground colour) after seeing the
  terraced terrain in play, to get good visual and reward variance: the current linear
  `(1 − moisture) × elevation` coupling, the 4 levels, the ramp and residual settings, and
  moisture's now larger reward spread (std 0.16 → 0.30) may all need adjusting.
- **Moisture is spatially structured**, so moisture-based reward creates
  location-dependent reward gradients (foraging by region, not just by
  inspection) — possibly a feature, possibly a confound for S3/S4. In the terraced sessions
  this is much stronger: neighbouring bushes share a moisture level, so moisture is largely a
  regional choice (find a good plateau and stay), raising the exploit share and lowering
  planning demand, and it is strongly confounded with position. Likewise
  shape and color are independent of position, moisture is not.
- **Weak-to-moderate prior on moisture** (ground color) — acknowledged in the
  attribute table; no mitigation.
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
