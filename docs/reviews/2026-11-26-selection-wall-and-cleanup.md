# Adversarial review, 39767b9..ca43c77 (2026-11-26)

Scope: six commits (dense 5x5 selection, rename ranking to selection, scoring, validator tolerance, the wall stage with bushes grown out of it and the grid orientation cycle, IRB consent text, ID screen notes, menu payment column). Reviewers: simplifier (dry run), red-team. Full reports: `scratchpad/review/simplifier.md` (SM-n, B1-B4) and `scratchpad/review/red_team.md` (RT-n). No engine or agent file (ENGINE_FILES, AGENT_FILES) changed in the range, and none of the proposals below needs to touch them. Nothing has been applied. No conflict between the two sides needed the arbiter, so there was no rebuttal round and no arbitration.

## Verdict

11 red-team findings (4 medium, 7 low, no blocker), 8 simplifier proposals plus a small tier, 4 suspected bugs (B1-B4, all confirmed). 9 items are safe to apply, 0 were arbitrated, 9 are for the person.

## Safe to apply (agreed and small)

| ID | What | Verify |
|---|---|---|
| RT-1 | `visibility.py` samples a rotated set of canopy points for every upright bush (the new basis uses `cross(up, x)`; the old frame was x, z). Use `side = cross(up, (0, 0, 1))` with the fallback `(1, 0, 0)` when up is parallel, `side2 = cross(side, up)`, so an upright bush has the old points. Add a regression test that an upright bush gives the old points. | `run_tests.py`; fixture 0ef0ba46 gives 10,222 sightings / 3661.09 again only if the points match the old ones (the red-team reproduced the old output with an upright frame) |
| RT-3 | Tests that can fail for the live rules: a synthetic dense, time-scheduled log through `validate_run` (the dense scoring branch and the 4-decimal tolerance), one tipped-bush aim test for `_aimed`, one exact partial-pick score test for `top_k_score`. About 50 test lines. | The two hand mutants the red-team found (aim ignoring the up axis; a missing pick counted as an average bush) must now fail |
| RT-6 (B4) | The resumed `Points` of a dense practice session is computed as hits times the pair bonus (`SelectionBreak.cs:170-171`). Use the dense rule. | Needs a playtest of a resumed tutorial |
| RT-9 (B2) | `ExperimentConfig.cs:109` and `SessionTimerUI.cs:182` test `SelectionEvery > 0`; use `SelectionTimes.Length > 0` or either. Falls out of SM-3 if that is taken. | recompile; console |
| RT-11 / SM-5 | Docs: rewrite the arc-design description in SCIENCE.md (172-179), the rename artifacts at SCIENCE.md 253 and 466, CODEMAP's `selection.py` entry, REGENERATING line 13; document `rank_set`, `rank_set_end`, `rank_due` payloads and the dense meaning of `correct_pairs` / `total_pairs` (hits and k) in ONLINE_DATA_PLAN; add `TopKScore` / `top_k_score` to CLAUDE.md's mirrored pairs and the renamed hint ids (`ranking_start`, `ranking_end`) to its stored-names list; say that `FOR_S1` is a stale template. | read |
| Small tier (SM) | Stale comments and headers (`SelectionBreak.cs` 8-14, 424, 709, 753; `SelectionDisc.cs`; `replay.py` docstrings; `design/FOR.py` 24 and 29-30); inline `GrayFade(float)` and `HideHud`; delete the duplicate `SetStationary(false)` at 403 and 564-567; replace `_setCounter` with `_poolIndex`; delete the unused pool fields `bearing`, `n`, `setSize`; `dense_grid.py` unused tuple, `solve`'s unused `world` parameter, the always-empty `PRESET`; `pilot_figures.py` imports `load_session` from `world`. About -30 code lines. | recompile and console for the C#; the Python items passed in scratch with pools byte-identical |
| RT-4 | Logs written before the rename (`ranking*` keys) are misread by `replay.verify` without notice (6 problems on the pre-rename fixtures) while `validate_run` calls them fine. Cheapest: mark them unsupported in `load_session_log` (1 line, as `validate_run` does for other old formats). Alternative: alias the keys (3 lines). `ForagingData/` holds 138 such sessions, all debug or dev. | a test on a pre-rename fixture |
| RT-7 | `visibility.py`'s angular `height` is wrong for a wall bush, which is seen end-on; use the extent along the viewing direction, or document it. About 3 lines. | test |
| Net lines | Red-team adds about +60 lines (50 tests, 10 code); simplifier small tier removes about 30; the larger proposals below remove far more. | |

