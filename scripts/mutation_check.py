"""Mutation testing on the lines you changed: do the tests notice when a rule is broken?

For every Python source file changed since a git ref, this makes small mutants of the changed lines (flip a comparison, swap + and -,
off-by-one a constant, negate a condition, flip a boolean), runs the test files that depend on the file (run_tests.DEPENDENCIES)
against each mutant in a scratch copy of the project, and lists the mutants that SURVIVED: rules the suite does not pin down. A
survivor is a lead, not a verdict: it may be an equivalent mutant (the change makes no observable difference) or a line that is
deliberately untested; the reviewer decides which.

    ./venv/bin/python scripts/mutation_check.py                      # changed files since HEAD
    ./venv/bin/python scripts/mutation_check.py --since main --max 40
    ./venv/bin/python scripts/mutation_check.py --files scripts/replay.py --lines scripts/replay.py:200-240

The project itself is never modified: mutants run in a temporary copy (tracked and untracked files, media and results left out).
Test files are not mutated. C# is out of scope (there is no way to run it from here).
"""

import argparse
import ast
import copy
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

SKIP_SUFFIXES = {".wav", ".mp3", ".ogg", ".png", ".jpg", ".jpeg", ".exr", ".psd", ".fbx", ".sqlite", ".bak", ".bin"}
SKIP_PREFIXES = ("results/", "ForagingData/", "Library/", "Builds/", "Logs/", "Assets/Audio/", "Assets/Textures/")
MAX_COPY_BYTES = 8_000_000

COMPARE = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
           ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}
BINOP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult}
SYMBOL = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=", ast.In: "in", ast.NotIn: "not in",
          ast.Is: "is", ast.IsNot: "is not", ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.And: "and", ast.Or: "or"}


@dataclass
class Mutant:
    file: str           # repo-relative path
    line: int
    description: str    # "`a < b` -> `a <= b`"
    source: str         # the whole mutated file


# --------------------------------------------------------------------------------------------------
# Generating mutants
# --------------------------------------------------------------------------------------------------

def _variants(node):
    """(replacement node, description) pairs for one AST node."""
    out = []
    if isinstance(node, ast.Compare):
        for i, op in enumerate(node.ops):
            if type(op) in COMPARE:
                new = copy.deepcopy(node)
                new.ops[i] = COMPARE[type(op)]()
                out.append((new, f"{SYMBOL[type(op)]} -> {SYMBOL[COMPARE[type(op)]]}"))
    elif isinstance(node, ast.BinOp) and type(node.op) in BINOP:
        new = copy.deepcopy(node)
        new.op = BINOP[type(node.op)]()
        out.append((new, f"{SYMBOL[type(node.op)]} -> {SYMBOL[BINOP[type(node.op)]]}"))
    elif isinstance(node, ast.BoolOp):
        new = copy.deepcopy(node)
        new.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        out.append((new, f"{SYMBOL[type(node.op)]} -> {SYMBOL[type(new.op)]}"))
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Not, ast.USub)):
        out.append((copy.deepcopy(node.operand), "drop " + ("not" if isinstance(node.op, ast.Not) else "-")))
    elif isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool):
            out.append((ast.Constant(not v), f"{v} -> {not v}"))
        elif isinstance(v, int):
            out.append((ast.Constant(v + 1), f"{v} -> {v + 1}"))
        elif isinstance(v, float):
            new = v * 2.0 if v else 1.0
            out.append((ast.Constant(new), f"{v:g} -> {new:g}"))
    return out


def _negations(node):
    """Conditions of if / while / ternaries, negated."""
    if isinstance(node, (ast.If, ast.While, ast.IfExp)):
        test = node.test
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            return [(copy.deepcopy(test.operand), "negate condition")]
        return [(ast.UnaryOp(ast.Not(), copy.deepcopy(test)), "negate condition")]
    return []


