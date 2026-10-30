"""Load test of a deployed online data server: N simulated participants, each playing one session of a given length in real time
and uploading the way the game does (events about every second, a trajectory chunk of 5 s of frames every fifth second), then
finishing the run. It reports the latency of every call and how many calls were slower than the game's grace window
(`SessionConfig.uploadGraceSeconds`, 4 s: past it a participant would see the game held still behind "Saving your data...").

It writes rows under the build commit given by --commit, which must be registered in `releases` (the printed SQL registers it and
deletes the rows afterwards) and uses a registered world's hash. Run it against a local server first (`supabase/local/serve.ts`,
see docs/ONLINE_DATA_PLAN.md) and against the project only with a number of participants you are happy to load it with.

    FORAGING_API_KEY=<publishable key> ./venv/bin/python scripts/load_test.py --url https://<ref>.supabase.co/functions/v1 \\
        --commit load-test --participants 20 --seconds 60 --ramp 20
"""

import argparse
import hashlib
import os
import statistics
import sys
import threading
import time
from pathlib import Path

import numpy as np

from server_client import Client, ServerError, event_rows

FPS = 90
CHUNK_SECONDS = 5
GRACE = 4.0
WORLD = Path(__file__).resolve().parent.parent / "Assets" / "StreamingAssets" / "Worlds" / "S1_seed1.world"

lock = threading.Lock()
timings = {}          # endpoint -> [ms]
errors = {}           # "endpoint status code" -> count
retries = [0]


def record(label, ms):
    with lock:
        timings.setdefault(label, []).append(ms)


def call(label, fn, attempts=4):
    """One request as the game makes it: retried (with backoff) on a failure; every attempt's time and error is recorded."""
    for attempt in range(attempts):
        start = time.perf_counter()
        try:
            result = fn()
            record(label, (time.perf_counter() - start) * 1000)
            return result
        except ServerError as e:
            record(label, (time.perf_counter() - start) * 1000)
            with lock:
                key = f"{label} {e.status} {e.code}"
                errors[key] = errors.get(key, 0) + 1
            if e.status < 500:
                return None
        except Exception as e:                      # timeouts and dropped connections
            record(label, (time.perf_counter() - start) * 1000)
            with lock:
                key = f"{label} {type(e).__name__}"
                errors[key] = errors.get(key, 0) + 1
        with lock:
            retries[0] += 1
        time.sleep(min(2 ** attempt, 8))
    return None


def participant(index, args, key, world_sha, start_delay):
    time.sleep(start_delay)
    build = {"commit": args.commit, "dirty": False, "platform": "LoadTest", "unity_version": "none"}
    client = Client(args.url, key, build, timeout=30)
    rng = np.random.default_rng(index)
    if call("run-start", lambda: client.start(prolific_pid=f"LOAD_{args.commit}_{index:04d}",
                                              consent={"version": "load-test", "signature": "Load Test", "at": "2026-10-31T00:00:00Z"})) is None:
        return
    row = {"name": "Load", "config": {"load_test": True}, "world_file": WORLD.name, "world_sha256": world_sha, "world_seed": 1}
    seq_events = seq_frames = 0
    x = z = yaw = 0.0
    pending = []                                    # frames of the current chunk
    t0 = time.perf_counter()
    for tick in range(int(args.seconds)):
        time.sleep(max(0.0, t0 + tick + 1 - time.perf_counter()))
        events = [{"t": tick + 0.2, "real": tick + 0.2, "type": "fruit", "tree_id": int(rng.integers(0, 600)), "k": 0, "reward": 2.0, "running_total": 2.0 * tick},
                  {"t": tick + 0.5, "real": tick + 0.5, "type": "harvest_press", "tree_id": int(rng.integers(0, 600))},
                  {"t": tick + 0.9, "real": tick + 0.9, "type": "harvest_release", "tree_id": int(rng.integers(0, 600))}]
        if tick == 0:
            events.insert(0, {"t": 0.0, "real": 0.0, "type": "session_start"})
        step = rng.normal(0, 0.05, (FPS, 2)).cumsum(axis=0)
        frames = np.c_[tick + (np.arange(FPS) + 1) / FPS, x + step[:, 0] + 100, z + step[:, 1] + 50,
                       yaw + rng.normal(0, 0.3, FPS).cumsum(), rng.normal(0, 2, FPS), rng.integers(0, 8, FPS)]
        pending.append(frames)
        flush = (tick + 1) % CHUNK_SECONDS == 0 or tick == int(args.seconds) - 1
        rows = event_rows(events, first_seq=seq_events)
        body_frames = np.vstack(pending) if flush else None
        ok = call("append", lambda: client.append(0, session=row if tick == 0 else None, events=rows, frames=body_frames, first_seq=seq_frames))
        if ok is None:
            return
        seq_events += len(rows)
        if flush:
            seq_frames += len(body_frames)
            pending = []
    end = {**row, "completed": True, "ended_at": "2026-10-31T00:10:00Z", "final_score": 1.0}
    call("append", lambda: client.append(0, session=end, events=event_rows([{"t": args.seconds, "type": "session_end", "running_total": 1.0}], first_seq=seq_events)))
    call("run-finish", client.finish)


def percentile(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", required=True)
    parser.add_argument("--commit", default="load-test")
    parser.add_argument("--participants", type=int, default=10)
    parser.add_argument("--seconds", type=int, default=60, help="session length each participant plays, in real time")
    parser.add_argument("--ramp", type=float, default=10.0, help="seconds over which the participants arrive")
    parser.add_argument("--world", default=str(WORLD), help="a registered world file (its sha256 is sent)")
    args = parser.parse_args()
    key = os.environ.get("FORAGING_API_KEY")
    if not key:
        sys.exit("set FORAGING_API_KEY to the project's publishable key")
    world_sha = hashlib.sha256(Path(args.world).read_bytes()).hexdigest()
    print(f"{args.participants} participants, {args.seconds} s each, arriving over {args.ramp} s, commit {args.commit}")
    threads = [threading.Thread(target=participant, args=(i, args, key, world_sha, args.ramp * i / max(1, args.participants)))
               for i in range(args.participants)]
    start = time.perf_counter()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    print(f"done in {time.perf_counter() - start:.0f} s")
    print(f"{'call':12} {'n':>6} {'p50':>7} {'p95':>7} {'p99':>7} {'max':>7}  (ms)   slower than the {GRACE:.0f} s grace window")
    slow = 0
    for label, values in sorted(timings.items()):
        over = sum(v > GRACE * 1000 for v in values)
        slow += over
        print(f"{label:12} {len(values):6d} {statistics.median(values):7.0f} {percentile(values, 95):7.0f} {percentile(values, 99):7.0f} {max(values):7.0f}"
              f"   {over}")
    print(f"retries {retries[0]}; errors {errors or 'none'}")
    print("clean up: delete from public.runs where build_commit = '%s'; delete from public.releases where build_commit = '%s';" % (args.commit, args.commit))
    sys.exit(1 if errors or slow else 0)


if __name__ == "__main__":
    main()