## Decided by the arbiter

None.

## For you (escalations and choices)

1. **SM-1: retire the exploratory and dead-design Python?** Delete `adaptive_grid_sim.py`, `fixed_grid.py`, `harvest_grid.py`, `plus_plans.py`, `selection_plus.py`, `selection_recovery.py` and their four tests; cut `selection.py` from 645 to about 209 lines; give `dense_grid` a 14-line `World`. About -2,080 code lines and -457 test lines (plus 347 lines of `docs/pilots` outputs, optional). Not scientific design. Cost: rebuild `FOR_S1` (the template) as dense, and update CODEMAP, SCIENCE, REGENERATING. Prototyped in a scratch copy: all 10 committed pools regenerate byte-identical. Option A: do it now. Option B: keep for a possible later return to the arc design (the tag `pre-cleanup` already holds old code).
2. **SM-2: retire the arc and pair-scoring path in C# and the validator?** Removes `ScorePairs` / `PairWeight`, the rank label, about 15 `SessionConfig` fields, `Dense` branches, `selectionPaid` "one". About -180 C# lines and about -100 Python and test lines. The fixture runs 0ef0ba46 and d0a5fb74 are pair-scored and leaving-triggered, so they need replacing with a dense run. It changes the logged config blob (fewer fields). Option A: do it, after SM-1. Option B: leave it; the cost of leaving is the 45 selection fields, 17 properties never read, and a newcomer misled by defaults of the dead design.
3. **SM-3: retire the patch-leaving trigger? (session flow)** Removes about 90 lines in `SelectionBreak`, 15 in `TutorialHints` (`patch_switch`), 6 config fields, about 110 validator lines and 60 test lines; "has selections" becomes `SelectionTimes.Length > 0` (also fixes RT-9 / B2). The deferred `_lastEnd` resume gap becomes moot. Option A: do it. Option B: keep the possibility of leaving-triggered selections.
4. **SM-4: fix one set per break? (session flow)** About -30 C# lines (the set loop, the not-last branch, `_rerunFrom`); `selectionSets` is 1 in every asset. Option A: do it. Option B: keep the multi-set capability.
5. **RT-2 (data column meaning): ties at the 5th and 6th place.** The shipped pools have exact ties at the boundary in 6 sets (TUT 0 and 1, PCX_S2 4, PSC_S3 3, PSP_S2 4 and 0). C#'s `List.Sort` is unstable and Python's is stable, so `correct_pairs` (top-5 hits) can differ between the game and `validate_run` (emulated .NET sort: PSC_S3 set 3 and PSP_S2 set 0; unverified that Unity sorts exactly so). The score is value-based and right; only the hit count and the validator's agreement are affected. Fix: a pick is a hit if its value is at least the 5th-best value minus 1e-4, on both sides (about 6 lines). Changes what the stored column means for ties. Option A: apply. Option B: leave `correct_pairs` as an informational column and make the validator not compare it at ties.
6. **RT-5 (task parameter): double touches on the wall.** On the wall the two bushes of a column are equally near, so where the 1-degree circle touches both, C# takes the first in scene order and replay may take the other (8 of 50 sets, the two upper rows of an outer squat column, about 0.5 square degrees each). SCIENCE.md's "never both touched" is false. A radius of 0.8 degrees has no overlap in any set. You said targeting is fine, so Option A: keep 1 degree, fix the doc and make replay break ties like C# (needs a stable rule on both sides). Option B: 0.8 degrees (small change in hit tolerance).
7. **RT-8 (needs a visual check):** at tilt 90 the mesh keeps its 0.3 dome while `HeightAt` drops it, so bushes stand up to 0.3 behind the drawn surface and the squat column's middle row looks about 2.5% narrower. Option A: look at it in a playtest first. Option B: drop the dome at 90 or make both consistent (about 2 lines).
8. **SM-6 / SM-7 / SM-8 (taste):** drop the 17 `SessionConfig` properties no C# reads (serialized fields stay); drop or redo `independence.pool_builds` (ladder-only; also removes RT-10 / B1, `dense_sets` planning on the asset's map whatever `generate_pool` overrides); split the HUD out of `SelectionBreak` only if SM-2 to SM-4 are not done.
9. **B3, the hint-id rename:** the hint ids `ranking_start` / `ranking_end` became selection ones; they are stored keys, outside CLAUDE.md's stored-names list. Harmless with no participant data; Option A: add to the list (docs). Option B: restore the old ids.

