"""The pure parts of `database.py`: the connection guards (project, scrubbing, terminal, confirmation, log) and `publish`: which experiments the catalog lists, and what a build's plan is."""

import io
import json
import os
import urllib.error
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

import database


def test_the_project_is_read_from_a_pooler_or_a_direct_string_and_unknown_forms_name_none():
    assert database.project_ref("postgresql://postgres.abcdefgh:pw@aws-0-eu.pooler.supabase.com:6543/postgres") == "abcdefgh"
    assert database.project_ref("postgresql://postgres:pw@db.abcdefgh.supabase.co:5432/postgres") == "abcdefgh"
    assert database.project_ref("postgresql://u:pw@127.0.0.1:5432/postgres") is None


def test_the_expected_project_is_the_one_online_json_points_at(tmp_path):
    path = tmp_path / "online.json"
    path.write_text(json.dumps({"url": "https://zzyyxxww.supabase.co/functions/v1"}))
    assert database.expected_ref(path) == "zzyyxxww"
    assert database.expected_ref() == "emdgczidpqdhftzujyte"


def test_a_string_for_another_project_is_refused_before_any_connection():
    with pytest.raises(SystemExit, match="is for project other.*online.json points at mine"):
        database.connect("postgresql://postgres.other:pw@aws-0-eu.pooler.supabase.com:6543/postgres", "mine")


def test_the_secret_and_its_password_are_scrubbed_from_text():
    url = "postgresql://postgres.abc:p%40ss@host:6543/postgres"
    text = f"could not connect to {url} with password p@ss and p%40ss"
    cleaned = database.scrub(text, *database.secrets_of(url))
    assert "p@ss" not in cleaned and "p%40ss" not in cleaned and "postgresql://" not in cleaned and "***" in cleaned


def test_the_script_refuses_to_run_without_a_terminal():
    class Stream:
        def __init__(self, tty):
            self.tty = tty

        def isatty(self):
            return self.tty
    database.require_terminal(Stream(True), Stream(True))
    for stdin, stdout in ((False, True), (True, False), (False, False)):
        with pytest.raises(SystemExit, match="needs a terminal"):
            database.require_terminal(Stream(stdin), Stream(stdout))


def test_a_write_waits_for_the_project_ref_to_be_typed():
    database.confirm_write("abc", lambda prompt: "abc")
    with pytest.raises(SystemExit, match="nothing written"):
        database.confirm_write("abc", lambda prompt: "yes")


def test_no_credential_is_read_from_the_environment_or_a_file():
    source = (Path(__file__).parent / "database.py").read_text()
    assert source.count("os.environ") == 1 and "os.environ.copy()" in source and "getenv" not in source and "FORAGING_DB_URL" not in source and "db_url" not in source


def test_the_log_keeps_what_was_reported_without_the_secret(tmp_path, capsys):
    log = database.Log("publish", ["publish", "--build", "Builds/web"], tmp_path, now=datetime(2026, 11, 18, 9, 0, tzinfo=timezone.utc))
    log.secrets = ["hunter2"]
    log.project = "abc"
    log("registered release with password hunter2")
    path = log.save("done")
    text = path.read_text()
    assert path.name == "db_publish_20261118-090000.log" and "hunter2" not in text and "registered release with password ***" in text and "project: abc" in text and "outcome: done" in text


def test_the_catalog_lists_the_experiments_in_menu_order_with_their_prerequisites():
    experiments = database.catalog_experiments()
    codes = [e["code"] for e in experiments]
    assert codes == ["TUT", "FOR"] and [e["order"] for e in experiments] == list(range(1, len(codes) + 1))
    by = {e["code"]: e for e in experiments}
    assert by["TUT"]["requires"] == [] and by["TUT"]["title"] == "Tutorial" and by["FOR"]["requires"] == ["TUT"] and by["FOR"]["title"] == "Foraging task"


