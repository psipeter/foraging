"""Summarise the runs of scripts/perf_browser.mjs: one row per variant (median over its runs), with the change against `base`.

    ./venv/bin/python scripts/perf_report.py <tag> [--out results/perf] [--phases]

Times are milliseconds per frame from the game's own frame clock (PerfProbe: only frames in which the game ran). A row's `spread` is the range of
the runs' mean frame time; a difference smaller than the spread is noise. `>33` is the share of frames slower than 30 fps. `draws`, `tris` and `casters` are
Unity's per-frame renderer counters (0 when the browser build does not report them). Warns when a run used software drawing or a different browser or GPU than base.
"""
import argparse
import json
import statistics
from pathlib import Path


def load(tag, out):
    runs = {}
    for f in sorted((Path(out) / tag).glob("*.json")):
        r = json.loads(f.read_text())
        runs.setdefault(r["run"]["variant"], []).append(r)
    return runs


def med(values):
    return statistics.median(values) if values else float("nan")


def phase_means(run):
    """Mean frame time per autopilot phase (the marks are 'label@frame index')."""
    marks = [(m.rsplit("@", 1)[0], int(m.rsplit("@", 1)[1])) for m in run.get("marks", [])]
    frames = run["frames"]
    out = {}
    for i, (label, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(frames)
        chunk = frames[start:end]
        if chunk:
            out[label] = sum(chunk) / len(chunk)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "results" / "perf"))
    ap.add_argument("--phases", action="store_true")
    a = ap.parse_args()
    runs = load(a.tag, a.out)
    if "base" not in runs:
        raise SystemExit("no 'base' variant in this tag")
    base_mean = med([r["summary"]["meanMs"] for r in runs["base"]])
    base_env = (runs["base"][0]["env"]["gpu"], runs["base"][0]["run"]["browser"])
    head = f"{'variant':<28}{'runs':>5}{'mean':>8}{'spread':>8}{'vs base':>9}{'p95':>7}{'p99':>7}{'max':>7}{'>33':>7}{'draws':>7}{'tris k':>8}{'casters':>9}{'gc':>4}"
    print(head)
    print("-" * len(head))
    for name, rs in runs.items():
        means = [r["summary"]["meanMs"] for r in rs]
        s = [r["summary"] for r in rs]
        frames = sum(x["frames"] for x in s)
        over = sum(x["over33"] for x in s) / frames * 100 if frames else 0
        sec = [row for r in rs for row in r["seconds"]]
        draws = med([row[3] for row in sec]) if sec else 0
        tris = med([row[5] for row in sec]) / 1000 if sec else 0
        casters = med([row[7] for row in sec]) if sec else 0
        print(f"{name:<28}{len(rs):>5}{med(means):>8.2f}{max(means) - min(means):>8.2f}{(med(means) / base_mean - 1) * 100:>+8.0f}%"
              f"{med([x['p95Ms'] for x in s]):>7.1f}{med([x['p99Ms'] for x in s]):>7.1f}{max(x['maxMs'] for x in s):>7.0f}{over:>6.1f}%"
              f"{draws:>7.0f}{tris:>8.0f}{casters:>9.0f}{med([x['gcCollections'] for x in s]):>4.0f}")
        env = (rs[0]["env"]["gpu"], rs[0]["run"]["browser"])
        if "SwiftShader" in env[0] or "llvmpipe" in env[0].lower():
            print(f"  WARNING: {name} was drawn in software ({env[0]}); its times mean nothing")
        if env != base_env:
            print(f"  WARNING: {name} ran on a different GPU or browser than base ({env} vs {base_env})")
        if a.phases:
            for label in ("walk", "horizon", "ground"):
                vals = [phase_means(r).get(label) for r in rs]
                vals = [v for v in vals if v is not None]
                if vals:
                    print(f"    {label:<8}{med(vals):>7.2f} ms")


if __name__ == "__main__":
    main()