## Declined or deferred (propose additions to "Known and deferred")

- B4's end-screen wrongness only after a resume of the tutorial: it is in "safe to apply" above; if left, record it.
- The constant `("stage", true)` key in the `rank_set` payload has no reader; leave it (a column-like payload key; removal is a log change).
- Proposed additions to Known and deferred, if the person declines: RT-5 (double touch, with the radius options), RT-8 (dome at 90 degrees), RT-4 (old-format logs), RT-2 (ties), with a pointer to this report.

## Residual

- C# was reviewed by reading only; RT-5, RT-6 and RT-8 need a playtest to confirm; every C# item above needs `unity command recompile` and a console check after editing.
- The red-team ran `run_tests.py --fast` since 39767b9: 630 passed, 1 skipped, 8 deselected. `--all` was not run by it (it was run once before the last commit: 668 passed, 1 skipped).
- Hash sensitivity: none of the proposals touches an engine or agent file; deleting `adaptive_grid_sim.py` and friends changes no stored hash.

## Checked and held up

The C# aim matches replay's (the bush's up axis is the disc's up, the centre is the logged root position, the logged radius and half-height come from the right axes); old logs without `up_x` replay as upright; `TopKScore` and `top_k_score` agree; the consent file's version parsing works and the new version asks everyone again by design; the payment column is null-safe; no `ranking*` keys remain in the assets.

## Applied (2026-11-26, after the PI's answers)

The PI kept the arc, ladder, pair-scoring and patch-leaving code for now (SM-1 to SM-4; notes in `docs/RETIRE_ARC_DESIGN.md`) and allowed small fixes for the wall depth and double touches.

Applied: RT-1 (basis, golden-value test), RT-7 (angular height), RT-3 (tests: dense validator branch with the 4-decimal tolerance, a cut-short selection, practice pays 0, tipped-bush aim), RT-4 (pre-rename logs are unsupported), RT-6 / B4 (resumed dense end-screen points), RT-9 / B2 (the pool preload and split clock accept a times-only session), RT-8 (the mesh dome follows cos(tilt)), the small tier except two items (stale comments and headers, `GrayFade` / `HideHud` inlined, unused pool fields, `dense_grid` cleanup, import, comments), and the docs (SCIENCE, CLAUDE.md, ONLINE_DATA_PLAN, CODEMAP, DECISIONS, REVIEW_POLICY).

Not applied: RT-2 (ties; changes a stored column's meaning; recorded in Known and deferred), RT-5 (double touches: the PI saw none; tooltip corrected, recorded in Known and deferred), SM-6 to SM-8, and two small-tier items that need a playtest to be sure (`_setCounter` into `_poolIndex`, the duplicate `SetStationary(false)`).

Checks: `run_tests.py --fast` 259 passed, 1 skipped; `unity command recompile` clean; all ten pools regenerate byte-identical. Not run: `--all`; the C# changes (resume points, the dome at tilt 90, the inlined helpers) have not been played.
