import numpy as np
import pytest

import specs
from agents import (REGISTRY, Actor, ComposedAgent, DeltaRuleCritic, FullKnowledge, FullMemory, NeutralPrior, OracleCritic,
                    PlannerActor, RBFFeatures, Softmax, UtilityActor, build_agent)
from perception import ConePercept, NullPercept
from sim import run_episode
from test_agents import Script, world_with


def spec_of(name):
    return REGISTRY[name]().spec()


# --- round trip and identity ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_every_registered_agent_round_trips_through_its_spec(name):
    spec = spec_of(name)
    assert build_agent(spec).spec() == spec
    assert specs.spec_hash(build_agent(spec).spec()) == specs.spec_hash(spec)


def test_a_rebuilt_agent_plays_exactly_like_the_original():
    w = world_with([[5, 0], [-6, 0], [0, 9]], rewards=[[2, 4, 6], [8, 8, 8], [1, 1, 1]],
                   attrs=[[0.2, 0.5, 0.5], [0.8, 0.5, 0.5], [0.5, 0.5, 0.5]])
    for name in ("nearest", "greedy_rate_10", "plan_beam", "delta_rate_10"):
        original = REGISTRY[name]()
        rebuilt = build_agent(original.spec())
        a, b = run_episode(original, w), run_episode(rebuilt, w)
        assert a.total == b.total and a.trace == b.trace


def test_the_spec_is_plain_json_with_defaults_resolved():
    spec = spec_of("delta_rate_10")
    assert specs.canonical_json(spec) == specs.canonical_json(__import__("json").loads(specs.canonical_json(spec)))
    assert spec["critic"] == {"type": "DeltaRuleCritic", "alpha": 0.5,
                              "features": {"type": "RBFFeatures", "length_scale": 0.3, "n_centers": 8, "additive": True},
                              "prior": {"type": "NeutralPrior", "initial": 1}}
    assert spec["actor"]["choice"] == {"type": "Argmax"}                     # the actor's default choice rule is reported
    assert spec["percept"] is None and spec["memory"] == {"type": "FullMemory"}


def test_changing_any_parameter_changes_the_hash_and_equal_agents_share_it():
    base = ComposedAgent(UtilityActor("rate", 10.0), DeltaRuleCritic(alpha=0.5), FullMemory())
    same = ComposedAgent(UtilityActor("rate", 10), DeltaRuleCritic(RBFFeatures(), NeutralPrior(), 0.5), FullMemory())
    assert base.spec_hash() == same.spec_hash()                              # 10 vs 10.0 and explicit defaults are the same agent
    variants = [ComposedAgent(UtilityActor("rate", 10.0), DeltaRuleCritic(alpha=0.2), FullMemory()),
                ComposedAgent(UtilityActor("rate", 10.0), DeltaRuleCritic(RBFFeatures(length_scale=0.2)), FullMemory()),
                ComposedAgent(UtilityActor("rate", 10.0), DeltaRuleCritic(prior=NeutralPrior(2.0)), FullMemory()),
                ComposedAgent(UtilityActor("value", 10.0), DeltaRuleCritic(), FullMemory()),
                ComposedAgent(UtilityActor("rate", 10.0, Softmax(0.5)), DeltaRuleCritic(), FullMemory()),
                ComposedAgent(UtilityActor("rate", 10.0), DeltaRuleCritic(), FullMemory(), ConePercept(60, 50))]
    hashes = {base.spec_hash()} | {v.spec_hash() for v in variants}
    assert len(hashes) == len(variants) + 1
    assert len(base.spec_hash()) == 12


def test_the_hash_of_a_plain_agent_is_pinned():
    # If this fails you changed a component's parameters or a default: every agent using it has a new identity. That is intended
    # when done on purpose (re-hash stored results from their spec JSON, see CLAUDE.md "Results database"); then update this value.
    assert specs.spec_hash(spec_of("nearest")) == "ec2396541b09"


