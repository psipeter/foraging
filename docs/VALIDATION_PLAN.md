# Validation plan: knowing that what is recorded is what happened (drafted 2026-11-14; nothing built)

Today's checks: `replay.py verify` re-derives the harvests from the trajectory; `server.finish_run` checks that sessions are complete, contiguous, have a
`session_end` and a trajectory; `test_server.py` / `test_resume_breaks.py` test the protocol; the unit tests pin the generators and the scoring. The
browser test of 2026-11-13 (two FOR runs) was read by hand. Nothing yet answers, for a real participant's run, "is this data trustworthy, and did the
game do what the design says?", before and after release. The machinery below does, in three layers.

## Layer 1: a run validator (`scripts/validate_run.py`)

`validate_run.py <run folder | run id | --all> [--json]` loads a run through `rundata`/`replay` (so it works on a pulled run or a local folder) and
reports PASS / WARN / FAIL per check, with the numbers that disagree. It is read-only, needs no server, and is the base of the other layers.

**Integrity (the data is complete and self-consistent)**
- Events: `seq` contiguous from 0, `t` non-decreasing except across a `session_resume`; one `session_start`, one `session_end` per completed session.
- Trajectory: frames contiguous, the count equals `frame_stats.count`; frame gaps (dt) summarised, long gaps listed (tab hidden, upload hold).
- Ranking rows: `ranking_sets.seq` contiguous; one `rank_set_end` event per row; `rank_break_start` / `rank_break_end` pairs balanced; every `rank_set`
  has a start and an end.
- Worlds: the logged `world_sha256` equals the hash of the world file at the run's build commit and is registered; the ranking pool likewise.

**Scoring (recomputed from the raw record, independent of the C# code)**
- `foraging_points` equals the last fruit event's `running_total` equals the sum of fruit rewards, and each fruit's reward equals the world file's
  pre-drawn `fruit_reward[bush][k]` (the replay already derives the fruits; the check compares paying values).
- `ranking_points` equals the sum of the sets' `points`; each set's `correct_pairs` / `total_pairs` equal `ranking.pair_scores` recomputed from the picked
  order and the pool file's true values (this tests `RankingSets.ScorePairs` against Python on real data); `points` = correct pairs x the session's
  `rankingBonusPerPair`, 0 in a practice session.
- `session_end` payload parts equal the session row's.

**Design (the game did what the configuration says)**
- Ranking breaks: each break started at a patch switch (nearest tile changed in the trajectory), not inside the cooldown (`rankingCooldown`) of the previous
  break, not before `rankingMinBushes` bushes were harvested, not in the last `rankingLastSeconds`; `rankingEvery` and `rankingSets` respected.
- During a break: the player did not move (trajectory x, z constant), no foraging fruit was logged, the clock `t` ran on while the foraging clock
  (`t - held_seconds`) did not; the session lasted `sessionDuration` of foraging time.
- Sets came from the pool in order (`pool_index` runs 0, 1, 2, ... wrapping at the pool size) and the logged bush table equals the pool's.
- Harvest rule: `replay.verify` (range, crosshair circle, release) with the number of bouts the game ended; flag more than the tail's.
- The logged `SessionConfig` equals the asset at the build commit for every field that shapes behaviour (a stale or hand-edited asset in a build shows here).
- Resume: each `session_resume` has a sensible gap and the restored clock, pose and score continue the pre-gap values.

**Behaviour (for exclusion rules, WARN only)**
- Idle share, windows with no key or mouse input, a hidden tab (focus events), a reduced run (`run_modes`), implausibly fast or slow runs, a
  participant with several runs of the same experiment.

Output: one table per run plus a summary count; exit code non-zero on any FAIL so scripts can gate on it. Tests: golden logs built with the
`rundata`/`synthetic` helpers with one injected fault each (a dropped event, a wrong running total, a break inside the cooldown, a wrong pair count) must
raise exactly that check; the two real browser runs of 2026-11-13 are the first positive fixtures (copied into a test fixtures folder, small).

## Layer 2: a release check (`scripts/release_check.py`)

Run before every `publish`; prints a checklist and exits non-zero on a FAIL. Each item has a command that proves it, so the PI does not rely on memory.
- Git: tree clean (the font atlases excepted), HEAD pushed, the build's `build_info.json` commit equals HEAD, `dirty` false, `development` as intended.
- Tests: `run_tests.py --all` (slow tests need the PI's yes) was green at HEAD (the check records the last green commit in a small file and compares).
- Generated files fresh: worlds, ranking pools and instruction texts equal what the design and generators produce now; `online.json` enabled.
- Database: every migration file is applied (`supabase_migrations.schema_migrations`), the live columns equal the expected schema (a short schema
  fixture), the deployed Edge Functions' time is not older than the last change to `supabase/functions` (their hash cannot be read back, so the time and
  a `/health` style probe are used), the build's world files are registered, the release row and experiments are registered, `ALLOWED_ORIGIN` is set.
- Unity: no console errors after a recompile; the build target is Linux again; scenes clean.
- Build smoke: `webgl_smoke.mjs` against the build (loads, logs in, plays a reduced run, uploads, resumes), then `validate_run.py` on the run it made.

## Layer 3: after release

- `scripts/monitor_runs.py` (cron or by hand): `human_data.py download`, then `validate_run.py --all --json` on the runs new since the last call;
  prints FAIL/WARN, completion and dropout counts, runs stuck `in_progress` for more than a day, upload-hold (`pause` reason `upload`) rates, p95 frame
  times by platform and browser. Results go to `ForagingData/validation.sqlite` (local, with participant IDs) so a failing run is never lost between looks.
- Server-side guard (later, if real data shows a need): extend `server.finish_run` problems with the cheap integrity checks above (points equal sums,
  set rows equal events), so a finished run carries a flag instead of waiting for the analysis.
- A canary: one scheduled synthetic run through the deployed endpoints (`server_smoke.py`) after each deploy, to catch a broken Function before a participant does.

## Order of work

1. `validate_run.py` integrity and scoring checks, with the fault-injection tests (about a day); run it over all existing runs and fix what it finds.
2. The design checks (break trigger rules, held clock, pool order), since they are what the experiment depends on.
3. `release_check.py`, then wire it before `publish`.
4. `monitor_runs.py` once real participants start; the server-side guard and the canary last.

## Decisions for the PI
- Which checks are FAIL (exclude the run) and which only WARN (a participant's idle share is an analysis choice; keep it a WARN).
- Whether the validator may run in CI on the repository (needs the two fixture runs committed; participant IDs stripped).
- Where validation results live (local only, as proposed, or a table in the database).
