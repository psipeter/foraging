"""The pure parts of `server_admin.py publish`: where the connection string comes from, which experiments the catalog lists, and what a build's plan is."""

import json
import subprocess

import pytest

import server_admin


def test_the_connection_string_comes_from_the_environment_first_then_a_private_file(tmp_path):
    file = tmp_path / "db_url"
    assert server_admin.db_url({}, file) is None
    file.write_text("postgresql://from-file\nsecond line ignored\n")
    file.chmod(0o600)
    assert server_admin.db_url({}, file) == "postgresql://from-file"
    assert server_admin.db_url({"FORAGING_DB_URL": "postgresql://from-env"}, file) == "postgresql://from-env"


def test_a_connection_string_file_others_can_read_is_refused(tmp_path):
    file = tmp_path / "db_url"
    file.write_text("postgresql://secret\n")
    file.chmod(0o644)
    with pytest.raises(PermissionError, match="chmod 600"):
        server_admin.db_url({}, file)


def test_the_catalog_lists_the_experiments_in_menu_order_with_their_prerequisites():
    experiments = server_admin.catalog_experiments()
    codes = [e["code"] for e in experiments]
    assert codes == ["FOR"] and [e["order"] for e in experiments] == list(range(1, len(codes) + 1))
    assert experiments[0]["requires"] == [] and experiments[0]["title"] == "Foraging in Tiles"


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
    plan = server_admin.build_plan(fake_build(tmp_path, head(), dirty=True))
    assert plan["commit"] == head() and [e["code"] for e in plan["experiments"]] == ["FOR"]
    assert set(plan["sessions"]) == {"FOR"} and all(n > 0 for n in plan["sessions"].values())
    assert plan["worlds"] == tmp_path / "build" / "StreamingAssets" / "Experiments"
    assert any("dirty" in note for note in plan["notes"])


def test_a_build_without_a_prerequisite_is_noted_and_one_without_experiments_is_refused(tmp_path, monkeypatch):
    catalog = [{"code": "AA", "title": "A", "requires": [], "order": 1, "counts": True}, {"code": "BB", "title": "B", "requires": ["AA"], "order": 2, "counts": True}]
    monkeypatch.setattr(server_admin, "catalog_experiments", lambda repo=None: catalog)
    monkeypatch.setattr(server_admin, "sessions_in_build", lambda commit, code, repo=None: 1)
    plan = server_admin.build_plan(fake_build(tmp_path, head(), experiments=("BB",)))
    assert [e["code"] for e in plan["experiments"]] == ["BB"] and any("requires AA" in note for note in plan["notes"])
    with pytest.raises(ValueError, match="no experiment"):
        server_admin.build_plan(fake_build(tmp_path / "empty", head(), experiments=()))


def test_a_development_builds_plan_is_marked_so_its_release_may_start_reduced_runs(tmp_path):
    assert server_admin.build_plan(fake_build(tmp_path / "a", head(), development=True))["development"] is True
    assert server_admin.build_plan(fake_build(tmp_path / "b", head(), development=False))["development"] is False
    assert server_admin.build_plan(fake_build(tmp_path / "c", head()))["development"] is False             # an older build_info.json has no flag: a release


def test_a_builds_description_names_its_kind_commit_size_and_parts_and_the_release_note_follows_it(tmp_path):
    from datetime import datetime, timezone
    build = fake_build(tmp_path, head(), dirty=True, development=True)
    (build / "Build.bin").write_bytes(b"\0" * 3_000_000)
    now = datetime(2026, 11, 10, 17, 30, tzinfo=timezone.utc)
    subject, body = server_admin.build_description(build, "reduced runs", now=now)
    assert subject.startswith(f"Development build {head()[:7]} (dirty): 3 MB, parts FOR ")
    assert body.splitlines()[0] == "Reason: reduced runs" and head() in body and "2026-11-10 17:30 UTC" in body and "uncommitted changes" in body
    assert server_admin.release_note(subject, "reduced runs") == f"{subject} | reduced runs" and server_admin.release_note(subject) == subject
    release, _ = server_admin.build_description(fake_build(tmp_path / "r", head(), development=False))
    assert release.startswith(f"Release build {head()[:7]}:") and "(dirty)" not in release
