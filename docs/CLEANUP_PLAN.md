# Cleanup plan: everything becomes FOR (drafted 2026-11-13; nothing executed)

Goal: one experiment, `FOR`. A session is foraging in tiles with ranking phases (the "ranking breaks") in place. Nothing is called an Interlude, and
the old tutorials and experiments (TUT, FN, RW, FI) are gone. The tutorial is redesigned afterwards, on the prototype.

## What is there (survey)

| Area | Size |
|---|---|
| Experiment assets | `ScriptableObjects/Experiments/{TUT 3, FN 43, RW 45, FI 25, FOR 3}` files; `StreamingAssets/Experiments/{TUT 8, FN 120, RW 134, FI 92, FOR 8}` files (~50 MB old) |
| Design modules | `scripts/design/{FN,RW,FI}.py` (+ `common.py`, `FOR.py` stay) |
| Interlude in C# | 33 files; `SessionConfig.cs` 115 mentions, `InterludeManager.cs` 38, `WorldData.cs` 15, `DataLogger.cs` 12, `RunModes.cs` 13, `GameManager`/`ExperimentConfig` 11-12 |
| Interlude in Python | ~48 scripts + tests (largest: `test_agents`, `interlude.py`, `test_interlude`, `sim`, `ranking`, `human_data`, `agents`, `battery`) |
| Interlude in SQL/TS | 8 migrations and `handlers.ts` (table `interlude_trials`, 2 migrations not yet applied) |
| Old-alias users | 47 Python files reference `TUT/FN/RW/FI_*`, `S1`-`S7` or `LEGACY_NAMES` |
| Docs | CLAUDE.md 583 lines, SCIENCE 1148, DECISIONS 2179, EXPERIMENTS 438 |

## Decisions I need from you (defaults in bold)

1. **Names.** `interlude*` config fields become `ranking*` (the arc fields `rankingArc*`; the break fields drop "Break" where it adds nothing:
   `rankingEvery`, `rankingSets`, `rankingSeconds`, ...). Table `interlude_trials` becomes `ranking_sets`. Event/file names `interlude_*` become `ranking_*`.
   Class `InterludeManager` is deleted (its set logic is already in `RankingSets`/`RankingBreak`). The mapping goes into DECISIONS as a glossary.
   Since no participant data exists, **rename the database table and columns outright** (one migration), rather than keeping old names.
2. **The simulator stack** (`sim`, `agents`, `battery`, `results`, `fingerprint`, `analysis`, `plots`, the agent screens, `human_agents`, `agent_inference`) is built around session + Interlude
   evaluation on the old non-tiles ladder. Options: (a) **keep it as the engine for FOR: drop the Interlude evaluation and re-base on tiles worlds (tile_calibration already runs there);
   re-add a ranking evaluation later**, (b) archive it all. Recommend (a), done in its own phase after the C#/data cleanup so it can be paused.
3. **Fixtures `S1`-`S7`/`P`** (frozen non-tiles sessions used as arbitrary test environments): **keep until phase 5**, then replace with a synthetic tiles environment and delete them. The
   non-tiles world generator (`world.py` random placement) stays for now; removing it is a later, separate step.
4. **Old design/analysis scripts for retired experiments** (`rw_*`, `fi_*`, `fn` tests, `interlude.py`, `interlude_design.py`, `ranking_design.py`, `carryover_decay`, `prior_carryover`,
   `idle_analysis` etc.): **delete those tied to a retired experiment; move the generic exploratory ones (`idle`, `gap`) to `archive/` only if they still run**. Git history keeps the rest.
5. **No tutorial in the prototype.** FOR_S1 is the only session; TUT's practice session goes away. (Instructions texts for FOR stay.)

## Order, each phase one commit, tree green at the end

**Phase 0, safety (10 min).** Tag `pre-cleanup`. `db_backup.py`. Confirm Editor is open and `ready`. Leave the font atlas files alone.

**Phase 1, delete the old experiments.**
- Unity (through the CLI, not YAML): delete `Experiments/{TUT,FN,RW,FI}` assets and `StreamingAssets/Experiments/{TUT,FN,RW,FI}`; remove their entries from `ExperimentCatalog` and the Boot/menu
  prerequisites; check `Resources/` and `GameManager.defaultExperiment` point at FOR.
