import os
import subprocess
import sys

import mutation_check as mc

SOURCE = '''def pick(a, b, items):
    if a < b and not items:
        return a + b - 1
    flag = True
    return items[0] * 2.5 if flag else 0.0
'''


def descriptions(mutants):
    return [m.description for m in mutants]


def test_every_kind_of_mutant_is_generated_and_compiles():
    ms = mc.generate_mutants(SOURCE)
    d = " | ".join(descriptions(ms))
    for expected in ("< -> <=", "and -> or", "drop not", "+ -> -", "- -> +", "1 -> 2", "True -> False", "* -> /", "2.5 -> 5", "negate condition"):
        assert expected in d, expected
    for m in ms:
        compile(m.source, "m.py", "exec")
        assert m.source != SOURCE


def test_lines_restrict_the_mutants():
    only = mc.generate_mutants(SOURCE, lines={3})
    assert only and {m.line for m in only} == {3}
    assert not mc.generate_mutants(SOURCE, lines={99})


def test_a_mutant_replaces_exactly_the_node_and_keeps_the_rest_of_the_file():
    ms = mc.generate_mutants("x = 1\ny = a < b  # keep me\nz = 'é' + w\n", lines={2})
    assert [m.source for m in ms if "<=" in m.description][0] == "x = 1\ny = a <= b  # keep me\nz = 'é' + w\n"
    wide = mc.generate_mutants("z = 'é' + w\n")                         # columns are UTF-8 bytes: the é is two of them
    assert any(m.source == "z = 'é' - w\n" for m in wide)


def test_changed_lines_come_from_a_zero_context_diff():
    diff = "@@ -3,2 +3,3 @@ def f():\n+a\n@@ -10 +11 @@\n-x\n+y\n@@ -20,3 +22,0 @@\n"
    assert mc.parse_changed_lines(diff) == {3, 4, 5, 11}


def test_survivors_and_killed_mutants_on_a_toy_project(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "m.py").write_text("def limit(x):\n    return x >= 10\n\n\ndef unused(x):\n    return x + 1\n")
    (tmp_path / "scripts" / "test_m.py").write_text("from m import limit\n\n\ndef test_limit():\n    assert limit(11) and not limit(5)\n")
    results, bad = mc.check(tmp_path, {"scripts/m.py": None}, lambda path: ["scripts/test_m.py"], sys.executable, max_mutants=20,
                            log=lambda *_: None)
    assert not bad
    boundary = [killed for m, killed, _, _ in results if m.line == 2 and "-> >" in m.description.replace("`", "")]
    assert boundary and not any(boundary)                                 # a survivor is reported
    assert all(killed for m, killed, _, _ in results if m.line == 2 and "negate" in m.description)
    assert not any(killed for m, killed, _, _ in results if m.line == 6)  # the untested function's mutants all survive
    text = mc.report(results, bad, "HEAD")
    assert "SURVIVED scripts/m.py:6" in text
    assert f"{len(results)} mutants run, {sum(k for _, k, _, _ in results)} killed" in text


def test_failing_baselines_and_missing_tests_are_reported_not_mutated(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "m.py").write_text("def f(x):\n    return x + 1\n")
    (tmp_path / "scripts" / "test_m.py").write_text("from m import f\n\n\ndef test_f():\n    assert f(1) == 99\n")
    results, bad = mc.check(tmp_path, {"scripts/m.py": None}, lambda path: ["scripts/test_m.py"], sys.executable, log=lambda *_: None)
    assert results == [] and "already fail" in bad[0]
    results, bad = mc.check(tmp_path, {"scripts/m.py": None}, lambda path: [], sys.executable, log=lambda *_: None)
    assert results == [] and "no test file depends on it" in bad[0]


def test_a_mutant_that_loops_forever_counts_as_killed(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "m.py").write_text("def count(n):\n    i = 0\n    while i < n:\n        i = i + 1\n    return i\n")
    (tmp_path / "scripts" / "test_m.py").write_text("from m import count\n\n\ndef test_count():\n    assert count(3) == 3\n")
    results, bad = mc.check(tmp_path, {"scripts/m.py": {4}}, lambda path: ["scripts/test_m.py"], sys.executable, timeout=2,
                            log=lambda *_: None)
    assert results and all(killed for _, killed, _, _ in results)
    assert "timeout" in [detail for _, _, detail, _ in results]                  # the `+ -> -` mutant never ends


def test_a_mutant_is_not_run_from_the_previous_mutants_bytecode(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTHONDONTWRITEBYTECODE", raising=False)
    (tmp_path / "scripts").mkdir()
    module = tmp_path / "scripts" / "m.py"
    module.write_text("def f(x):\n    return x + 1\n")
    (tmp_path / "scripts" / "test_m.py").write_text("from m import f\n\n\ndef test_f():\n    assert f(1) == 2\n")
    stamp = module.stat().st_mtime_ns
    assert mc.run_tests_in(tmp_path, ["scripts/test_m.py"], sys.executable, 60)[0]
    module.write_text("def f(x):\n    return x - 1\n")                        # same size, same modification time
    os.utime(module, ns=(stamp, stamp))
    assert not mc.run_tests_in(tmp_path, ["scripts/test_m.py"], sys.executable, 60)[0]


def test_changed_files_are_the_non_test_scripts_with_their_changed_lines(tmp_path, monkeypatch):
    def run(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=tmp_path, check=True, capture_output=True)

    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "a.py").write_text("a = 1\nb = 2\nc = 3\n")
    (tmp_path / "scripts" / "test_a.py").write_text("x = 1\n")
    (tmp_path / "notes.py").write_text("x = 1\n")
    run("init")
    run("add", ".")
    run("commit", "-m", "x")
    (tmp_path / "scripts" / "a.py").write_text("a = 1\nb = 5\nc = 3\n")
    (tmp_path / "scripts" / "test_a.py").write_text("x = 2\n")
    (tmp_path / "notes.py").write_text("x = 2\n")
    (tmp_path / "scripts" / "new.py").write_text("y = 1\n")
    (tmp_path / "scripts" / "readme.md").write_text("text\n")
    monkeypatch.setattr(mc, "ROOT", tmp_path)
    assert mc.changed_python_files("HEAD") == {"scripts/a.py": {2}, "scripts/new.py": None}


def test_lines_arguments_accumulate_per_file():
    assert mc.parse_lines_arg(["a.py:3-5", "a.py:9", "b.py:1-2"]) == {"a.py": {3, 4, 5, 9}, "b.py": {1, 2}}


def test_main_mutates_the_named_files(tmp_path, monkeypatch, capsys):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "m.py").write_text("def limit(x):\n    return x >= 10\n")
    (tmp_path / "scripts" / "test_m.py").write_text("from m import limit\n\n\ndef test_limit():\n    assert limit(11) and not limit(5)\n")
    monkeypatch.setattr(mc, "ROOT", tmp_path)
    monkeypatch.setattr(mc, "tests_for", lambda path: ["scripts/test_m.py"])
    assert mc.main(["--files", "scripts/m.py", "--lines", "scripts/m.py:2-2"]) == 0
    assert "mutants run" in capsys.readouterr().out
