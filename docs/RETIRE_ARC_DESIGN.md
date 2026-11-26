# Retiring the arc, ladder and pair design (notes for later; nothing here is done)

Written 2026-11-26 from the adversarial review `docs/reviews/2026-11-26-selection-wall-and-cleanup.md` (the simplifier's
proposals SM-1 to SM-4 and its scratch prototype). The PI decided to **keep** all of it until the grid approach (the dense 5x5
selection with a time schedule and top-k scoring) is validated on participant data; this file says what would go, so the
deletion is quick and safe once that happens. The tag `pre-cleanup` and git history keep the old code.

**What stays when this is done:** the dense design (`selection.dense_pool`, `dense_grid.py`, the top-k score, `SelectionSets.TopKScore`),
the time schedule (`selectionTimes`, `selectionMaxWait`), `SelectionDisc`, the stored names (`ranking_sets`, `ranking_points`,
`ranking_pairs`, `rank_*` events, `*.ranking.json`, `ranking-pool`). Do not touch `ENGINE_FILES` or `AGENT_FILES`: nothing below does.

## Order

1. SM-1 (Python only, no effect on the game or on logs).
2. SM-2 (C# and validator; needs a dense fixture run to replace two pair-scored ones).
3. SM-3 and SM-4 (session flow; do together with SM-2's fixtures).
4. Docs, last.

## SM-1: the pool generators and exploratory scripts (Python)

**Delete:** `scripts/adaptive_grid_sim.py`, `fixed_grid.py`, `harvest_grid.py`, `plus_plans.py`, `selection_plus.py`, `selection_recovery.py`
and their tests (`test_adaptive_grid_sim.py`, `test_fixed_grid.py`, `test_harvest_grid.py`, `test_selection_recovery.py`);
optionally the outputs in `docs/pilots/` that only they wrote (`adaptive_grid_sim*.txt`, `PSC_S1_harvest_grid_rules.txt`,
`selection_plus_plans.txt`, `selection_plus_recovery.txt`, about 347 lines).

**Cut `scripts/selection.py`** from 645 to about 209 lines: keep `dense_sets`, `dense_pool`, `grid_slot_position`, `grid_orientations`,
`top_k_score`, `top_k_values`, `top_k_hits`, `paid_set_index`, the pool export and `selections_to_points` (the validator still
needs it until SM-2); drop the ladder, plus and arc generators, difficulty, plans and the five analysis metrics.
`test_selection.py` goes from 379 to about 65 lines (keep the committed-pool freshness test, the pair-score tests, the pool path test).

**Needed first:** `dense_grid.py` imports a `World` wrapper from `adaptive_grid_sim` (which calls the plus design's `peak_and_frame`);
give it its own 14-line `World` (value map, peak, `value(cells)`, `vmax`). Also: `independence.pool_builds` is ladder-only and
wrong for dense (it plans on the asset's map whatever `generate_pool` overrides): drop it or point it at `dense_grid.plan_session`;
`pilot_figures.py` should import `load_session` from `world`; rebuild `FOR_S1` as dense (`build_experiment.py FOR`), since it is
still `selectionDesign: ladder`, `pair_mean_value`, tilt 0, `selectionPaid: one`.

**Verified in a scratch copy (2026-11-26):** with the above, all 10 committed pools regenerate byte-identical
(`selection.py pool <session>` then `git diff --stat Assets/StreamingAssets` shows nothing); the non-slow suite passed except 6
`test_publish*` that failed the same way on an untouched export.

## SM-2: the arc and pair path (C# and validator)

- `SelectionSets.cs`: `ScorePairs`, `PairWeight`, `IndexOf` (and the mirrored `selection.selections_to_points` and `POINTS_MODES`).
- `SelectionBreak.cs`: the non-`Dense` branches, the tree rank label (and `Tree.cs`'s rank label code that the label uses), `selectionPaid` "one".
- `SessionConfig.cs`: about 15 fields and properties: `selectionBonusPerPair`, `selectionPointsMode`, `selectionRankScale`,
  `selectionSetSize`, `selectionArcSpan`, `selectionDistance`, `selectionTieGap`, `selectionPlus*` (seven), `selectionPoolSets` if unused,
  and the 17 properties no C# reads (the serialized fields that Python reads stay until SM-1 is done). Removing a serialized field
  means `design/FOR.py` `SELECTION_FIELDS` and every session asset and fixture that carries it must be regenerated
  (`build_experiment.py` for TUT, PCX, PSC, PSP; the frozen `scripts/fixtures/sessions/FIX_T0.asset`).
- `validate_run.py`: the pair-scoring branch (`selection pair scores` check, `selectionBonusPerPair`, `pair_mean_value`).
- Fixtures: `scripts/fixtures/runs/0ef0ba46` and `d0a5fb74` are pair-scored and leaving-triggered; replace them with a dense,
  time-scheduled run (a short Linux-build run on a private display validates with `validate_run.py`; see CLAUDE.md "Playing the game
  without touching the person's desktop"), and update the tests that use them (`test_validate_run.py`, `test_replay.py`, `test_visibility.py`).
- The dense design puts hits and k in `correct_pairs` / `total_pairs`; keep those columns (stored names).

## SM-3: the patch-leaving trigger (session flow)

- `SelectionBreak.cs`: the leaving mode (about 90 lines): settle depth, cooldown, minimum bushes, last seconds, the leavings schedule,
  `rank_leaving`, `_lastEnd` (the deferred resume gap in REVIEW_POLICY becomes moot).
- `TutorialHints.cs`: the `patch_switch` trigger (about 15 lines), and `patch_switch` in `hints_S1.txt`'s comment.
- `SessionConfig.cs`: six fields (`selectionEvery`, `selectionLeavings`, `selectionMinBushes`, `selectionSettleDepth`, `selectionCooldown`,
  `selectionLastSeconds`). "Has selections" becomes `SelectionTimes.Length > 0`: change `ExperimentConfig.cs` (WebGL pool preload),
  `SessionTimerUI.cs` (the split clock) and `SelectionBreak.Create`'s condition together (today the first two test `selectionEvery > 0`
  while `Create` accepts `selectionTimes` alone: a latent trap).
- `validate_run.py` `check_break_rules` (about 110 lines) and its tests (about 60); `replay.py` / `visibility.py` need nothing for the
  trigger (they read the logged break windows), but keep the `rank_break_start` payload keys (`switches`, `tile`, `leaving`) as
  constants or drop them (a data-format choice: the server stores the payload as JSON; ask first).
- The server's resume fields for leavings (`ResumeReply`, `open_break_leaving`) can stay: unused, harmless.

## SM-4: one set per break

`selectionSets` is 1 in every asset: drop the loop over sets in `SelectionBreak.RunSet`'s caller, the `last` / not-last branches (fade,
wait, `RemoveSet`), `_rerunFrom` and `open_break_sets_done` handling, `indexInBreak` (about 30 lines). `replay.py` /
`visibility.py` keep working (a break is still a window).

## Docs to update when done

`docs/SCIENCE.md` ("Selection breaks", lines about the arc, leavings and pair points; the rename artifacts), `docs/CODEMAP.md` (the
`selection.py`, `selection_plus.py`, `plus_plans.py` ... entries), `docs/REGENERATING.md` (the pool recipe line), `docs/DECISIONS.md`
(add one entry: what was retired and why; older entries keep their text), `docs/ONLINE_DATA_PLAN.md` (the dense meaning of
`correct_pairs` / `total_pairs`), `docs/REVIEW_POLICY.md` (drop the deferred items that become moot), `CLAUDE.md` (the "Mirrored pairs"
list: `SelectionSets.ScorePairs` / `PairWeight` with `selections_to_points` go away).

## Verification

`unity command recompile` and the console after the C# edits; a Play-mode (or private-display build) selection of TUT and one pilot
session, `validate_run.py` on the result; `run_tests.py` (plain, then `--all` with the PI's approval); pools byte-identical
(`selection.py pool` for all ten sessions leaves `git status` clean).
