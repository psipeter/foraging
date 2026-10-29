"""Smoke test of a deployed online data server: one throwaway run through every endpoint, with the checks the local tests make
(idempotent repeat, 401/409/400 cases, resume state, finish) and the latency of each call. It writes rows under the build commit
given by --commit, which must be registered in `releases` with n_sessions 1 and be deleted afterwards (the printed SQL does it).

    FORAGING_API_KEY=<publishable key> ./venv/bin/python scripts/server_smoke.py --url https://<ref>.supabase.co/functions/v1 \\
        --commit smoke-test --world-sha <sha256 of a registered world file>
"""

import argparse
import base64
import os
import sys
import time

import numpy as np

import trajectory_codec as codec
from server_client import Client, ServerError, event_rows

failures = []


def check(name, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {name}{(' - ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


def timed(label, call, timings):
    start = time.perf_counter()
    try:
        return call()
    finally:
        timings.append((label, (time.perf_counter() - start) * 1000))


def refused(call, status, code):
    try:
        call()
    except ServerError as e:
        return e.status == status and e.code == code
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", required=True)
    parser.add_argument("--commit", default="smoke-test")
    parser.add_argument("--world-sha", required=True)
    args = parser.parse_args()
    key = os.environ.get("FORAGING_API_KEY")
    if not key:
        sys.exit("set FORAGING_API_KEY to the project's publishable key")

    t = []
    build = {"commit": args.commit, "dirty": False, "platform": "SmokeTest", "unity_version": "none"}
    c = Client(args.url, key, build, timeout=30)
    rng = np.random.default_rng(1)
    n = 400
    frames = np.c_[(np.arange(n) + 1) * 0.0083333, np.cumsum(rng.normal(0, 0.05, n)) + 100, np.cumsum(rng.normal(0, 0.05, n)) + 50,
                   np.cumsum(rng.normal(0, 0.3, n)), rng.normal(0, 2, n), rng.integers(0, 8, n)]
    row = {"name": "Smoke", "config": {"smoke": True}, "world_file": "smoke.world", "world_sha256": args.world_sha, "world_seed": 0}
    events = event_rows([{"t": 0.0, "real": 0.0, "type": "session_start"},
                         {"t": 1.0, "real": 1.0, "type": "fruit", "tree_id": 3, "k": 0, "reward": 2.0, "running_total": 2.0},
                         {"t": 1.5, "real": 1.5, "type": "harvest_press", "tree_id": 4}])

    print("endpoints")
    check("wrong api key refused", refused(lambda: Client(args.url, "wrong", build).start(), 401, "unauthorized"))
    check("unregistered build refused", refused(lambda: Client(args.url, key, {**build, "commit": "not-registered"}).start(), 403, "unknown_build"))
    started = timed("run-start", lambda: c.start(prolific_pid="SMOKE_TEST"), t)
    check("run starts with a token", started["status"] == "in_progress" and bool(started["token"]) and started["resume"] is None)
    ack = timed("append (session, events, 400 frames)", lambda: c.append(0, session=row, events=events, frames=frames), t)
    check("append acknowledges every stream", ack["events_next"] == 3 and ack["trajectory_next"] == n, ack)
    again = timed("append (exact repeat)", lambda: c.append(0, session=row, events=events, frames=frames), t)
    check("a repeat changes nothing", again == ack, again)
    check("a gap is a 409", refused(lambda: c.append(0, events=event_rows([{"t": 2.0, "type": "pause"}], first_seq=9)), 409, "gap_events"))
    check("an unregistered world is a 403", refused(lambda: c.append(1, session={**row, "world_sha256": "f" * 64}), 403, "unknown_world"))
    bad = bytearray(codec.encode(frames[:50], n))
    bad[50] ^= 1
    check("a damaged chunk is a 400", refused(lambda: c.append_chunks(0, chunks=[base64.b64encode(bytes(bad)).decode()]), 400, "invalid_chunk"))
    old = c.token
    state = timed("run-start (returning ID)", lambda: c.start(prolific_pid="SMOKE_TEST"), t)["resume"]
    q = codec.quantize(frames)[-1]
    check("resume state is right", state["fruits_taken"] == [{"tree": 3, "n": 1}] and state["open_bout_tree"] == 4 and state["running_total"] == 2.0
          and state["trajectory_next"] == n and state["events_next"] == 3 and abs(state["pose"]["x"] - q[1]) < 1e-9, state)
    stale = Client(args.url, key, build)
    stale.run_id, stale.token = c.run_id, old
    check("the old token stopped working", refused(lambda: stale.append(0, events=event_rows([{"t": 3.0, "type": "x"}], first_seq=3)), 401, "unauthorized"))
    check("finish lists what is missing", timed("run-finish (incomplete)", c.finish, t)["ok"] is False)
    timed("append (session end)", lambda: c.append(0, session={**row, "completed": True, "ended_at": "2026-10-29T12:00:00Z", "final_score": 2.0},
                                                   events=event_rows([{"t": 2.0, "type": "session_end", "running_total": 2.0}], first_seq=3)), t)
    result = timed("run-finish (complete)", c.finish, t)
    check("finish accepts a complete run", result == {"ok": True, "problems": []}, result)

    print("latency (ms)")
    for label, ms in t:
        print(f"  {ms:7.0f}  {label}")
    print(f"run {c.run_id}")
    print("delete the rows afterwards: delete from public.runs where build_commit = '%s';" % args.commit)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