def _offsets(source):
    """Byte offset of the start of each line (ast columns are UTF-8 byte offsets)."""
    starts, pos = [0], 0
    for line in source.encode().splitlines(keepends=True):
        pos += len(line)
        starts.append(pos)
    return starts


def generate_mutants(source, file="module.py", lines=None):
    """All mutants of `source` on the given 1-based `lines` (None = every line), as Mutant objects. A mutant that does not
    compile is dropped."""
    tree = ast.parse(source)
    data = source.encode()
    starts = _offsets(source)
    seen, mutants = set(), []

    def emit(node, replacement, description):
        if lines is not None and node.lineno not in lines:
            return
        begin = starts[node.lineno - 1] + node.col_offset
        end = starts[node.end_lineno - 1] + node.end_col_offset
        text = ast.unparse(replacement)
        mutated = (data[:begin] + text.encode() + data[end:]).decode()
        original = data[begin:end].decode()
        key = (node.lineno, begin, mutated)
        if key in seen or mutated == source:
            return
        try:
            compile(mutated, file, "exec")
        except SyntaxError:
            return
        seen.add(key)
        snippet = " ".join(original.split())
        mutants.append(Mutant(file, node.lineno, f"`{snippet[:60]}`: {description}", mutated))

    for node in ast.walk(tree):
        if not hasattr(node, "lineno") or not hasattr(node, "end_lineno"):
            continue
        for replacement, description in _variants(node):
            emit(node, replacement, description)
        for replacement, description in _negations(node):
            emit(node.test, replacement, description)
    return sorted(mutants, key=lambda m: m.line)


# --------------------------------------------------------------------------------------------------
# Which lines changed
# --------------------------------------------------------------------------------------------------

def parse_changed_lines(diff_text):
    """New-file line numbers touched by a `git diff -U0` of one file."""
    lines = set()
    for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", diff_text, re.M):
        start, count = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        lines.update(range(start, start + count))
    return lines


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout


def changed_python_files(since):
    """{repo-relative path: set of changed lines, or None for all lines (a new file)} for non-test scripts/*.py."""
    tracked = {f for f in git("diff", "--name-only", since).splitlines() if f}
    untracked = {f for f in git("ls-files", "--others", "--exclude-standard").splitlines() if f}
    out = {}
    for f in sorted(tracked | untracked):
        name = Path(f).name
        if not f.startswith("scripts/") or not f.endswith(".py") or name.startswith("test_") or name == "conftest.py":
            continue
        if not (ROOT / f).exists():
            continue
        out[f] = None if f in untracked else parse_changed_lines(git("diff", "-U0", since, "--", f))
    return out


# --------------------------------------------------------------------------------------------------
# Running mutants
# --------------------------------------------------------------------------------------------------

def make_scratch(root):
    """A temporary copy of the project's tracked and untracked (not ignored) files, minus media, results and big files."""
    files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=root, capture_output=True, text=True).stdout.splitlines()
    if not files:       # non-git directory (the tests' tmp_path): take everything
        files = [str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file()]
    scratch = Path(tempfile.mkdtemp(prefix="mutation_check_"))
    try:
        for f in files:
            src = Path(root) / f
            if f.startswith(SKIP_PREFIXES) or src.suffix.lower() in SKIP_SUFFIXES or not src.is_file():
                continue
            if src.stat().st_size > MAX_COPY_BYTES:
                continue
            dst = scratch / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    except BaseException:
        shutil.rmtree(scratch, ignore_errors=True)
        raise
    return scratch


def python_for(root):
    venv = Path(root) / "venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def tests_for(path):
    """Test files (repo-relative) that depend on `path` (run_tests.DEPENDENCIES)."""
    import run_tests
    return [t for t in run_tests.DEPENDENCIES if run_tests.affected(t, {path})]


