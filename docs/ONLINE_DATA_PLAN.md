# docs/ONLINE_DATA_PLAN.md — online data collection: protocol and build plan

Rationale and rejected alternatives: `docs/DECISIONS.md` ("Online data collection"). Status: **phases 1 to 5 built (schema, codec, local layout, replay adaptation; server functions, reference client, admin and pull, end-to-end tests; the Unity recorder, sinks, uploader and pause gate; resume; the WebGL build); phase 6 not started.** Phase 2 is **deployed** to the Supabase project `emdgczidpqdhftzujyte` (2026-10-29) and passes `scripts/server_smoke.py` there; the 10 world and Interlude files are registered, no release is (the first real one is registered with the first Unity build). Nothing
below changes task design, reward, visuals or session flow; it changes how a session is recorded, uploaded and resumed.

## 1. Data model (Postgres, separate Supabase project)

All tables are keyed by `run_id` (server-issued, pseudonymous). RLS enabled, no policies for `anon`/`authenticated`: only the
Edge Functions (service role) read or write.

| Table | One row per | Columns (sketch) |
|---|---|---|
| `runs` | participant run | `run_id`, `token_hash`, `platform`, `build_commit`, `build_dirty`, `unity_version`, `started_at`, `finished_at`, `status` |
| `pid_registry` | participant | `prolific_pid`, `run_id` (kept apart from analysis tables) |
| `sessions` | session in a run | `run_id`, `session_index`, `name`, `world_sha256`, `interlude_sha256`, `config` jsonb (the full `SessionConfig`), `display` jsonb, `frame_stats`, `started_at`, `ended_at`, `completed`, `final_score` |
| `events` | event | `run_id`, `session_index`, `seq`, `t`, `real`, `type`, `tree_id`, `k`, `reward`, `running_total`, `payload` jsonb |
| `trajectory` | chunk | `run_id`, `session_index`, `first_seq`, `n_frames`, `t_start`, `t_end`, `data` bytea |
| `interlude_plan` | session | `run_id`, `session_index`, `order` (the shuffled trial list, written at the Interlude's start) |
| `interlude_trials` | trial | the columns of today's `interlude.csv`, plus `run_id`, `session_index`, `seq` |
| `worlds`, `releases` | registered world hash / allowed build commit | filled by a release script, read by `run-start` |

Unique keys make every upload idempotent: `(run_id, session_index, seq)` for `events` and `interlude_trials`, `(run_id,
session_index, first_seq)` for `trajectory`. `harvests` is a derived view/step, not an uploaded table. Event types are today's
(`session_start/end`, `pause/resume`, `harvest_press/release/pause/resume`, `fruit`, `focus_*`, teleports, Interlude trials) plus
`resume` and `upload_pause`/`upload_resume`; the old `note` strings move into `payload`.

## 2. Trajectory chunk format

Built: `scripts/trajectory_codec.py` (the format is in its docstring; `test_trajectory_codec.py` pins it byte for byte with a golden
chunk). Per frame `[t, x, z, yaw, pitch, keys]` quantized (**time 1 microsecond**, x and z 0.01 world units, yaw and pitch 0.02
degrees; the steps are in the chunk header), each column delta-coded against the previous frame, zigzag-varint encoded, then raw
DEFLATE (RFC 1951: .NET's `DeflateStream`; Unity 6 has no `ZLibStream`). The header holds magic, version, frame count, `first_seq`,
the three steps and a CRC32 of the uncompressed bytes. Time is 1 us, not 1 ms, because `replay.verify` re-derives frame-level
harvest decisions from the frame times (DECISIONS has the measurement); on 76 real debug logs the quantized replay verified exactly
as often as the originals, at about 3.5 B/frame. Rounding is half to even (`Math.Round`'s default), so the C# encoder can match.
The C# codec is tested against the golden bytes and a Python-produced fixture in phase 3. Compression in WebGL
(`System.IO.Compression`) must be confirmed early in phase 5.

## 2b. Local layout (the developer mirror), `scripts/rundata.py`

One folder per session, one file per table, the same columns as the database (`events.csv`, `trajectory.csv` of the quantized
values, `interlude_trials.csv`, `interlude_plan.json`, `session.json` = the `sessions` row, `run.json` above them). `rundata.py`
reads and writes it (a cut-short last line is dropped and reported, anything else bad is an error); `replay.load_session_log`
reads it (and still the legacy DataLogger folders: the legacy loader and `convert_legacy.py` are kept only until the old-format tests are rewritten); `convert_legacy.py` turns a legacy folder into it. The
migration is `supabase/migrations/20261029000000_online_data.sql` (parsed with PostgreSQL's own parser, `pglast`; **not yet run
against a database**).

## 3. Upload protocol (built and tested locally)

Three Edge Functions (`supabase/functions/`, Deno, `verify_jwt = false` and an `apikey` header filter as in `evidence_integration`),
all POST with a JSON body, each a thin wrapper (`_shared/handlers.ts`: validation, chunk decoding) over a function of the
unexposed `server` schema (`migrations/20261029000100_online_functions.sql`: authentication, idempotent inserts, gap checks, resume
state), reached over a direct database connection (`SUPABASE_DB_URL`). Errors: 400 `invalid` / `invalid_chunk`, 401 `unauthorized`,
403 `unknown_build` / `unknown_world`, 409 `no_session` / `session_gap` / `gap_events` / `gap_trajectory` / `overlap_trajectory` /
`gap_trials` (the client's sequence numbers disagree with the server: re-sync through `run-start`), 413, 500 `internal`.
- **`run-start`** `{build: {commit, dirty, platform, unity_version}, prolific_pid?}` starts a run, or continues the Prolific ID's run
  with a fresh token (the old one stops working); `{build, run_id, token}` continues an anonymous run the same way. Returns
  `{run_id, token, status, resume}`; a finished run returns its status and no token. A build commit not in `releases` is refused;
  every commit that touches a run is kept in `runs.build_commits`; a dirty build is accepted and flagged.
- **`append`** `{run_id, token, session_index, session?, events?, trajectory?: [base64 chunk], plan?, trials?}` returns
  `{ok, events_next, trajectory_next, trials_next}`. **A 200 means every row of the request is stored** (all or nothing). Repeats of
  stored rows are harmless; a gap, or a chunk that overlaps a stored one without being identical, is a 409. The server decodes
  every chunk itself (checksum, frame count, time order) and takes `first_seq`, the time span and the last frame from it, never from
  the client. A session's first append carries its row (a world or Interlude hash not in `worlds` is a 403); later appends may
  update `ended_at`, `completed`, `final_score`, `frame_stats`, `display` and nothing else. Requests for one run are serialized
  (advisory lock).
- **`run-finish`** `{run_id, token}` returns `{ok, problems}`; with no problems the run is marked finished and accepts nothing more
  (the Prolific code comes with the Prolific step). It checks the session count against `releases.n_sessions`, that each session is
  complete and has a `session_end` event and a trajectory, and that the indices are contiguous.
- **Resume state** (`run-start`'s `resume`, from the rows): `session_index`, `name`, `completed`, `final_score`, `pose` (the last
  frame), `last_event_t`, `running_total`, `fruits_taken` (bush -> count), `open_bout_tree`, `interlude_plan`,
  `interlude_trials_done` and the three `*_next` sequence numbers.
- **Tools:** `scripts/server_client.py` (the reference client, and `upload_session` to push a local-layout session in batches),
  `scripts/server_admin.py` (`register-release`, `register-worlds`, `runs`, `pull` = a run back into the local layout of section 2b).

Still the client's job (phase 3): an `IDataSink` with the three implementations, the in-memory queue with backoff and the
pause-until-acknowledged overlay (grace window in `SessionConfig`), the cadence (events within about 1 s, trajectory every 5 s,
everything on session end and on page unload), and the unload flush for WebGL.

### Deploying (done once for `emdgczidpqdhftzujyte`; repeat after a change)

The CLI is the one in `evidence_integration/task_backend/node_modules/.bin/supabase`; `supabase/config.toml` (from `supabase init`) has
`verify_jwt = false` for the three functions. Facts learned doing it: **no Docker and no database password are needed**: after
`supabase link --project-ref emdgczidpqdhftzujyte` (the CLI is logged in), `db push`, `db query --linked "<sql>"` / `-f file.sql` and
`migration list` reach the database through a temporary login role, and `functions deploy run-start append run-finish --no-verify-jwt
--use-api` bundles on Supabase's side (the `npm:postgres` import and the relative `_shared/` imports both worked). `db push` prints a
harmless "failed to cache migrations catalog ... Docker" warning. Edge Functions get `SUPABASE_DB_URL` and the publishable key from the
platform (the direct connection and the `apikey` check both worked). `ALLOWED_ORIGIN` (optional secret) restricts CORS to the game's
web origin. Worlds are registered by SQL (`db query --linked -f`, the hashes of `Assets/StreamingAssets/Worlds/*`) or with
`server_admin.py register-worlds` (needs `FORAGING_DB_URL`); a release with `register-release --commit <hash> --sessions <n>`
(n = 10: P and S1 to S4, each with its Interlude). **Re-register worlds after regenerating them.** The publishable key is in the
dashboard (API Keys) or `supabase projects api-keys`: that listing also prints the secret keys, so do not paste its output anywhere.

`scripts/server_smoke.py` runs one throwaway run through every endpoint and prints the latency of each call; it needs a release
`smoke-test` with `n_sessions` 1 (register it, run, then `delete from public.runs where build_commit = 'smoke-test'` and delete the
release). First results: all 12 checks pass; the public roles can select, insert or execute nothing and all 9 tables have RLS;
calls took 0.3 to 1.1 s, the slower ones probably cold starts, which the grace window before a pause must tolerate (several seconds).
Supabase's GitHub integration is connected to the repo; whether it deploys on push, and what it would redeploy, has not been
checked (the remote migration history already lists both migrations, so a push should find nothing new).

### Deploying the game (GitHub Pages)

The Unity build is static files; a CI runner cannot make it (it needs your licence), so it is built locally and published as one
fresh commit to a separate Pages repository (`scripts/deploy_webgl.sh`; a build is tens of megabytes of binary that does not delta, so
history would grow by that much per deploy).
1. In `Assets/StreamingAssets/online.json` set `"enabled": true` (the URL and the publishable key are already there; the build refuses
   to run in a browser without it). Registered worlds must match the ones in the build (`server_admin.py register-worlds` again if
   they were regenerated).
2. Commit the code, then register that commit: `server_admin.py register-release --commit <hash> --sessions 10` (or the SQL in the
   walkthrough). A build from a dirty tree is accepted but flagged.
3. Unity: File > Build Profiles (or Build Settings) > WebGL, **not** a development build, scenes `Boot` then `SampleScene` (already the
   list), Player Settings > Publishing > Decompression Fallback **on** (already set in this project), output to e.g. `Builds/web`.
   Switching the Editor to WebGL reimports and the first release build takes several minutes; switch back to Linux afterwards.
4. `scripts/deploy_webgl.sh Builds/web <clone of the Pages repository>`, then run the `git push --force` line it prints, and enable
   Pages for that repository (Settings > Pages > branch, root). The Pages repository can be a separate one (the build files are public,
   the source need not be) or this one: `git clone <url> ~/foraging-pages` and deploy with `--branch gh-pages` (the script refuses a
   Unity project folder and leaves `main` alone; the repository must then be public for free Pages, which also publishes the source).
5. Allow only that origin to call the functions: `supabase secrets set ALLOWED_ORIGIN=https://<user>.github.io` (no path), then test
   the page. `node scripts/webgl_smoke.mjs <build dir> --release --pid X` checks a build locally (patch the copy of `online.json` in the
   build directory to point at a test server).
6. Prolific study URL: `https://<user>.github.io/<repo>/index.html?PROLIFIC_PID={{%PROLIFIC_PID%}}`. The completion code and
   redirect back to Prolific are not built yet (`run-finish` answers `{ok, problems}` only), nor is a consent screen.

### Running the server tests locally (no Docker)

`pip install pgserver "psycopg[binary]"` in `./venv`, and Deno on the PATH (or `FORAGING_DENO=/path/to/deno`; `npm install deno`
gives one). `scripts/test_server.py` then starts a private PostgreSQL 16, applies the migrations and runs the functions with
`supabase/local/serve.ts`; without them the file is skipped. `deno test supabase/functions/_shared/chunk_test.ts` checks the
TypeScript chunk decoder against the Python golden chunk.

## 4. Resume (built and tested)

**Who resumes:** a participant who comes back with a Prolific ID the server knows (`-pid <id>` now; the URL parameter in the browser
build). Each such `run-start` gets a fresh token (the old one stops working), `has_resume` and the server's `resume` state. A run
started without an ID cannot be resumed (there is no way yet to say it is the same person; a stored token for the browser build is
a later option). A finished run gets a notice and no token.

**The state** (`server.resume_state`, migration `20261030000000`): the latest session's index, name, kind and `completed`; `pose` (the
last stored frame); `clock` (later than every stored frame and event: the session clock to continue from); `running_total`;
`fruits_taken` (bush, count; the k-th fruit pays the pre-drawn reward); `open_bout_tree` (-1 if none); the Interlude's `interlude_plan`
and `trial_rows` (finished trials: correct, bonus); `previous` (completed sessions and scores) and `previous_interlude` (totals over
completed non-practice Interludes), for the running totals on the final screen; `gap_seconds` (server clock, from the new
`received_at` columns); `started_at`; and the three `*_next` sequence numbers. It is flat (no nulls) so JsonUtility reads it.

**The client** (`DataPipeline`, `DataLogger`, `ResumeInfo`): when `run-start` returns a resume the pipeline restores the running
totals, drops what the loaded scene recorded (`SceneSuperseded`: the scene was started for session 0 before the server answered),
and reloads the scene for the session to continue: the next one when the latest is `completed` (a normal start, its `session_start`
carries `resumed_run`), the same one otherwise. In the same session the logger continues the sequence numbers and the clock, logs a
`session_resume` event (payload: `gap_s`, `stale_s`, `open_bout_tree`, `frames_held`, `has_pose`) before anything else, and two frames
later puts the player at the last pose and view, takes the fruits already taken off their bushes (which ones is not recorded: the
first n; a bush left with none turns spent), sets the score and sets the sun's clock; the Interlude takes its order from the plan,
restarts at its first unfinished trial and counts the finished trials again. The participant sees "Welcome back"
(`StreamingAssets/instructions_resume.txt`) and presses Enter. If every session is already complete the pipeline calls `run-finish`
and shows a notice. After the last session's end screen, Enter calls `run-finish` once everything is stored (`TryFinish`).
The local copy continues too: `FileSink.PrepareResume` cuts the local files back to the rows the server holds before appending.

**What a resume does not restore:** an open harvest bout and the progress on the fruit being picked (they start over; the bout is
named in the event), the view of an Interlude trial in progress (the trial restarts), which individual fruits were taken. The
frame statistics of a resumed session count only its later frames. An abandoned session (Escape, or the Editor stopped) logs a
`session_end` with `completed` false; if it is later resumed, its events continue after that `session_end`.

**Replay and analysis:** a `session_resume` event is a discontinuity. `replay.py` starts the harvest state empty at the first frame
after it, takes the fruit counts and total from the logged events (the fruits of the gap, after the last uploaded frame and up to the
resume, have no frames and are only in the log), and `verify` leaves the events of the gap out. The clock `t` stays monotone; the
trajectory has no frames in the gap. Limits on the gap and the number of resumes are still deferred: `gap_seconds`, `gap_s` and the
count of `session_resume` events are what to apply them to.

## 5. Phases (each ends with a verification; commit points are the PI's)

0. **Prerequisites (PI):** create the separate Supabase project, `supabase link` from the repo (a new top-level `supabase/`
   directory); keys stay out of git. Decide where the release registry is edited.
1. **Schema and codec (Python only). Done.** Migration, codec and tests, local layout with reader, writer and legacy converter,
   `replay.py` and `visibility.py` reading the online layout (`fields(event)` replaces the `note` parsing). Not done: the `pull`
   script from the database (needs phase 2's server; it will write this same layout). *Verified:* `scripts/run_tests.py --fast`
   (97 passed); 76 real debug logs verify as before after quantization; the SQL parses.
2. **Server. Done locally.** Functions, release/world registry, reference client, admin and pull. There is no Docker here, so the
   tests run a real PostgreSQL 16 (`pgserver`) and the real functions under Deno instead of `supabase start`. *Verified* (20 tests in
   `test_server.py`): idempotent repeats, gaps, overlaps, damaged chunks, all-or-nothing requests, concurrent duplicate uploads, token
   rotation, resume state against known events, finish, and a session uploaded in batches then pulled back equal to the original.
   The public roles (`anon`, `authenticated`, created in the test database) are refused every table and every `server` function. Not verified: Supabase's own role setup and everything on a real project.
3. **Client recorder. Done (2026-10-29).** `DataLogger` records rows and batches them (events within a second; trajectory every 5 s
   online, every second offline) to `DataPipeline`, which owns a `FileSink` (the local layout, always) and an `HttpSink` (the queue,
   one request in flight, backoff on network errors and 5xx, a 4xx stops uploading with a message), starts the run (`run-start`), and
   gates the game with `PauseGate` (the only writer of `Time.timeScale`; `pause` events carry a `reason`: `instructions`, `upload`,
   `instructions+upload`; this replaces the planned `upload_pause`/`upload_resume` event types). Leaving a session's end screen and
   quitting wait for the drain. The Interlude's shuffled order is logged (`interlude_plan`) and its trials go through the logger.
   `harvests.csv` and `manifest.json` are gone (derived / replaced by the session row); `note` strings became JSON payloads.
   `online.json` in `StreamingAssets` (`enabled`, `url`, `apikey`, `uploadInEditor`; committed with `enabled: false`) or `-onlineUrl` /
   `-onlineKey` / `-pid` on the command line turn uploading on. *Verified:* the C# codec decodes Python's chunks and Python decodes C#'s
   (the golden chunk re-encodes to identical bytes); a Linux standalone build on a private Xvfb display wrote the local layout, `scripts/rundata.py`
   read it and `replay.py` verified it; the same build uploaded a run to the real Supabase project and the stored rows (events,
   decoded trajectory, plan, trial, session rows with completion) equal the local copy; against a local server frozen with SIGSTOP in the
   middle of a session the game paused on "Saving your data..." and, when the server thawed, resumed with nothing lost (the DB equals
   the local files); a build whose commit is not registered shows the refusal; a wrong server shows "Connecting...". Not verified:
   no resume (phase 4), mouse and keyboard play (only the instruction and end screens were driven), WebGL, a participant who closes
   the window mid-upload on Windows.
4. **Resume. Done (2026-10-30).** Server state, client restore, replay and the finish call (section 4). *Verified* with a Linux build on
   a private display against a local server, killing the build with SIGKILL as a crash: a session killed 9 s in (last frames 3.5 s
   stale) came back at the right clock (the countdown continued), the data is continuous (sequence numbers, monotone `t`, the DB equal
   to the local copy, replay verifies); a session boundary resume starts the next session normally; an Interlude killed in its second
   trial came back with the same trial order, restarted that trial and went on to the third (the trial rows continue); a run injected
   with fruits and a pose came back with the score restored (36), the bush spent, and the player at the bush facing it; a run whose
   sessions were all complete was closed with `run-finish` and showed a notice, as did a finished one. Not verified: the Enter on the
   last real end screen (`TryFinish`; only its `run-finish` call was exercised, through the all-complete path), a resume on another computer,
   a resume with Space held, WebGL.
5. **WebGL port. Built (2026-10-30); needs your real-browser check.** A new first scene, `Boot` (`Bootstrap`), fetches every file in
   StreamingAssets into memory (`StreamingData`, driven by `streaming_files.txt`, which `BuildInfoWriter` writes before each build),
   waits for a click (the gesture that starts pointer lock, audio and fullscreen) and loads the game scene; on desktop it hands over at
   once, and playing `SampleScene` in the Editor skips it as before. In a browser: no local copy (`FileSink` is skipped; without a
   server the game says so), no command line (`?PROLIFIC_PID=` or `?pid=` in the address; `?onlineUrl=`/`?onlineKey=` only in a
   development build), no world archive, request timeouts by `Abort` (UnityWebRequest's own timeout is not honoured), and a
   `PointerLockGuard` that holds the game behind "Click to continue" whenever the mouse capture is released (Escape). *Verified in
   headless Chromium with software GL (`scripts/webgl_smoke.mjs`):* a development build and a release build load, fetch the files,
   show the click prompt, load the game scene, run the practice session (timer, terrain, fruit, instruction and end screens), go on
   to the Interlude, and upload to the server as `WebGLPlayer` (events, trajectory, plan, a resume with `session_resume`); the release
   build was served **without** `Content-Encoding` headers, as GitHub Pages does, and loaded through Unity's decompression fallback.
   *Sizes (release):* `.data` 12.8 MB, `.wasm` 8.4 MB, framework 78 KB, loader 118 KB (compressed), StreamingAssets about 20 MB raw
   (the five worlds compress about 2.4x): about 41 MB, no file near GitHub's 100 MB limit. *Not verified, needs a real browser:* pointer
   lock and Escape, fullscreen, audio after the click, mouse feel (the look sensitivity may need recalibrating), frame rate and
   timing, Safari and Firefox, a low-memory laptop, closing the tab mid-upload (no unload flush was built; the last second of
   events and five seconds of frames may be lost, and resume covers it). Headless Chromium cannot take pointer lock.
6. **Cleanup and docs.** Delete the old `ForagingData/` debug folders (PI approved, after phase 3), rewrite CLAUDE.md "Data logging"
   and `docs/SCIENCE.md` "Data", `/adversarial-review` before each commit, restore the design session durations (currently a
   temporary 15 s). Prolific integration (code, redirect, `PROLIFIC_PID`, returning-participant check) follows this plan.

## 6. Open items

- Yaw/pitch quantization step: derive from `lookDegreesPerCount` x `lookSensitivity` (the PI accepted "no coarser than one count").
- Grace window length before a pause (a `SessionConfig` field).
- Resume limits (maximum gap, number of resumes): deferred, set from pilot experience.
- Consent screen, participant-ID entry for the non-Prolific path, minimum-performance gate for the browser: before the first pilot.
- Where the release script runs and who registers world hashes and commits.
