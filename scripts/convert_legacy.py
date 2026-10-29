"""Convert a legacy session folder (the Unity DataLogger's trajectory/events/harvests/manifest.json) to the online layout
of rundata.py, so old logs and the new tools meet: the trajectory goes through the codec's quantization (what the server
would hold), each event's `note` string becomes a `payload`. Used to check the online layout against real logs until the
Unity recorder writes it directly (docs/ONLINE_DATA_PLAN.md, phase 3); not needed after that.

    ./venv/bin/python scripts/convert_legacy.py <session folder or id> <out root> [--run-id ID] [--session-index N]
"""

import argparse
import csv
import io
import json
import uuid
from pathlib import Path

import replay
import rundata


def _value(text):
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def note_to_payload(note):
    """'x=1;z=2.5;policy=Hide' -> {'x': 1, 'z': 2.5, 'policy': 'Hide'}"""
    return {key: _value(value) for key, value in replay.parse_note(note).items()}


def convert(folder, root, run_id=None, session_index=0):
    folder = Path(folder)
    m = json.loads((folder / "manifest.json").read_text())
    traj, _ = replay._read_trajectory(folder / "trajectory.csv")
    legacy_events, _ = replay._read_events(folder / "events.csv")
    events = [dict({k: v for k, v in e.items() if k != "note"}, payload=note_to_payload(e["note"])) for e in legacy_events]
    trials = None
    if (folder / "interlude.csv").exists():
        text, _ = rundata._complete_lines((folder / "interlude.csv").read_text())
        trials = [rundata._trial(dict(row, seq=str(i))) for i, row in enumerate(csv.DictReader(io.StringIO(text, newline="")))]
    w = m["world"]
    session = {
        "name": m["sessionName"], "is_practice": m["isPractice"], "is_interlude": m["isInterlude"],
        "world_seed": w["seed"], "world_file": w["file"], "world_sha256": w["sha256"],
        "interlude_file": w.get("interludeFile"), "interlude_sha256": w.get("interludeSha256"),
        "config": m["config"], "camera": m["camera"], "display": m["display"], "frame_stats": m["frames"],
        "started_at": m["startedAtUtc"], "ended_at": m["endedAtUtc"], "completed": m["completed"], "final_score": m["finalScore"]}
    run_id = run_id or str(uuid.uuid4())
    if not (Path(root) / run_id / "run.json").exists():
        rundata.write_run(root, run_id, {"platform": m["build"]["platform"], "build_commit": m["build"]["commit"],
                                         "build_dirty": m["build"]["dirty"], "unity_version": m["build"]["unityVersion"]})
    return rundata.write_session(root, run_id, session_index, session, traj, events, trials=trials)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("session")
    parser.add_argument("out")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--session-index", type=int, default=0)
    args = parser.parse_args()
    folder = Path(args.session)
    folder = folder if folder.exists() else replay.DATA_DIR / args.session
    print(convert(folder, args.out, args.run_id, args.session_index))


if __name__ == "__main__":
    main()
