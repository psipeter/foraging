# Adversarial review rounds, 2026-10-30 (online data stack, WebGL/consent flow, participant UI, replay tooling, re-balance)

Full reports (simplifier.md, red-team.md per round) were written to the session scratchpad, which is wiped; this file keeps what matters.
Nothing here is committed. State of the working tree at the end of the day: all of the changes below are applied except the "Waiting for you" list.

## Applied today (with the person's approval)
- **Round 1 (server, upload, resume):** held-buffer, retry-loop, `Decode`, `ResumeReply` and other dead code removed (about -300 lines); migrations squashed to two and the live history repaired; `start_run` takes the run's advisory lock (RT-1, a second tab could lose events); finished run returns the completion code from `run-start` (RT-2); anonymous token resume removed.
- **Round 2 (WebGL input/pause, consent):** invariant culture for the consent time (browser language could block `run-start`); "Paused" overlay below the data overlay (4900 < 5000) so the completion code stays readable; Enter ignored while "Paused"; malformed `?PROLIFIC_PID=` stays editable; small simplifier batch, `UiStyle.MessageScreen`/consent helpers.
- **Round 3 (participant UI, replay tooling):** simplifier batch for UI (instruction files written as displayed, `GameManager` counting helper, points kept in `InterludeManager.Points`, `HudWidgets` folded into `UiStyle`, timer as a number); interlude points only on the final screen except the practice Interlude, which shows what it would have earned and pays nothing; desktop Escape quit accepted; legacy loader and `convert_legacy.py` removed; replay tie rule (logged fruit decides within 1e-5 s), last-two-frames release, resume-Interlude guard, `pull_run` archives world files; `run_tests.py` dependencies derived from imports; `test_world.py` follows the assets. Replay verify: 33 of 33 real browser sessions pass (22 of 23 with fruits failed before).
- **Not built yet / not deployed:** none of the C# changes are in a build; the live build is still c8ad5ec. Server, database and functions changes ARE live.

## Waiting for you (suggested, not applied)
Re-balance review (your other session's reward-weight changes; mechanics are sound: worlds and Interludes match the generators, all tests pass):
- RT-1 (low): mark the SCIENCE.md "Current baselines" (`newterrain-floor-100`, around line 582) and the `s1-90s-learning` table as stale where they appear, not only in one sentence near line 429.
- RT-2 (low): SCIENCE.md ~429 and the newest DECISIONS entry say the weight-specific tests still need updating; they are already updated.
- RT-3 (low): `test_interlude.py:229` swaps one hard-coded threshold (0.25) for another (0.15) with a wrong comment; the generator's floor is 0.3 x scale (0.252 for S3, 0.204 for S4). One line: `>= 0.3 * sidecar["scale"] - 1e-9`.
- RT-4 (info): the Interlude tie tolerance (0.05) is absolute points per fruit; it does not scale with `rewardStd` or the spread of R. Decide if it should.
- RT-5 (nit): quoted statistics from other steps/seeds (DECISIONS spread "0.66/0.57" is now 0.87 for S3 and 0.70 for S4; S2 mean 1.95 over 20 seeds vs 2.0; SCIENCE:459 old moisture spreads; tree counts 686-695 vs 692-701).
- RT-6 (nit): C# defaults/fallbacks for `rewardFeedbackMax` are still 6 (SessionConfig.cs:130, HarvestUI.cs:115, FeedbackAudio.cs:61); every asset says 4.
- Known-and-deferred item "every S1/S2 Interlude has one free either trial" only holds in designed mode; all five assets use random mode (no either trials).
- All 29 stored simulation environments are now stale for these sessions (not wrong); a default query will not pick them up. Do not re-run baselines unprompted.

Declined or left for you from earlier rounds:
- Round 2 SM-14: drop the 1.3 s relock cooldown (-11 lines), only after a Chrome and Firefox test (Escape, click immediately: no pop-up, next click resumes).
- Round 2 SM-15 (one cached `OnlineSettings.Current`, readability only), SM-16 (fix `patch_webgl_page.py` size to constants, -9 lines, removes `--width/--height`), SM-17 (keep the 15 s quit timer; I would), SM-18 (a pause records its reason only when it starts: decide with the analysis plan).
- Round 3 replay: SM-12 (remove `replay.steps`, about -165 lines with SM-13) and SM-13 (drop `server_smoke.py`; I would keep it); `load_test.py` exits 1 even when a retry recovered; `webgl_smoke.mjs` never fails; RT-5 `FORAGING_DENO` is not set in the shell, so `run_tests.py --all` silently skips the 23 server tests.
- Round 3 UI: "This harvest earned 1 points" (declined: plural ignored); SM-12 end screen as one block (premise false, already a centred layout).
- Possible Known-and-deferred additions: run-finish racing the final batch if Enter is pressed in the exact last-session frame (no data lost, no code withheld).
- Simulator and agents (topic 8): not reviewed again; only `visibility.py` changed since the last review (commit 553e37d).

## Before the next deploy
1. Playtest in a browser: Finnish-language browser reaches the game (consent time); malformed `?PROLIFIC_PID=` is editable; Escape on the completion screen shows the code; Enter does nothing behind "Paused"; the "Hold [Space] to harvest" hint and practice controls line; the practice Interlude end screen shows "+x points"; other Interlude end screens show no points; the final screen shows "This interlude: +y points" and the total; the "saving", "connecting" and pointer-lock screens after the `UiStyle.MessageScreen` change.
2. Commit the assets and regenerated worlds first (a pulled run's world files are archived from git at the build commit), then `scripts/server_admin.py register-worlds` and `register-release --commit <new> --sessions 10` (the server refuses unregistered world hashes and commits).
3. Feedback field (added 2026-11-02): apply `supabase/migrations/20261102000000_feedback.sql` to the live database, `supabase functions deploy feedback --no-verify-jwt`, then check in a browser that the final screen shows the box, a click does not re-capture the mouse, Send stores the text (`select * from public.feedback`), and "Return to Prolific" works. Ask before deploying.
4. Replace `consent.txt` (placeholder; it also says "about 30 minutes" where the design is about 15-18) with the IRB text and bump `version:`.
