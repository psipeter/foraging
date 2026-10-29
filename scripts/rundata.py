"""The local layout of a run's data, one-to-one with the database tables (docs/ONLINE_DATA_PLAN.md, sections 1 and 3).

    <root>/<run_id>/run.json                       the `runs` row (platform, build, ...)
    <root>/<run_id>/<session_index:02d>/
        session.json                               the `sessions` row (config, world hashes, camera, display, score, ...)
        events.csv                                 seq,t,real,type,tree_id,k,reward,running_total,payload
        trajectory.csv                             seq,t,x,z,yaw,pitch,keys   (the quantized values the server would hold)
        interlude_plan.json                        {"trial_order": [...]}     (Interludes only)
        interlude_trials.csv                       seq + the columns of the `interlude_trials` table

The Editor and standalone builds write this as the developer mirror of what an online build uploads; `read_session`
returns the same structures whether the rows came from here or from the database. Missing numbers are empty cells
(tree_id and k use -1 in memory, reward and running_total NaN). This module does not import replay.py.
"""

import csv
import io
import json
import math
from pathlib import Path

import numpy as np

import trajectory_codec as codec

EVENT_COLUMNS = ("seq", "t", "real", "type", "tree_id", "k", "reward", "running_total", "payload")
TRAJECTORY_COLUMNS = ("seq", "t", "x", "z", "yaw", "pitch", "keys")
INTERLUDE_COLUMNS = (
    "seq", "presented_order", "trial_index", "type", "varied_feature", "stage_x", "stage_z",
    "left_id", "left_shape", "left_color", "left_moisture", "left_value",
    "right_id", "right_shape", "right_color", "right_moisture", "right_value",
    "correct_side", "choice", "choice_correct", "timed_out", "response_time", "first_harvest_time", "first_harvest_side",
    "left_fruits", "right_fruits", "bonus", "locked_at")
_INTEGER = {"presented_order", "trial_index", "left_id", "right_id", "choice_correct", "timed_out", "left_fruits", "right_fruits"}
_TEXT = {"type", "varied_feature", "correct_side", "choice", "first_harvest_side"}


def session_dir(root, run_id, session_index):
    return Path(root) / str(run_id) / f"{session_index:02d}"


def _number(value):
    """'' -> None, otherwise float."""
    return float(value) if value != "" else None


def _cell(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if isinstance(value, float):
        return format(value, ".10g")
    return value


def _complete_lines(text):
    """(text without a last line that was cut short, whether one was cut): a crash can end a file mid-line."""
    cut = bool(text) and not text.endswith("\n")
    return (text[:text.rfind("\n") + 1] if cut else text), cut


def _read_rows(path, columns, parse):
    """Rows of a CSV with this header, parsed by `parse(row_dict)`. Only a last line cut by a crash may be bad: it is
    dropped and reported (second return value); a bad line anywhere else raises ValueError."""
    text, cut = _complete_lines(Path(path).read_text())
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, None)
    if tuple(header or ()) != tuple(columns):
        raise ValueError(f"{path}: header {header} is not {list(columns)}")
    rows = list(reader)
    out, truncated = [], cut
    for i, row in enumerate(rows):
        try:
            if len(row) != len(columns):
                raise ValueError("short or long row")
            out.append(parse(dict(zip(columns, row))))
        except (ValueError, TypeError, KeyError):
            if i != len(rows) - 1:
                raise ValueError(f"{path}: bad row {i + 2}: {row}")
            truncated = True
    return out, truncated


def _event(row):
    return {
        "seq": int(row["seq"]), "t": float(row["t"]), "real": float(row["real"]) if row["real"] else math.nan,
        "type": row["type"],
        "tree_id": int(row["tree_id"]) if row["tree_id"] else -1,
        "k": int(row["k"]) if row["k"] else -1,
        "reward": float(row["reward"]) if row["reward"] else math.nan,
        "running_total": float(row["running_total"]) if row["running_total"] else math.nan,
        "payload": json.loads(row["payload"]) if row["payload"] else {},
    }


