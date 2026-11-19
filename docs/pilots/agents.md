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