def fake_build(tmp_path, commit, dirty=False, experiments=("FOR",), development=None):
    build = tmp_path / "build"
    (build / "StreamingAssets").mkdir(parents=True)
    (build / "StreamingAssets" / "build_info.json").write_text(json.dumps({"commit": commit, "dirty": dirty, **({} if development is None else {"development": development})}))
    for code in experiments:
        (build / "StreamingAssets" / "Experiments" / code).mkdir(parents=True)
    return build


def head():
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def test_a_builds_plan_takes_its_commit_and_experiments_from_the_build(tmp_path):
    plan = database.build_plan(fake_build(tmp_path, head(), dirty=True))
    assert plan["commit"] == head() and [e["code"] for e in plan["experiments"]] == ["FOR"]
    assert set(plan["sessions"]) == {"FOR"} and all(n > 0 for n in plan["sessions"].values())
    assert plan["worlds"] == tmp_path / "build" / "StreamingAssets" / "Experiments"
    assert any("dirty" in note for note in plan["notes"])


def test_a_build_without_a_prerequisite_is_noted_and_one_without_experiments_is_refused(tmp_path, monkeypatch):
    catalog = [{"code": "AA", "title": "A", "requires": [], "order": 1, "counts": True}, {"code": "BB", "title": "B", "requires": ["AA"], "order": 2, "counts": True}]
    monkeypatch.setattr(database, "catalog_experiments", lambda repo=None: catalog)
    monkeypatch.setattr(database, "sessions_in_build", lambda commit, code, repo=None: 1)
    plan = database.build_plan(fake_build(tmp_path, head(), experiments=("BB",)))
    assert [e["code"] for e in plan["experiments"]] == ["BB"] and any("requires AA" in note for note in plan["notes"])
    with pytest.raises(ValueError, match="no experiment"):
        database.build_plan(fake_build(tmp_path / "empty", head(), experiments=()))


def test_a_development_builds_plan_is_marked_so_its_release_may_start_reduced_runs(tmp_path):
    assert database.build_plan(fake_build(tmp_path / "a", head(), development=True))["development"] is True
    assert database.build_plan(fake_build(tmp_path / "b", head(), development=False))["development"] is False
    assert database.build_plan(fake_build(tmp_path / "c", head()))["development"] is False             # an older build_info.json has no flag: a release


def test_a_builds_description_names_its_kind_commit_size_and_parts_and_the_release_note_follows_it(tmp_path):
    from datetime import datetime, timezone
    build = fake_build(tmp_path, head(), dirty=True, development=True)
    (build / "Build.bin").write_bytes(b"\0" * 3_000_000)
    now = datetime(2026, 11, 10, 17, 30, tzinfo=timezone.utc)
    subject, body = database.build_description(build, "reduced runs", now=now)
    assert subject.startswith(f"Development build {head()[:7]} (dirty): 3 MB, parts FOR ")
    assert body.splitlines()[0] == "Reason: reduced runs" and head() in body and "2026-11-10 17:30 UTC" in body and "uncommitted changes" in body
    assert database.release_note(subject, "reduced runs") == f"{subject} | reduced runs" and database.release_note(subject) == subject
    release, _ = database.build_description(fake_build(tmp_path / "r", head(), development=False))
    assert release.startswith(f"Release build {head()[:7]}:") and "(dirty)" not in release


def test_url_from_password_encodes_and_keeps_a_full_url():
    url = database.url_from_password("p@ss/w:rd#1", "abcdefgh", host="h.example", port=5432)
    assert url == "postgresql://postgres.abcdefgh:p%40ss%2Fw%3Ard%231@h.example:5432/postgres"
    assert database.project_ref(url) == "abcdefgh"
    assert database.secrets_of(url)[-1] == "p@ss/w:rd#1"
    full = "postgresql://postgres.abcdefgh:pw@h.example:6543/postgres"
    assert database.url_from_password(full, "other") == full


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def run_token(argv, tmp_path, answer="local", opener=None, runner=None, value=None, token="sbp_secrettoken"):
    database.main(argv, secret=lambda: "dbpassword", ask=lambda prompt: answer, expected="local", log_dir=tmp_path, token=lambda: token, value=value,
                  opener=opener or (lambda request, timeout: FakeResponse()), runner=runner)
    return sorted(tmp_path.glob("db_*.log"))[-1].read_text()