def test_numbers_are_canonical_whatever_their_type():
    assert specs.spec_hash({"a": 10}) == specs.spec_hash({"a": 10.0}) == specs.spec_hash({"a": np.float64(10.0)})
    assert specs.spec_hash({"a": 0.5}) == specs.spec_hash({"a": np.float32(0.5)})
    assert specs.spec_hash({"a": True}) != specs.spec_hash({"a": 1})
    assert specs.canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


# --- what a spec can hold ------------------------------------------------------------------------------------------

def test_a_component_with_something_unwritable_has_no_spec():
    with pytest.raises(specs.SpecError):
        UtilityActor(lambda view: -view.travel_times()).spec()
    with pytest.raises(specs.SpecError):
        Script(object()).spec()


def test_planner_and_percepts_report_their_parameters():
    assert PlannerActor("beam", beam_width=50).spec() == {"type": "PlannerActor", "method": "beam", "beam_width": 50,
                                                            "max_nodes": 2000000, "incumbent_width": 150}
    assert ConePercept(90, 40).spec() == {"type": "ConePercept", "angle": 90, "distance": 40}
    assert NullPercept().spec() == {"type": "NullPercept"}
    assert isinstance(build_agent(ComposedAgent(UtilityActor("nearest"), OracleCritic(), FullKnowledge(), NullPercept()).spec()).percept,
                      NullPercept)


def test_the_outermost_constructor_call_is_recorded():
    class Hot(Softmax):
        def __init__(self, scale=2.0):
            super().__init__(temperature=scale * 10)
            self.scale = scale

    spec = Hot(3.0).spec()
    assert spec == {"type": "Hot", "scale": 3}                              # not the inner Softmax temperature


def test_only_library_classes_build_without_being_named():
    class Mine(Actor):
        def __init__(self, k=1):
            self.k = k

    spec = Mine(2).spec()
    with pytest.raises(specs.SpecError):
        specs.build(spec)
    assert specs.build(spec, extra={"Mine": Mine}).k == 2
    with pytest.raises(specs.SpecError):
        specs.build({"type": "NoSuchThing"})


def test_a_parameter_called_type_is_refused():
    class Typed(Actor):
        def __init__(self, type="x"):
            self.type = type

    with pytest.raises(specs.SpecError):
        Typed().spec()


# --- flattening and labels -----------------------------------------------------------------------------------------

def test_flatten_gives_one_entry_per_parameter():
    flat = specs.flatten(spec_of("delta_rate_10"))
    assert flat["critic.alpha"] == 0.5 and flat["critic.features.length_scale"] == 0.3
    assert flat["actor.utility"] == "rate" and flat["actor.choice.type"] == "Argmax" and flat["percept"] is None


def test_labels_show_only_what_differs():
    def agent(alpha=0.5, features=None):
        return ComposedAgent(UtilityActor("rate", 10.0), DeltaRuleCritic(features, None, alpha), FullMemory()).spec()

    assert specs.labels([agent(0.2), agent(0.5)]) == ["alpha=0.2", "alpha=0.5"]
    assert specs.labels([agent(), agent(features=RBFFeatures(length_scale=0.2))]) == ["length_scale=0.3", "length_scale=0.2"]
    assert specs.labels([agent(), agent()]) == ["same", "same"]
    mixed = specs.labels([spec_of("nearest"), spec_of("greedy_rate_10"), spec_of("delta_rate_10")])
    assert len(set(mixed)) == 3 and mixed[0] != "same"


def test_labels_leave_out_the_parameters_of_a_component_whose_type_differs():
    def delta_agent(alpha):
        return ComposedAgent(UtilityActor("rate", 10.0), DeltaRuleCritic(alpha=alpha), FullMemory()).spec()

    mixed = specs.labels([spec_of("nearest"), delta_agent(0.2), delta_agent(0.5)])
    assert len(set(mixed)) == 3
    assert mixed[0] == "OracleCritic, FullKnowledge, max_walk_time=None, utility=nearest"      # no alpha, features or prior fields
    assert mixed[1].startswith("DeltaRuleCritic, FullMemory") and mixed[1].endswith("alpha=0.2") and "alpha=0.5" in mixed[2]
    assert "length_scale" not in mixed[1]
