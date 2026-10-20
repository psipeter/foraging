"""Foraging agents. All agents live in this file; add new ones with @register.

An agent is run by sim.run_episode with this protocol:

    begin_session(world, rng)      once per session; `world` is the full World (positions, attributes, values,
                                   canopy radii) and `rng` a numpy Generator seeded per world seed. Agents
                                   currently get full information; restrict what they read to model a percept.
    choose_target(state) -> id|None  pick the next bush (must not be depleted) or None to stop. `state` is
                                   sim.State: time_left, pos, depleted, fruits_taken, history, travel_times().
    keep_harvesting(state, id, reward) -> bool   called after each fruit except the last; False leaves the bush.
    end_session(result)            hook for learning across sessions.
"""

REGISTRY = {}


def register(name):
    """Class decorator: make the agent available to the sim.py command line by `name`."""
    def deco(cls):
        REGISTRY[name] = cls
        return cls
    return deco


class Agent:
    def begin_session(self, world, rng):
        self.world = world
        self.rng = rng

    def choose_target(self, state):
        raise NotImplementedError

    def keep_harvesting(self, state, bush, reward):
        return True

    def end_session(self, result):
        pass