- Python: delete `design/{FN,RW,FI}.py`, `rw_*.py`, `fi_*.py`, `test_{fn,rw,fi}_design.py`, `test_fi_interlude.py`, `test_rw_*`; update `design/__init__.py`, `build_experiment.py`, `run_tests.py` mappings, `test_realization`.
- Server: `server_admin.py` unregisters nothing needed (no data); the catalog only registers FOR at the next `publish`.
- **Checkpoint:** recompile, no console errors; menu shows only FOR; `run_tests.py --fast`; Editor play test of FOR_S1 start (you).

**Phase 2, remove the Interlude session kind from Unity.**
- Delete `InterludeManager.cs` and its scene component (CLI `remove_component`), `isInterlude` branches (GameManager, DataLogger, HarvestManager, HarvestUI, SessionTimerUI, Tree, SunController,
  CameraController, PlayerController, FeedbackAudio, Music, InstructionsPanel, ScoreScreen, RunModes, SessionPreview), `*.interlude.json` loading in `WorldData`, `Interlude` experiment/session pairing in
  `ExperimentConfig` and `ExperimentBuilder`, the inter-session Interlude flow in `GameManager`.
- `RankingBreak` and `RankingSets` become the only ranking code; the arc fields stay (renamed in phase 3).
- **Checkpoint:** recompile, console clean, full session play test of FOR_S1 including two breaks and the end screen (you), `replay.py` on that log.

**Phase 3, rename (config, data, SQL, Python mirrors) in one pass so replay stays consistent.**
- `SessionConfig`: field renames per decision 1 (ScriptableObject renames lose values; FOR_S1 is generated, so rebuild it with `build_experiment.py FOR` rather than `FormerlySerializedAs`). Remove the fields of
  retired modes (`interludeMode`, trial counts, peak/interaction trials, repeats, pair distances, bonus per correct, `isInterlude`, `interludeText` variants not used).
- Data: events (`interlude_*` to `ranking_*`), `interlude_trials.csv` / `interlude_plan.json` to `ranking_sets.csv`, `DataRows`, `FileSink`, `HttpSink`, `ResumeInfo`, handlers.ts.
- SQL: new migration `..._rename_ranking.sql` (rename table/columns, update `server.resume_state`, `run_points`, finish-run checks); the two pending migrations are applied before it, after the backup.
- Python: `rundata`, `human_data`, `replay`, `visibility`, `ranking`, `server_admin`, `test_server`, `test_resume_breaks`, `test_ranking`, `test_replay`, `test_visibility`.
- **Checkpoint:** `run_tests.py --all --fast`; `test_server.py` (needs Deno); a logged run uploads against the local server and the schema; play test, replay (you).

**Phase 4, simulator stack, in the order: `sim` → `agents` → `fingerprint` → `results` → `battery` → `analysis`/`plots` → human scripts** (decision 2). Drop Interlude evaluation and the Interlude episodes/checkpoints from
the schema logic (a results-schema version bump with a migration, copy `results.sqlite` first), re-base tests on a synthetic tiles environment (`synthetic.py`). Replace `S1`-`S7` fixtures (decision 3).
**Checkpoint:** `--all` including slow tests (needs your approval), plus one small `sim.py` run on FOR_S1.

**Phase 5, docs.** CLAUDE.md: remove the Interlude/old-experiment paragraphs, tree entries, regeneration rules (the file shrinks by a third); SCIENCE: FOR becomes the document, the old ladder moves under
"History"; DECISIONS: keep entries (mark superseded), add the rename glossary and a "Cleanup 2026-11" entry; EXPERIMENTS: reduce to the plan for tutorials and later FOR variants; ONLINE_DATA_PLAN, README; memory.

**Phase 6, final.** `run_tests.py --all` (slow tests with approval), clean Editor play test of FOR_S1, `build_experiment.py FOR --remove-stale`, dev WebGL build (ask first), `publish` after your go-ahead.

## Risks

- Scene and asset GUIDs: only CLI edits; delete assets with `delete_asset --confirm true`, then check for missing-script warnings in the scene.
- The deployed database has the old experiments' migrations; no data, but the rename migration must run after the backup and before the new build is published, or old builds break (the server refuses unregistered commits anyway).
- Replay mirrors C# rules; every rename touches `HarvestManager`, `RankingBreak`, `replay.py`, `visibility.py` together, which is why phase 3 is one pass.
- The engine hashes (`ENGINE_FILES`, `AGENT_FILES`) change on any edit: old results in `results/` become stale. Acceptable; say so in the commit message.
- `Unity test` finds no tests; the only Unity-side check is compile plus play test, so each phase ends with a play test from you.
