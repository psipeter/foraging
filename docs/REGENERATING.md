# Regenerating generated files

Moved out of `CLAUDE.md` on 2026-11-19 (the detailed recipes of "What to regenerate after a change", verbatim). `CLAUDE.md` keeps the short table of
triggers. The generated files are manual steps (nothing runs them at build time).

- **Session world** (terrain, seed, tile fields, mountains, canopy width/shape ranges,
  the value map and reward std, fruit count): `./venv/bin/python scripts/world.py <sessions> --unity`.
  Unity warns at startup when a session world is stale.
- **An experiment's sessions** (a session's reward function, which features vary, terrain, duration, instruction file, hints): edit the design table in `scripts/design/<code>.py`, then
  `./venv/bin/python scripts/build_experiment.py <code>` (an open Editor; it makes or updates the assets, writes the instruction texts and regenerates the worlds and ranking pools; `--no-generate` skips those,
  `--remove-stale` deletes assets the design no longer lists). The engine tests use the frozen `FIX_T0` in `scripts/fixtures/sessions/` (a session name starting FIX_ is read from there). (The ABAB design is archived in `archive/abab/`, the CF ladder script in `archive/cf_ladder/`; the old experiments TUT, FN, RW and FI are in git at tag `pre-cleanup`.)
- **Tutorial** (`design/TUT.py`: `TUTORIAL_*`, `INSTRUCTIONS`, `HINTS`): its own experiment `TUT` of one practice session `TUT_S1` (120 s, a world chosen by `cells.py` from the realised cell, ranking breaks on) that must be finished before the pilots unlock (each design's `REQUIRES`; FOR is only the template session), with `instructions_S1.txt` and `hints_S1.txt` in `StreamingAssets/Experiments/TUT/` (written by `build_experiment.py TUT` from the design file; a hints file needs no regeneration). **Reward and layout** (2026-11-17): TUT's and FOR's one session are realised cells (`design/tables/TUT.json`, `design/tables/FOR.json`, realised by `cells.py realize <table>` into `design/realized/`; the baseline: additive rung, round corner Gaussian, Gini 0.4, travel time 8 s for FOR and 5 s for TUT, the pool of bushes placed `balanced` (equal patch totals, 2026-11-18); FOR 180 s with the corner where both features pay more when higher, TUT 120 s with the corner where **shape pays more when lower** and colour when higher, so the practice does not teach FOR's rule). The map, gain, tile layout, world seed (searched among 100) and feedback maximum come from the realised file. Each session's logged `designJson` carries its map and descriptors. **Texts, in order** (every popup carries the small blue "Tutorial" label, `SessionConfig.sessionLabel`, in place of "Session n of m"): the Controls screen (1 s after the session starts, the game held), then pause popups from `TutorialHints` (`@bout 1` Harvesting, `@bout 2` Features, `@ranking_start 1` Ranking, 0.25 s after the first set's bushes have grown, `@ranking_end 1` Ranking, `@time_left 60` Scoring, `@time_left 30` Pausing (asks for [Escape]), with 60 s of foraging time left, the clock pulsing yellow), then the end screen "Tutorial complete" with the captions and note of `SessionConfig.scoreCaptionForaging` / `scoreCaptionRanking` / `scoreNote`. The full wording is in `design/TUT.py` and `docs/SCIENCE.md` ("The tutorial"). Rebuild with `build_experiment.py TUT`.
- **Ranking pool** (`rankingEvery`, `rankingLeavings` (no regeneration for the schedule), `rankingPoolSets`, `rankingSetSize`, `rankingArcSpan`, `rankingDistance`, `rankingTieGap` or the reward function of a session that has rankings): `./venv/bin/python scripts/ranking.py pool <session>` (`build_experiment.py` does it for a session with `rankingEvery` > 0). A tiles world file also carries `tileCentres`, `tileRadius`, `tileRamp` in its header (regenerate the world).
- **Tiles world** (`layout`/`assignment` `tiles`, `tileRadius`, `tileRampWidth`, `tileMoistureLevels`, `tileBushes`, `tileClusterRadius`, `tileClusterSpacing`, `tileArrangement`, `tilePlacement`, `tileCoverageMin`, `tileStartSpreadMin`, `tileSumTol`): regenerate the world as for a session world; Unity warns when a tiles file is stale (the numeric tile fields).
- **Fields only the removed generator read** (`spatialBalance`, `featureBalance*`, `featureCoverage`, `treeSpacing`, `placementJitter`, `startClearingRadius`, `terrainNoise*`, `moistureTerrace*`, `terrace*`): no Python generator or the simulator reads them now (a world file's header still echoes the terrace and `CHECK_KEYS` ones, which the game compares); changing them regenerates nothing and moves no environment hash.
- **No regeneration needed:** `targetFrameRate`, `sessionDuration`, `fruitHarvestDuration`, `playerMoveSpeed`,
  `rankingSeconds`, `rankingBonusPerPair`,
  audio volumes, instruction text.


## Testing (full text)

Moved out of `CLAUDE.md` on 2026-11-19 (the former "Testing" section, verbatim).

During a long change (several milestones), run `run_tests.py --fast` and leave the full run (`--all`, about 13 minutes: world and ranking pool freshness, the fingerprint field check, the simulator, agent, battery and
results runs) for the end of the work (PI, 2026-11-05); the slow checks to confirm then are listed in DECISIONS ("Test policy during the new-ladder milestones"). Tests of the old-ladder generators (lattice placement,
terraces, spatial balance, feature balance) were deleted with them (2026-11-13); git history keeps them.
**Tests state their configuration; they do not name a shipped session** (PI, 2026-11-09). Generator tests build sessions with `scripts/synthetic.py`
(which features are visible, what each pays and in which direction, the noise) on the frozen tiles session `FIX_T0` (tile fields stated in `synthetic.TILES`); `scripts/test_realization.py` checks that
what a configuration intends is what the generators produce (visible features vary, hidden ones do not, the value slopes equal the weights and
directions, the noise is the stated size, the session declares its features). The engine-level test modules
(simulator, agents, battery, results, analysis, fingerprint, replay, rundata) use `FIX_T0` as an arbitrary environment (several worlds through the world seed),
so changing or deleting a live experiment cannot move them. Only tests of the live files (freshness and the design tests) read the real assets.
**Slow tests (`slow` marker, `--all`) run only when the PI approves, after a major change and before a commit.**
`./venv/bin/python scripts/run_tests.py` runs only the Python test files the changed
files can affect (`--all` before committing; `--dry-run` shows the decision). `--fast`
additionally skips tests marked `slow` (freshness checks of committed generated files, long
planner searches): a few seconds vs about 35 s for everything, so use it while iterating, but run
the plain command after touching a session asset, `world.py`, `ranking.py` or the
planner. The tests call the real generators in memory and write nothing into the project. There
are no Unity-side tests.

**Validate a pilot run before trusting it:** `./venv/bin/python scripts/validate_run.py <run id or folder>` (read-only; `--all` for every run under `ForagingData/`, `--json`
for scripts). It recomputes the scoring independently of the C# code (foraging points against the fruit events and the world's pre-drawn rewards; each ranking set's pairs
and points against `ranking.rankings_to_points` (the payout rule: `SessionConfig.rankingPointsMode`, `pair` or `pair_mean_value`; the C# mirror is `RankingSets.ScorePairs` / `PairWeight`), its `rank_set_end` event and `session_end`), checks the log's integrity (event seq and clock, one start and end, frame count, break
and set events and rows, the world file's hash) and the design's break rules (a patch switch before each break, cooldown, minimum bushes, last seconds, player still, no
foraging fruit and the foraging clock lasting `sessionDuration`, the pool in order). FAIL = the data or scoring is wrong; WARN = undecidable. Old log formats (Interlude sessions, breaks of the early prototype, the `final_score` column, old column layouts) are unsupported:
they FAIL with one "unsupported log format" line (git history at b7e1895 has the code that handled them).
