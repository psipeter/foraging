# Pilot summaries (PCX, PSP, PSC)

Each pilot is three sessions of the same foraging task (180 s each, fixed order S1, S2, S3, after the tutorial) in which one knob rises and the rest are held. Participants are not told what varies. The numbers below are from simulated agents (`scripts/agent_benchmark.py`, 20 worlds per session, ± standard error); no participant data exist yet.

Agents: **mvt** is the marginal-value-theorem forager at the optimal long-run rate (true values, no tuning on the world: a near-optimal reference); **learner** is a delta-rule learner that learns the map from what it sees; **nearest** takes the nearest bush with no learning; **best k** is the best fixed number of bushes per patch (chosen with hindsight). The point gain of each session is set so the learner earns about 1,125 points in every session of PCX and PSP (PSC fixes the gain on purpose, so its points fall with travel time).

> **2026-11-25: the maps of PCX_S2, PSC and PSP were replaced by stretched Gaussians** (PCX_S2 2:1; PSC 2:1, 1:2, round; PSP 1:2, 2:1, round; DECISIONS, "Pilot value maps: stretched Gaussians in PCX_S2, PSC and PSP") and the cells realised again (the gains and learner points below are the new ones where marked; the **agent tables, mvt and best-k numbers, and bushes per patch below are of the earlier maps and are stale** until `agent_benchmark.py` is run on the new ones). On the 40 check worlds the learner earns 1118, 1126, 1131 (PCX), 1128, 1124, 1135 (PSC) and 1124, 1114, 1131 (PSP) points; nearest and oracle on those worlds: PCX 863, 930, 1071 and 1314, 1454, 1644; PSC 895, 979, 1041 and 1385, 1341, 1300; PSP 1057, 993, 982 and 1384, 1434, 1623.

---

## PCX: Pilot Complexity

**What is varied.** The point-value map over the two visible features (shape, colour) is a single Gaussian bump, moved from a simple corner peak (S1, additive) to an axis-aligned peak away from the corner (S2, multiplicative) to a rotated ridge (S3, non-separable). The knob is how far the value of one feature depends on the other: interaction 0.09, 0.18, 0.40; nonlinearity 0.14, 0.43, 0.92. Held fixed: inequality of bush values (Gini 0.55), travel time (5 s) and the learner's expected points.

**Where to see it.** `docs/pilots/pilot_trends.png` (the three value maps with the world's bushes as dots, contour at half the peak, and the descriptors across sessions); `docs/pilots/PCX.txt` (numeric span-and-hold check); `docs/pilots/agents.md` (agent table).

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

**Where to see it.** `docs/pilots/pilot_trends.png` (the three maps: a Gaussian stretched 1:2, 2:1 and round, narrower and taller); `docs/pilots/PSP.txt` (numeric check).

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

## PSC: Pilot Spacing (redesigned 2026-11-23)

**What is varied.** The travel time between patches: 3, 6 and 9 s. Patches are pushed farther apart, so the world holds fewer of them (79, 33 and 18 tiles). Each session has a different round value bump at Gini 0.5 (interaction 0.13 to 0.15, nonlinearity about 0.4), centred at a different point, so each needs fresh learning. To hold the number of bushes harvested roughly equal, the longer-travel sessions are longer (180, 200 and 220 s), and to hold the learner's points equal they have a larger gain (1.31, 1.42 and 1.51; peak bush 5.2, 5.7 and 6.0).

**Where to see it.** `docs/pilots/pilot_trends.png` (the three value maps and the hexagonal layouts); `docs/pilots/PSC.txt` (numeric check; mean bush value rises with the gain, 1.75 to 1.98, which the check flags by design); `docs/pilots/agents.md` (agent table); the top-down layouts are in the third row of `pilot_trends.png` (79, 33 and 18 tiles).

Averages over 20 unselected worlds, each at its own session length:

| | S1 (3 s, 180 s) | S2 (6 s, 200 s) | S3 (9 s, 220 s) |
|---|---:|---:|---:|
| Learner, points | 1133 ± 8 | 1131 ± 8 | 1134 ± 9 |
| Learner, bushes harvested | 46.6 | 47.8 | 47.7 |
| Learner, bushes per patch | 5.7 | 6.8 | 6.9 |
| mvt benchmark, points | 1423 ± 7 | 1382 ± 9 | 1346 ± 10 |
| mvt benchmark, bushes harvested | 36.6 | 34.6 | 33.7 |
| mvt benchmark, bushes per patch | 2.56 | 2.90 | 3.30 |
| Nearest-bush agent, points | 900 | 969 | 1047 |

**Key differences in agent behaviour**
- Longer travel rewards staying longer in each patch: the optimal bushes per patch rises 2.6, 2.9, 3.3 (2.9, 3.1, 3.6 when the benchmark believes the within-patch step people take). This is the opposite direction from PSP and the marginal-value-theorem prediction.
- The learner moves the same way (5.7, 6.8, 6.9) but overstays at every level.
- The sessions' lengths and gains remove most of the confounds of the first design: the number of bushes harvested and the learner's points are about equal across sessions (the benchmark's points still fall about 5%).

**Caveats.** The sample counts and points are matched for the simulated learner; people may behave differently. The progression in bushes per patch is smaller on an average world than on the chosen ones (S1 to S2 +0.34, against +0.55 on the chosen worlds). The pre-pilot data collected before 2026-11-23 used the earlier design (one additive map in all three sessions, fixed gain, 180 s) and is not comparable.
