# Pilot summaries (PCX, PSP, PSC)

Each pilot is three sessions of the same foraging task (180 s each, fixed order S1, S2, S3, after the tutorial) in which one knob rises and the rest are held. Participants are not told what varies. The numbers below are from simulated agents (`scripts/agent_benchmark.py`, 20 worlds per session, ± standard error); no participant data exist yet.

Agents: **mvt** is the marginal-value-theorem forager at the optimal long-run rate (true values, no tuning on the world: a near-optimal reference); **learner** is a delta-rule learner that learns the map from what it sees; **nearest** takes the nearest bush with no learning; **best k** is the best fixed number of bushes per patch (chosen with hindsight). The point gain of each session is set so the learner earns about 1,125 points in every session of PCX and PSP (PSC fixes the gain on purpose, so its points fall with travel time).

---

## PCX: Pilot Complexity

**What is varied.** The point-value map over the two visible features (shape, colour) is a single Gaussian bump, moved from a simple corner peak (S1, additive) to an axis-aligned peak away from the corner (S2, multiplicative) to a rotated ridge (S3, non-separable). The knob is how far the value of one feature depends on the other: interaction 0.09, 0.18, 0.40; nonlinearity 0.14, 0.43, 0.92. Held fixed: inequality of bush values (Gini 0.55), travel time (5 s) and the learner's expected points.

**Where to see it.** `docs/pilots/PCX.png` (the three value maps; bushes as dots, contour at half the peak); `docs/pilots/PCX.txt` (numeric span-and-hold check); `docs/pilots/agents.md` (agent table).

| | S1 additive | S2 multiplicative | S3 non-separable |
|---|---:|---:|---:|
| Learner, points | 1117 ± 9 | 1132 ± 9 | 1122 ± 15 |
| mvt benchmark, points | 1346 ± 8 | 1470 ± 10 | 1681 ± 10 |
| Learner as a share of benchmark | 0.83 | 0.77 | 0.67 |
| Learner bushes per patch | 5.65 ± 0.11 | 6.23 ± 0.10 | 7.60 ± 0.04 |
| Benchmark bushes per patch | 2.4 | 2.4 | 2.9 |

**Key differences in agent behaviour**
- The learner falls further behind as the map gets harder. Its points are flat by design while the benchmark's rise, so its shortfall grows from 229 to 338 to 559 points.
- Its foraging changes with the map. A well-adapted forager leaves a patch after about 2.4 to 2.9 of 8 bushes. The learner stays longer as the map gets harder (5.7, 6.2, 7.6 bushes); in S3 it harvests nearly every bush, about as many as the nearest-bush agent (7.8), which suggests it can no longer tell good bushes from poor ones.
- Knowing the map is worth more as it gets harder: oracle points (known map) rise 1347, 1452, 1659.

**Caveats.** Mean bush value is not held across sessions (1.79, 1.93, 2.23; flagged in the check), so the nearest-bush agent's rise (863, 930, 1082) is not a complexity effect. The benchmark is a reference, not a model of human behaviour.

---

## PSP: Pilot Sparsity

**What is varied.** How concentrated the points are among the bushes. The value map is a single round Gaussian bump; the Gini of bush values rises 0.4, 0.5, 0.6, so fewer bushes pay well and the best ones pay more (share of bushes above half the peak: 0.32, 0.23, 0.16). Held fixed: travel time (5 s), interaction and mean bush value (within tolerance), and the learner's expected points.

**Where to see it.** `docs/pilots/PSP.png` (the three maps: the same round bump, narrower and taller); `docs/pilots/PSP.txt` (numeric check).

| | S1 Gini 0.4 | S2 Gini 0.5 | S3 Gini 0.6 |
|---|---:|---:|---:|
| mvt benchmark, points | 1343 ± 10 | 1454 ± 9 | 1641 ± 12 |
| Learner, points | 1116 ± 8 | 1129 ± 6 | 1138 ± 10 |
| Learner as a share of benchmark | 0.83 | 0.78 | 0.69 |
| Nearest-bush agent, points | 1034 ± 4 | 1000 ± 6 | 983 ± 7 |
| Benchmark bushes per patch | 3.0 | 2.5 | 2.1 |
| Learner bushes per patch | 7.6 | 7.3 | 7.0 |
| Best fixed k | 3.9 | 3.0 | 2.2 |

**Key differences in agent behaviour**
- Sparser worlds reward leaving patches earlier: the benchmark takes 3.0, 2.5, 2.1 bushes per patch and the best fixed k 3.9, 3.0, 2.2, while its points rise because the peak bushes pay more. The optimal leaving rule changes with the knob.
- The learner is far from that rule at every level (7.0 to 7.6 of 8 bushes per patch); its drift towards leaving earlier is much smaller than the benchmark's.
- The shortfall grows with sparsity (learner 83% to 69% of the benchmark): a participant who finds the good bushes and skips the rest gains more in sparser worlds.
- The nearest-bush agent loses points as the world gets sparser (1034, 1000, 983).

**Caveats.** The bump's position differs between sessions and its peak rises with Gini (5.6, 6.9, 9.0, capped at 9; about 0.2% of S3 fruits pay over 9). Mean bush value is held only within tolerance (2.19, 2.09, 2.03).

---

## PSC: Pilot Spacing

**What is varied.** Only the travel time between patches: 3, 6 and 9 s, on the same additive value map (Gini 0.55, same bush values). Patches are pushed farther apart, so the world holds fewer of them (76, 34, 18 tiles; 684, 306, 162 bushes). The gain is fixed, so points fall as travel time rises.

**Where to see it.** `docs/pilots/PSC_layout.png` (top-down layout: same patches, spaced farther apart, bush values coloured); `docs/pilots/PSC.png` (the value maps, identical); `docs/pilots/PSC.txt` (numeric check: only travel time changes; mean bush value 1.54, 1.54, 1.55).

| | S1 travel 3 s | S2 travel 6 s | S3 travel 9 s |
|---|---:|---:|---:|
| mvt benchmark, points | 1357 ± 9 | 1082 ± 8 | 906 ± 10 |
| Learner, points | 1127 ± 7 | 905 ± 7 | 791 ± 8 |
| Nearest-bush agent, points | 797 ± 5 | 730 ± 3 | 680 ± 7 |
| Benchmark bushes per patch | 2.0 | 2.6 | 3.1 |
| Learner bushes per patch | 4.9 | 6.0 | 6.4 |
| Best fixed k | 2.4 | 3.2 | 3.5 |

**Key differences in agent behaviour**
- Longer travel lowers every agent's points (benchmark 1357 to 906, learner 1127 to 791), so the score carries the manipulation directly.
- Longer travel rewards staying longer in each patch: the optimal bushes per patch rises 2.0, 2.6, 3.1 and the best fixed k 2.4 to 3.5. This is the opposite direction from PSP and the classic marginal-value-theorem prediction.
- The learner moves the same way (4.9, 6.0, 6.4 bushes per patch), though it overstays at every level; its gap to the benchmark stays about 17 to 18%.
- Long-travel worlds are less forgiving of a bad strategy: the nearest-bush agent loses about 15% from S1 to S3, the benchmark about 33%.

**Caveats.** Because the gain is fixed, travel time and points change together; participants earn less in S3 by design, which could affect motivation as well as strategy. The tables show a direction, not a threshold: the pilot has to show whether participants lengthen their patch visits with travel time, and by how much.
