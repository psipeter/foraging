# Adversarial review, 2026-11-17: the reward function is a sum of Gaussian bumps

Scope: the uncommitted diff against `b1bd7fd` (35 files, +278 / −762): the removal of the per-feature ramp components, product and sigmoid terms, `randomBushValueRange`, `moistureIsFeature`, `terms_relevance` / `RELEVANCE` / `session_features` and `Ramp` / `ramps`; FOR_S1 and TUT_S1 rebuilt as the additive rung; design modules, `synthetic.py` and `FIX_T0` rebuilt on `ValueMap`. Not in scope: the `ExperimentConfig.cs` rounding fix and the "Addendum 2026-11-16" hunk of DECISIONS. Full reports: simplifier (dry run, each proposal tried in a scratch copy) and red-team; the red-team's "Checked and held up" list is summarised under 6.

Intent: reward is a value map, one primitive; moisture never pays; code, docs and tests should say so.

## 1. Verdict

No data or scoring defect. Found: 9 small simplifications, 4 red-team findings (1 medium), 2 findings outside the diff, 8 proposals that need the person. No conflicts between the two reviewers (SM-3 and RT-2 are two sizes of one fix), so no rebuttal and no arbiter. Nothing applied.

## 2. Safe to apply (agreed and small)

| ID | File | What | Verify |
|---|---|---|---|
| S1 | `scripts/value_maps.py` (`log_interaction` docstring) | Wrong since the ramps went: an additive map is not "above 0" in log interaction. The wide-corner additive rung and the multiplicative rung both read 0 (measured 1e-29) and differ only in the raw `interaction` | `test_value_maps.py` |
| S2 | `RewardBump.cs:8` | Comment says "Added to the reward function's per-feature terms" | recompile, console |
| S3 | `tiles.py:226` | Remove "(the reward at the middle moisture)" | tests (moves the engine hash, which already moved) |
| S4 | `fixtures/sessions/FIX_T0.asset:151` | Leftover `moistureIsFeature: 0` (FIX_T0 hash `0cc9c597575c` unchanged) | `test_fingerprint.py` |
| S5 | `WorldData.cs:338` | Stray blank line before the closing brace | recompile |
| S6 | `scripts/synthetic.py` | Unused parameters (`std` is silently ignored when a map is passed, `scale`, `spread`); 39 to about 33 lines | 109 tests pass in scratch |
| S7 | `test_world.py` | Drop the duplicated first clause of `test_moisture_pays_nothing` | tests |
| S8, S9 | `test_world.py`, `test_realization.py` | Delete the anisotropic-bump-versus-Unity test (duplicate of the formula test and the C# tilted-bump test) and "the bushes pay the value map" (duplicate of the `test_value_maps` world test); three hand mutants still caught | 46 tests pass in scratch |
| RT-4 | `SessionConfig.cs:209, 213, 217` | Three tooltips still say "give the shape/color component weight 0" | recompile |
| RT-1 | new fast test (about 6 lines) | A committed ranking pool is never compared with the session's value map: `CLAUDE.md` says `--all` checks pool freshness but no test reads a `*.ranking.json`. Evidence: HEAD's two pools (stale against the new maps by up to 0.545 and 0.736) pass all 78 tests in a copy of the tree. Test: each committed pool's `value` equals `bush_value(asset.reward_function, shape, color)` | the test itself, and a mutant putting HEAD's pools back |
| RT-3 | `world.generate_world` (2 lines) | A reward function with no bumps (or the removed format) silently gives an all-zero world (the logged config of `fixtures/runs/0ef0ba46` does); raise | tests |
| docs | TUT.py:21, CLAUDE.md, DECISIONS | "3/4 of the slope" is a measured 0.71 (the quarter-power recipe of `wide_corner`); say so; `SCIENCE.md:332` and `:644-645` (history) name `session_features`, `RewardProduct`, `randomBushValueRange` as if present: add "(removed 2026-11-17)"; `WorldData.cs:316` comment should state the gap RT-2 describes until it is fixed | read |

Net lines if all are applied: simplifier −22 (code and tests), red-team +9 (RT-1 about 6, RT-3 2, RT-2 one clause): about −13.

## 3. Decided by the arbiter

Nothing (no conflicts).

## 4. For you

1. **RT-2 / SM-3, the stale-world check.** `WorldData.FindMismatches` does not notice a bump added to a config at angle 0 and widthColor 0 (only `.widthColor` and `.angle` are checked from config to file), so a hand-added round bump gives no stale warning, and the bumps are the whole reward now. (a) the one-clause fix, also flag a missing `.centerShape` (about +1 line, no format change, recommended); (b) SM-3, always write every field in the header and flag any missing key (about −18 C#, −8 Python, regenerates the world files, changes the header format).
2. **A-1, a stale doc that bears on the tile radius.** The tile calibration of `SCIENCE.md:34` and DECISIONS ("FOR: tentative tile radius and bushes per tile": "thr-60, 4.3 bushes, +10.1%, the only setting where a few good bushes per visit is favoured") was already false at HEAD: rerun with `tile_calibration.py FOR_S1 --seeds 0-7 --set session_duration=180`, HEAD gives thr-40, 6.1 bushes, +9.2%, TOO MANY; the working tree gives thr-50, 5.3 bushes, +8.6%, TOO MANY. Mark it stale now (recommended), or re-open the radius?
3. **SM-1, `ValueMap(bumps, sd)` instead of `noise` / `equaliser` dicts** (−9 lines in `value_maps.py`, −17 in tests; changes the `value_map` JSON inside the logged designJson). It is in tension with your decision of 2026-11-17 that noise is a second map and the equaliser a pluggable slot. Recommended: decline.
4. **SM-2, remove the reward-stage machinery** (`REWARDS` has one entry; `reward_stage` and the callable threaded through 15 functions; −20 to −30 lines and one SessionConfig field). It reverses the recorded "kept for path B". Recommended: decline.
5. **Taste, no scientific effect:** SM-4 (move `value_map_design` from `design/FOR.py` into `value_maps.py`), SM-5 (merge the bump-formula tests into one file and rename `test_reward_terms.py`, named after terms that no longer exist), SM-6 (rename `gaussian()`'s `width` to `across`: `width` means the spread along shape in `Bump` and the short axis in `gaussian()`), SM-7 (if SM-2 is declined, rename the stage key "terms" and fix `SessionConfig.cs:209`'s tooltip), SM-8 (`FOR.py` 400-character lines, nested spread; TUT imports a private helper from FOR). Recommended: SM-4, SM-5, SM-6 yes; SM-7 and SM-8 your taste.

## 5. Declined or deferred (proposed for Known and deferred)

- A-2 (latent): `between_bimodal`'s "poor" region (at most 30 percent of the best) shrinks under a wide corner map (the map no longer reaches 0): 13 percent of the plane at base 0.7, empty from about base 0.95, where `_region` raises. FOR does not use bimodal; revisit when a session does.
- The `ranking_stage` and per-bush `moisture` field in the pool file stay as they were.

## 6. Residual and held up

- Held up (the red-team, by evidence): no live reader of a removed name (scripts, design, C#, Editor scripts, supabase, scenes and prefabs; the GUIDs of the four deleted scripts; golden run fixtures hold the old logged config but nothing evaluates it, replay, validate_run, visibility and rundata use the pre-drawn rewards); FOR_S1 and TUT_S1 worlds and pools regenerate identically; pool minimum gap per set at least 0.63 (FOR) and 0.68 (TUT) against a tie gap of 0.25; live bush values 0.57 to 4.0 (FOR) and 0.39 to 3.99 (TUT), realised slopes +2.07 and +2.07 (FOR), shape −3.15 and colour +1.18 (TUT), per-fruit rewards 0 to 6 as before so `rewardFeedbackMax` 4 needs no change; hint and instruction texts make no claim the maps break; the C# and Python bump rules agree (and I checked the TUT map at three points: identical to 6 places).
- Mutation: one hand mutant (the stale HEAD pools), which survived every test: RT-1.
- Could not check: Unity runtime behaviour of the stale check beyond the two sessions (read only); a playtest of FOR and TUT with the new rewards; `run_tests.py --all` (needs your approval).
- Hashes: `world.py`, `tiles.py` (engine) and `agents.py` (agents) changed, so every stored simulation result is stale (accepted); S3 edits `tiles.py` again (comment only) and moves nothing further.

## Status (2026-11-17, after the person's answers)

Applied: S1 to S9, RT-1 (`test_every_committed_pool_pays_its_sessions_value_map`; with HEAD's pool for TUT_S1 put back it fails, with the current one it passes), RT-3, RT-4 (the three tooltips), RT-2 (the one-clause stale check), the doc fixes (0.71 wording, "removed 2026-11-17" on the history passages), SM-4 (`ValueMap.describe()`), SM-5 (`test_bump.py`), SM-6 (`across`). A-1 marked stale in `docs/SCIENCE.md` and DECISIONS. Declined: SM-1, SM-2 (and SM-3 in favour of RT-2); SM-7 and SM-8 left. Added to Known and deferred in `docs/REVIEW_POLICY.md`: A-2, SM-1, SM-2, SM-7, SM-8.

