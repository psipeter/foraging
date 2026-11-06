import glob
from pathlib import Path

import numpy as np
import pytest

import human_agents
import world
import perception
import replay
from agents import REGISTRY
from test_sim import tiny_world


def toy_log(events, duration=3.0):
    """A participant standing at the origin facing +z for `duration` seconds; bush 0 is ahead (0, 10), bush 1 behind (0, -10)."""
    t = np.arange(0.0, duration + 1e-9, 0.1)
    traj = np.column_stack([t, np.zeros_like(t), np.zeros_like(t), np.zeros_like(t), np.zeros_like(t), np.zeros_like(t)])
    bushes = replay.Bushes(pos=np.array([[0.0, 10.0], [0.0, -10.0]]), canopy_radius=np.ones(2), fruit_reward=np.array([[5, 7], [1, 2]]))
    ev = [dict(t=e[0], real=0.0, type=e[1], tree_id=e[2], k=e[3], reward=e[4], running_total=0, payload={}) for e in events]
    return replay.SessionLog(Path("."), {"name": "T"}, traj, ev, bushes)


def feed(events, **kw):
    world = tiny_world([[0, 10], [0, -10]], [[5, 7], [1, 2]], duration=3.0)
    agent = REGISTRY["learner"]()
    return human_agents.replay_into_agent(agent, toy_log(events), world=world, percept=perception.ConePercept(120.0, 100.0), **kw)


def test_the_agent_sees_what_is_in_front_and_learns_the_logged_rewards_in_order():
    fed = feed([(0.5, "fruit", 0, 0, 5), (1.0, "fruit", 0, 1, 7), (1.2, "harvest_release", 0, -1, 0)])
    mem = fed.agent.memory
    assert list(mem.known) == [True, False]                                         # the bush behind the participant was never in view
    assert mem.rewards[0] == [5.0, 7.0] and mem.depleted[0]                         # both fruits taken: the bush is spent
    assert (fed.n_fruits, fed.total, fed.unseen_harvests) == (2, 12.0, [])


def test_a_bush_the_sensor_missed_is_shown_when_harvested_and_counted():
    fed = feed([(0.5, "fruit", 1, 0, 1), (0.9, "harvest_release", 1, -1, 0)])
    assert fed.unseen_harvests == [(0.5, 1)] and fed.agent.memory.known[1] and fed.agent.memory.rewards[1] == [1.0]
    assert not fed.agent.memory.depleted[1]                                         # one fruit of two


def test_a_visit_is_ended_by_its_release_or_by_the_end_of_the_session():
    open_bout = feed([(0.5, "fruit", 0, 0, 5)]).agent.critic
    closed = feed([(0.5, "fruit", 0, 0, 5), (0.6, "harvest_release", 0, -1, 0)]).agent.critic
    assert open_bout.update_on == "bush" and not np.allclose(closed.w, 0.0) and np.allclose(open_bout.w, closed.w)


def test_fast_mode_teaches_the_same_critic_and_shows_only_the_harvested_bushes():
    events = [(0.5, "fruit", 0, 0, 5), (1.0, "fruit", 0, 1, 7), (1.2, "harvest_release", 0, -1, 0), (2.0, "fruit", 1, 0, 1)]
    full, fast = feed(events), feed(events, fast=True)
    assert fast.agent.memory.rewards == full.agent.memory.rewards and fast.n_fruits == full.n_fruits == 3 and fast.total == full.total
    assert np.allclose(fast.agent.critic.w, full.agent.critic.w)
    assert list(fast.agent.memory.known) == [True, True] and fast.n_steps == 0 and fast.unseen_harvests == []


FINISHED = sorted(glob.glob(str(Path(__file__).resolve().parent.parent / "ForagingData" / "*" / "02" / "session.json")))


def _asset_exists(log):
    """A pilot run of a session that has since been removed (an archived design's variant) cannot be rebuilt."""
    return world.session_asset_path(log.name).exists()


@pytest.mark.skipif(not FINISHED, reason="no participant data in ForagingData/")
def test_every_participant_session_is_replayed_fast_to_its_logged_score():
    for path in FINISHED:
        log = replay.load_session_log(Path(path).parent)
        if log.final_score is None or len(log.traj) == 0 or not _asset_exists(log):      # (a session stopped before the first frame has nothing to replay)
            continue
        fed = human_agents.replay_into_agent(REGISTRY["learner"](), log, fast=True)
        assert fed.total == log.final_score and fed.n_steps == 0


@pytest.mark.skip(reason="TODO: the full (trajectory) replay has only been run on one S1 session (score matched, sensor overlap 0.986 with visibility.py); "
                         "check it on every participant and session when the choice-set or memory analyses need it")
def test_the_full_replay_of_every_participant_session_matches_the_log_and_visibility():
    for path in FINISHED:
        log = replay.load_session_log(Path(path).parent)
        world = human_agents.session_world(log)
        fed = human_agents.replay_into_agent(REGISTRY["learner"](), log, world=world)
        assert fed.total == log.final_score and fed.unseen_harvests == []
        assert human_agents.compare_with_visibility(log, world=world)["jaccard"] > 0.9


def test_the_interlude_summary_counts_agreement_where_the_participant_was_right_and_wrong():
    def row(me, agent, correct):
        return {"participant": me, "participant_correct": None if me is None else me == correct, "agent": agent, "agent_correct": agent == correct}
    s = human_agents.summarize_interlude([row("left", "left", "left"), row("right", "left", "left"), row("right", "right", "left"), row(None, "left", "left")])
    assert (s["trials"], s["answered"]) == (4, 3) and s["participant_accuracy"] == pytest.approx(1 / 3) and s["agent_accuracy"] == pytest.approx(2 / 3)
    assert s["agreement"] == pytest.approx(2 / 3) and s["agreement_when_participant_right"] == 1.0 and s["agreement_when_participant_wrong"] == 0.5


@pytest.mark.skipif(not FINISHED, reason="no participant data in ForagingData/")
def test_a_participants_interlude_is_answered_trial_by_trial_by_the_agent_that_learned_from_their_session():
    for path in FINISHED:
        folder = Path(path).parent
        log = replay.load_session_log(folder)
        if log.final_score is None or not _asset_exists(log) or not human_agents.interlude_folder(folder).exists():
            continue
        fed = human_agents.replay_into_agent(REGISTRY["gp_mean"](), log, fast=True)
        rows = human_agents.interlude_comparison(fed.agent, human_agents.interlude_folder(folder))
        assert [r["order"] for r in rows] == sorted(r["order"] for r in rows) and {r["agent"] for r in rows} <= {"left", "right"}
        assert all(np.isfinite(r["margin"]) for r in rows)
        assert human_agents.summarize_interlude(rows)["agent_accuracy"] >= 0.5      # (a critic that has learned this session's rule is not at chance)
        return
    pytest.skip("no finished session with an Interlude")