def run_tests_in(scratch, tests, python, timeout):
    """(passed, seconds, tail of output). A timeout counts as a failure (the mutant loops)."""
    cmd = [python, "-B", "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", *[str(Path(scratch) / t) for t in tests]]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=Path(scratch) / "scripts", capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, time.time() - t0, "timeout"
    failed = [line for line in r.stdout.splitlines() if line.startswith("FAILED")]
    return r.returncode == 0, time.time() - t0, (failed[0][7:100] if failed else (r.stdout.strip().splitlines() or [""])[-1])


def _say(*args):
    print(*args, flush=True)


def check(project_root, targets, tests_of, python, max_mutants=30, seed=0, timeout=180, log=_say):
    """Mutate `targets` ({repo-relative path: set of lines or None}), run `tests_of(path)` for each mutant in a scratch copy and
    return (results, baseline_failures): results is a list of (Mutant, killed, detail, tests)."""
    rng = random.Random(seed)
    pool = []
    for path, lines in targets.items():
        source = (Path(project_root) / path).read_text()
        pool += generate_mutants(source, path, lines)
    if len(pool) > max_mutants:
        log(f"{len(pool)} mutants on the changed lines; sampling {max_mutants} (seed {seed}; raise --max to run more)")
        pool = sorted(rng.sample(pool, max_mutants), key=lambda m: (m.file, m.line))
    scratch = make_scratch(project_root)
    results, bad = [], []
    try:
        baselines = {}
        for path in targets:
            tests = tests_of(path)
            if not tests:
                bad.append(f"{path}: no test file depends on it (add it to run_tests.DEPENDENCIES)")
                continue
            ok, _, detail = run_tests_in(scratch, tests, python, timeout)
            if ok:
                baselines[path] = tests
            else:
                bad.append(f"{path}: the tests already fail unmutated ({detail})")
        for m in pool:
            if m.file not in baselines:
                continue
            target = scratch / m.file
            original = target.read_text()
            try:
                target.write_text(m.source)
                ok, secs, detail = run_tests_in(scratch, baselines[m.file], python, timeout)
            finally:
                target.write_text(original)
            results.append((m, not ok, detail if not ok else f"{secs:.0f}s", baselines[m.file]))
            log(f"  {'killed  ' if not ok else 'SURVIVED'} {m.file}:{m.line}  {m.description}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return results, bad


def report(results, bad, since):
    survivors = [r for r in results if not r[1]]
    lines = [f"mutation_check ({since}): {len(results)} mutants run, {len(results) - len(survivors)} killed, {len(survivors)} survived"]
    lines += [f"  cannot check: {b}" for b in bad]
    for m, _, _, tests in survivors:
        lines.append(f"  SURVIVED {m.file}:{m.line}  {m.description}   (tests run: {', '.join(Path(t).name for t in tests)})")
    if survivors:
        lines.append("A survivor is a lead: it may be an equivalent mutant or an untested rule; judge each.")
    return "\n".join(lines)


def parse_lines_arg(values):
    out = {}
    for v in values or []:
        path, _, span = v.partition(":")
        a, _, b = span.partition("-")
        out.setdefault(path, set()).update(range(int(a), int(b or a) + 1))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--since", default="HEAD", help="git ref to compare the working tree with (default HEAD)")
    ap.add_argument("--files", nargs="+", help="mutate these repo-relative files (all their lines unless --lines)")
    ap.add_argument("--lines", nargs="+", help="restrict to path:start-end spans (repo-relative)")
    ap.add_argument("--max", type=int, default=30, help="most mutants to run (a seeded random sample beyond it)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=180, help="seconds per mutant's test run")
    args = ap.parse_args(argv)

    if args.files:
        targets = {f: None for f in args.files}
    else:
        targets = changed_python_files(args.since)
    for path, lines in parse_lines_arg(args.lines).items():
        targets[path] = lines
    if not targets:
        print("No changed non-test scripts/*.py files; nothing to mutate (pass --files to choose).")
        return 0
    results, bad = check(ROOT, targets, tests_for, python_for(ROOT), args.max, args.seed, args.timeout)
    print(report(results, bad, args.since))
    return 0


if __name__ == "__main__":
    sys.exit(main())
