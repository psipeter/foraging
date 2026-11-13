# Validating recorded runs and releases (2026-11-14)

**Scope (PI decision 2026-11-14): a small validator and a release checklist. Nothing more until a pilot argues for it.**

## Built: `scripts/validate_run.py`

`./venv/bin/python scripts/validate_run.py <session folder | run folder | run id | --all> [--json]` reads a logged run (a local `ForagingData/<run>/` or one pulled with
`server_admin.py pull` / `human_data.py download`) and reports PASS / WARN / FAIL / SKIP per check, with the numbers that disagree; exit code 1 on any FAIL. It reuses
`rundata` and `replay`. Three groups:

1. **Scoring, recomputed independently of the C# code.** `foraging_points` equals the last fruit's running total and the sum of the fruit rewards, each of which equals the
   world file's pre-drawn reward; each ranking set's `correct_pairs` / `total_pairs` equal `ranking.pair_scores` recomputed from the logged picks and true values (this
   tests `RankingSets.ScorePairs` against Python on real data); `points` = correct pairs x `rankingBonusPerPair` (0 in practice); `ranking_points` is the sum of the sets'
   points; the `session_end` payload and the session row agree.
2. **Integrity.** Events contiguous and ordered (except across a resume), one start and one end, frame count equals the session row's, break events balanced, every set
   has start and end events and a row, the world hash matches the file.
3. **Break rules.** Each break started at a patch switch, not inside the cooldown, not before the minimum bushes, not in the last seconds; the player stood still and no
   foraging fruit was logged during a break; foraging time equals `sessionDuration`; sets came from the pool in order.

Tests (`scripts/test_validate_run.py`) use small golden sessions with one injected fault per check kind, plus the two real browser runs of 2026-11-13 as fixtures
(`scripts/fixtures/runs/`, participant fields stripped).

**When to run it:** on every pilot run (`validate_run.py --all` after `human_data.py download`), and after any change to `RankingBreak`, `RankingSets`, `DataLogger`
or `replay.py`. A FAIL is either a validator bug or a game bug; decide which before collecting more.

## Release checklist (by hand; each line has a command that proves it)

Before `server_admin.py publish` and `deploy_webgl.sh`:
- Git: `git status` clean (the font atlases excepted), HEAD pushed, `Builds/web/StreamingAssets/build_info.json` has `"commit"` = `git rev-parse HEAD` and `"dirty": false`.
- Tests: `run_tests.py --all` green at HEAD (slow tests need the PI's yes); `validate_run.py` clean on the latest pilot or browser run.
- Generated files fresh: `world.py` / `ranking.py pool` output equals the committed files (the slow freshness tests); `online.json` has `"enabled": true`.
- Server: every migration applied (`select version from supabase_migrations.schema_migrations`), the Edge Functions' `updated_at` (`supabase functions list`) is later than the last commit touching
  `supabase/functions`, `ALLOWED_ORIGIN` set. **Migrations and functions go together** (an old build breaks in between); back up with `db_backup.py` first.
- Unity: `recompile` clean, no console errors, scenes saved, build target back to Linux after a WebGL build.
- After deploy: `https://<user>.github.io/foraging-web/StreamingAssets/build_info.json` shows the new commit (Pages caches up to 10 minutes); play one reduced run in the browser
  (`?short=0.3`), `human_data.py download`, `validate_run.py` on it.

## Not built, on purpose

A scripted `release_check.py`, `monitor_runs.py`, a scheduled canary, a server-side guard in `finish_run`, CI with fixture runs, a validation table in the database, and the
behaviour warnings (idle share, hidden tab, duplicate runs). They pay off with many unattended participants; at pilot scale each run is looked at anyway. The full design
is in git history of this file (commit `bbf06e5`). Revisit after a pilot.