def test_set_secret_builds_the_pooler_url_from_the_password_sends_it_in_the_body_and_logs_none_of_it(tmp_path):
    sent = {}

    def opener(request, timeout):
        sent.update(url=request.full_url, auth=request.get_header("Authorization"), body=json.loads(request.data))
        return FakeResponse()
    text = run_token(["set-secret", "--name", "FORAGING_POOLER_URL"], tmp_path, opener=opener, value=lambda: "p@ss/w")
    assert sent["url"].endswith("/projects/local/secrets") and sent["auth"] == "Bearer sbp_secrettoken"
    assert sent["body"] == [{"name": "FORAGING_POOLER_URL", "value": "postgresql://postgres.local:p%40ss%2Fw@" + database.POOLER_HOST + ":6543/postgres"}]
    assert "outcome: done" in text and "secret FORAGING_POOLER_URL set" in text
    assert "sbp_secrettoken" not in text and "p@ss/w" not in text and "p%40ss" not in text


def test_set_secret_needs_the_typed_ref_and_refuses_reserved_names_and_api_errors(tmp_path):
    called = []
    with pytest.raises(SystemExit, match="nothing written"):
        run_token(["set-secret", "--name", "ALLOWED_ORIGIN"], tmp_path, answer="no", opener=lambda r, timeout: called.append(r), value=lambda: "https://x")
    assert called == []
    with pytest.raises(SystemExit, match="not a settable"):
        run_token(["set-secret", "--name", "SUPABASE_URL"], tmp_path, value=lambda: "v")

    def refuse(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO(b"bad token sbp_secrettoken"))
    with pytest.raises(SystemExit, match="refused the secret \\(401\\)") as e:
        run_token(["set-secret", "--name", "ALLOWED_ORIGIN"], tmp_path, opener=refuse, value=lambda: "v")
    assert "sbp_secrettoken" not in str(e.value)


def test_deploy_functions_puts_the_token_in_the_child_environment_only_and_scrubs_its_output(tmp_path):
    seen = {}

    def runner(cmd, **kwargs):
        seen.update(cmd=cmd, env=kwargs["env"], cwd=kwargs["cwd"])

        class Done:
            returncode, stdout, stderr = 0, "Deployed run-start with sbp_secrettoken\n", ""
        return Done()
    text = run_token(["deploy-functions"], tmp_path, runner=runner)
    assert seen["env"]["SUPABASE_ACCESS_TOKEN"] == "sbp_secrettoken" and "sbp_secrettoken" not in " ".join(seen["cmd"])
    assert seen["cmd"][-2:] == ["--project-ref", "local"] and {"participant-start", "run-start", "append", "run-finish", "feedback", "--no-verify-jwt", "--use-api"} <= set(seen["cmd"]) and "_shared" not in seen["cmd"] and "sbp_secrettoken" not in text and "functions deployed" in text
    assert "SUPABASE_ACCESS_TOKEN" not in os.environ


def test_a_failed_deploy_is_a_failed_run(tmp_path):
    class Done:
        returncode, stdout, stderr = 1, "", "boom"
    with pytest.raises(SystemExit, match="deploy failed"):
        run_token(["deploy-functions"], tmp_path, runner=lambda cmd, **k: Done())
    assert "outcome: stopped" in sorted(tmp_path.glob("db_*.log"))[-1].read_text()


def test_cleanup_refuses_a_git_commit_name():
    with pytest.raises(SystemExit, match="looks like a git commit"):
        database.throwaway_rows(None, "22f16b46f042459260ad70ceca206e60171d197e")
