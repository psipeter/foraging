# Agents on the realised sessions

Mean points earned and mean bushes harvested per patch visit (± standard error across worlds) of five agents, from `scripts/agent_benchmark.py`. top-k and thr-q are tuned with hindsight on each world, mvt is not.

## PCX

| agent | PCX_S1 points | PCX_S1 bushes/patch | PCX_S2 points | PCX_S2 bushes/patch | PCX_S3 points | PCX_S3 bushes/patch |
|---|---:|---:|---:|---:|---:|---:|
| nearest | 863 ± 6 | 7.83 ± 0.00 | 923 ± 6 | 7.84 ± 0.01 | 1078 ± 7 | 7.84 ± 0.01 |
| learner (delta rule) | 1117 ± 9 | 5.65 ± 0.11 | 1132 ± 9 | 6.23 ± 0.10 | 1122 ± 15 | 7.60 ± 0.04 |
| best top-k (hindsight) | 1344 ± 5 | 2.84 ± 0.09 | 1464 ± 6 | 2.80 ± 0.08 | 1676 ± 9 | 2.97 ± 0.04 |
| best thr-q (hindsight) | 1357 ± 4 | 2.67 ± 0.07 | 1479 ± 6 | 2.85 ± 0.06 | 1688 ± 9 | 3.07 ± 0.07 |
| mvt (marginal value) | 1346 ± 8 | 2.42 ± 0.03 | 1470 ± 10 | 2.36 ± 0.03 | 1681 ± 10 | 2.85 ± 0.02 |

Worlds per session: 20 (the session's own, then seeds 1000 up). Mean k and q chosen: PCX_S1: top-2.9, thr-69; PCX_S2: top-2.9, thr-67; PCX_S3: top-3.0, thr-65.
Knobs: PCX_S1: class additive, gini 0.55, travel_time 5.0; PCX_S2: class multiplicative, gini 0.55, travel_time 5.0, interaction 0.18; PCX_S3: class nonseparable, gini 0.55, travel_time 5.0, interaction 0.4.

## PSP

| agent | PSP_S1 points | PSP_S1 bushes/patch | PSP_S2 points | PSP_S2 bushes/patch | PSP_S3 points | PSP_S3 bushes/patch |
|---|---:|---:|---:|---:|---:|---:|
| nearest | 1034 ± 4 | 7.84 ± 0.01 | 1000 ± 6 | 7.85 ± 0.01 | 983 ± 7 | 7.83 ± 0.01 |
| learner (delta rule) | 1116 ± 8 | 7.64 ± 0.03 | 1129 ± 6 | 7.28 ± 0.14 | 1138 ± 10 | 6.99 ± 0.13 |
| best top-k (hindsight) | 1370 ± 6 | 3.67 ± 0.11 | 1484 ± 8 | 2.88 ± 0.08 | 1644 ± 6 | 2.20 ± 0.09 |
| best thr-q (hindsight) | 1376 ± 5 | 3.62 ± 0.12 | 1486 ± 7 | 2.86 ± 0.08 | 1653 ± 8 | 2.28 ± 0.08 |
| mvt (marginal value) | 1343 ± 10 | 2.99 ± 0.03 | 1454 ± 9 | 2.54 ± 0.02 | 1641 ± 12 | 2.08 ± 0.02 |

Worlds per session: 20 (the session's own, then seeds 1000 up). Mean k and q chosen: PSP_S1: top-3.9, thr-59; PSP_S2: top-3.0, thr-66; PSP_S3: top-2.2, thr-74.
Knobs: PSP_S1: class round, gini 0.4, travel_time 5.0; PSP_S2: class round, gini 0.5, travel_time 5.0; PSP_S3: class round, gini 0.6, travel_time 5.0.

## PSC

| agent | PSC_S1 points | PSC_S1 bushes/patch | PSC_S2 points | PSC_S2 bushes/patch | PSC_S3 points | PSC_S3 bushes/patch |
|---|---:|---:|---:|---:|---:|---:|
| nearest | 797 ± 5 | 8.45 ± 0.02 | 730 ± 3 | 8.40 ± 0.15 | 680 ± 7 | 8.52 ± 0.04 |
| learner (delta rule) | 1127 ± 7 | 4.86 ± 0.07 | 905 ± 7 | 5.96 ± 0.08 | 791 ± 8 | 6.39 ± 0.06 |
| best top-k (hindsight) | 1353 ± 7 | 2.37 ± 0.11 | 1086 ± 6 | 3.13 ± 0.14 | 938 ± 3 | 3.47 ± 0.10 |
| best thr-q (hindsight) | 1357 ± 6 | 2.24 ± 0.08 | 1096 ± 5 | 2.97 ± 0.08 | 924 ± 5 | 3.40 ± 0.11 |
| mvt (marginal value) | 1357 ± 9 | 2.03 ± 0.02 | 1082 ± 8 | 2.56 ± 0.04 | 906 ± 10 | 3.10 ± 0.04 |

Worlds per session: 20 (the session's own, then seeds 1000 up). Mean k and q chosen: PSC_S1: top-2.4, thr-74; PSC_S2: top-3.2, thr-66; PSC_S3: top-3.5, thr-60.
Knobs: PSC_S1: class additive, gini 0.55, travel_time 3.0; PSC_S2: class additive, gini 0.55, travel_time 6.0; PSC_S3: class additive, gini 0.55, travel_time 9.0.

## FOR

| agent | FOR_S1 points | FOR_S1 bushes/patch |
|---|---:|---:|
| nearest | 1043 ± 5 | 8.81 ± 0.03 |
| learner (delta rule) | 1083 ± 11 | 7.11 ± 0.13 |
| best top-k (hindsight) | 1267 ± 3 | 3.65 ± 0.12 |
| best thr-q (hindsight) | 1281 ± 6 | 3.64 ± 0.15 |
| mvt (marginal value) | 1259 ± 6 | 3.23 ± 0.03 |

Worlds per session: 20 (the session's own, then seeds 1000 up). Mean k and q chosen: FOR_S1: top-3.7, thr-58.
Knobs: FOR_S1: class additive, gini 0.4, travel_time 8.0.

## TUT

| agent | TUT_S1 points | TUT_S1 bushes/patch |
|---|---:|---:|
| nearest | 684 ± 6 | 7.99 ± 0.01 |
| learner (delta rule) | 739 ± 4 | 7.27 ± 0.13 |
| best top-k (hindsight) | 918 ± 6 | 3.00 ± 0.12 |
| best thr-q (hindsight) | 918 ± 4 | 3.14 ± 0.11 |
| mvt (marginal value) | 904 ± 5 | 2.70 ± 0.04 |

Worlds per session: 20 (the session's own, then seeds 1000 up). Mean k and q chosen: TUT_S1: top-3.1, thr-64.
Knobs: TUT_S1: class additive, gini 0.4, travel_time 5.0.