def _trial(row):
    out = {}
    for name, value in row.items():
        if name in _TEXT:
            out[name] = value
        elif name == "seq" or name in _INTEGER:
            out[name] = int(value) if value != "" else None
        else:
            out[name] = _number(value)
    return out


def write_run(root, run_id, run):
    folder = Path(root) / str(run_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text(json.dumps(run, indent=2, sort_keys=True))
    return folder


def write_session(root, run_id, session_index, session, traj, events, plan=None, trials=None, steps=codec.DEFAULT_STEPS):
    """Write one session. `traj` is (n, 6) t, x, z, yaw, pitch, keys (it is quantized, as it would be on the server),
    `events` a list of dicts (t, type and optionally real, tree_id, k, reward, running_total, payload), `plan` the
    shuffled Interlude trial order, `trials` Interlude trial dicts. `seq` is the position in the list."""
    folder = session_dir(root, run_id, session_index)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "session.json").write_text(json.dumps(dict(session, run_id=str(run_id), session_index=session_index), indent=2, sort_keys=True))

    with open(folder / "events.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(EVENT_COLUMNS)
        for seq, e in enumerate(events):
            payload = e.get("payload") or {}
            w.writerow([seq, _cell(float(e["t"])), _cell(float(e.get("real", math.nan))), e["type"],
                        _cell(e.get("tree_id", -1) if e.get("tree_id", -1) >= 0 else None),
                        _cell(e.get("k", -1) if e.get("k", -1) >= 0 else None),
                        _cell(float(e.get("reward", math.nan))), _cell(float(e.get("running_total", math.nan))),
                        json.dumps(payload, separators=(",", ":"), sort_keys=True) if payload else ""])

    frames = codec.quantize(traj, steps) if len(traj) else np.empty((0, 6))
    with open(folder / "trajectory.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(TRAJECTORY_COLUMNS)
        for seq, row in enumerate(frames):
            w.writerow([seq, *(format(float(v), ".10g") for v in row[:5]), int(row[5])])

    if plan is not None:
        (folder / "interlude_plan.json").write_text(json.dumps({"trial_order": list(plan)}))
    if trials is not None:
        with open(folder / "interlude_trials.csv", "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(INTERLUDE_COLUMNS)
            for seq, t in enumerate(trials):
                w.writerow([seq if c == "seq" else _cell(t.get(c)) for c in INTERLUDE_COLUMNS])
    return folder


def read_run(root, run_id):
    return json.loads((Path(root) / str(run_id) / "run.json").read_text())


def read_session(folder):
    """A session folder as a dict: session (the row), traj (n, 6), events (list of dicts with `payload` dicts), plan
    (list or None), trials (list of dicts or None), truncated (names of files whose last line was cut short and dropped)."""
    folder = Path(folder)
    session = json.loads((folder / "session.json").read_text())
    events, events_cut = _read_rows(folder / "events.csv", EVENT_COLUMNS, _event)
    rows, traj_cut = _read_rows(folder / "trajectory.csv", TRAJECTORY_COLUMNS,
                                lambda r: [float(r[c]) for c in TRAJECTORY_COLUMNS])
    traj = np.array(rows, dtype=float).reshape(-1, 7)
    # The sequence numbers must be consecutive; a local copy of a session that was continued on another computer starts later than 0.
    if len(traj) and not np.array_equal(traj[:, 0], traj[0, 0] + np.arange(len(traj))):
        raise ValueError(f"{folder}: trajectory seq is not consecutive")
    plan = json.loads((folder / "interlude_plan.json").read_text())["trial_order"] if (folder / "interlude_plan.json").exists() else None
    trials = trial_cut = None
    if (folder / "interlude_trials.csv").exists():
        trials, trial_cut = _read_rows(folder / "interlude_trials.csv", INTERLUDE_COLUMNS, _trial)
    truncated = [name for name, cut in (("trajectory.csv", traj_cut), ("events.csv", events_cut),
                                        ("interlude_trials.csv", trial_cut)) if cut]
    return {"session": session, "traj": traj[:, 1:], "events": events, "plan": plan, "trials": trials, "truncated": truncated}
