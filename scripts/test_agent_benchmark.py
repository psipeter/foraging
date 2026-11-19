"""The five-agent table (agent_benchmark.py): the Markdown and the statistics, on stated numbers."""

import pytest

import agent_benchmark as ab


def result(code="XX", session="XX_S1", scale=1.0):
    points = {a: [100.0 * scale, 110.0 * scale] for a in ab.AGENTS}
    bushes = {a: [2.0, 3.0] for a in ab.AGENTS}
    return {"code": code, "session": session, "knobs": {"class": "additive", "gini": 0.4}, "points": points, "bushes": bushes, "chosen": {"top-k": [2, 3], "thr-q": [60, 70]}, "n_worlds": 2}


def test_the_mean_and_the_standard_error_of_worlds():
    mean, se = ab.stats([1.0, 3.0])
    assert mean == pytest.approx(2.0) and se == pytest.approx(1.0)


def test_the_table_has_a_row_per_agent_and_two_columns_per_session_of_each_experiment():
    text = ab.markdown([result(session="XX_S1"), result(session="XX_S2", scale=2.0), result(code="YY", session="YY_S1")])
    assert text.count("## ") == 2 and text.count("| mvt (marginal value) |") == 2
    assert "| agent | XX_S1 points | XX_S1 bushes/patch | XX_S2 points | XX_S2 bushes/patch |" in text
    assert "105 ± 5 | 2.50 ± 0.50" in text and "210 ± 10" in text


def test_the_csv_lists_every_agent_of_every_session(tmp_path):
    ab.write_csv([result(), result(session="XX_S2")], tmp_path / "a.csv")
    rows = (tmp_path / "a.csv").read_text().splitlines()
    assert len(rows) == 1 + 2 * len(ab.AGENTS) and rows[0].startswith("code,session,agent")
