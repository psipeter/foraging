"""Foraging agents. All agents live in this file; add new ones with REGISTRY.

An agent is three components plus a sensor, composed by `ComposedAgent` and run by sim.run_episode:

    Memory  what the agent keeps about the bushes it has seen and the rewards it has received. It is the constraint on
            the other two (and the only way anything the agent sees reaches them): the actor may only use `memory` (the map: positions, attributes, spent or not, the fruits
            taken), and the critic may only learn from `memory.experiences()` (attributes and reward, one per fruit).
            FullKnowledge is preloaded with the whole map; FullMemory accumulates everything it sees and receives.
    Critic  the value representation and its learning rule: value(attributes) -> (mean reward per fruit, uncertainty),
            fit from memory, freezable. OracleCritic is "full knowledge": the true reward function.
    Actor   the policy: what to do next (Harvest a known bush, Explore, Look, Stop) and whether to leave a bush after a
            fruit. Its choices go through a ChoiceRule (hard-max or softmax) and any value it uses (value, rate) is
            derived from the critic, never read from the world.
    Percept the sensor: which bushes are in view. It belongs to the environment, not the agent: perception.py defines it and the
            engine applies it (by default a cone as wide as the session camera), so every agent senses the same world the
            same way; an agent may carry its own `percept` as an override. Walking, exploring and looking are actions of the
            actor, not part of the percept.

`nearest`, `greedy_*` and `plan_*` are actors with the oracle critic and full-knowledge memory. A learning agent swaps
the critic and memory; the actor code is the same. Agents are built by zero-argument factories in
REGISTRY (a fresh agent per world).

What an agent may know is explicit. Components learn about the task through `begin(task)` (rules and speeds, no bush
positions); they see the world only through observations the engine gives them, and the engine's state only through a `Body`
(position, heading, time left, total reward). Components that start with the world's own knowledge (FullKnowledge,
OracleCritic) are flagged `omniscient = True` and are the only ones granted a `WorldKnowledge` (`grant`), so a learning
critic or a limited memory cannot reach it. After a session `ComposedAgent.begin_interlude` gives the agent a fresh memory
for the Interlude, freezes the critic and carries it over.
"""

import copy
from dataclasses import dataclass

import numpy as np

import costs
from specs import Component, SpecError, build, spec_hash
from world import bush_value

REGISTRY = {}   # name -> zero-argument agent factory
INTERLUDE_TIME_TIE = 0.01   # seconds: travel times to the two bushes of an Interlude trial closer than this are a tie


# --------------------------------------------------------------------------------------------------
# Actions (what an actor returns; the engine executes them and charges time)
# --------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Harvest:
    """Walk to the edge of this bush's harvest range and harvest it, fruit by fruit, until the actor leaves or it is empty."""
    bush: int


@dataclass(frozen=True)
class Explore:
    """Walk `distance` units along `bearing` (degrees about +Y from +Z toward +X; the game's yaw), looking where it goes."""
    bearing: float
    distance: float


@dataclass(frozen=True)
class Look:
    """Turn the view by `angle` degrees (+ = right); costs costs.TURN_OVERHEAD + |angle| / costs.TURN_RATE seconds. A zero angle
    is refused (an action that costs nothing)."""
    angle: float


@dataclass(frozen=True)
class Stop:
    """End the session's activity (the remaining time is idle)."""


# --------------------------------------------------------------------------------------------------
# What crosses the boundary between the engine and the agent
# --------------------------------------------------------------------------------------------------

@dataclass
class Body:
    """What an actor may read of the engine each decision: where the agent stands and faces, the clock and its score so far.
    A snapshot (the engine hands over a copy of the position)."""
    pos: np.ndarray
    heading: float
    time_left: float
    total: float


@dataclass
class WorldKnowledge:
    """What a full-knowledge component is granted: every bush's position, size and attributes, the true mean reward per fruit
    of each bush (None when unknown) and the reward function (None when unknown). Only components flagged `omniscient`
    ever receive it."""
    pos: np.ndarray
    radius: np.ndarray
    attrs: np.ndarray
    values: object = None
    reward_function: object = None

    def __post_init__(self):
        # Own, read-only copies: a component that is granted the knowledge can read it but can neither change the world it
        # came from (worlds are shared across the agents of a comparison) nor see later changes to it.
        for name in ("pos", "radius", "attrs", "values"):
            value = getattr(self, name)
            if value is not None:
                value = np.array(value, dtype=float, copy=True)
                value.flags.writeable = False
                setattr(self, name, value)

    @property
    def n(self):
        return len(self.pos)

    @classmethod
    def from_world(cls, world):
        attrs = np.column_stack([world.shape, world.color, world.moisture])
        return cls(np.asarray(world.pos, dtype=float), np.asarray(world.canopy_radius, dtype=float), attrs,
                   getattr(world, "value", None), getattr(world.params, "reward_function", None))

    @classmethod
    def from_sidecar(cls, sidecar):
        """The Interlude's bush table (interlude.generate_interlude), whose `value` is each bush's true reward per fruit."""
        n = len(sidecar["canopyRadius"])
        attrs = np.column_stack([sidecar["shape"], sidecar["color"], sidecar["moisture"]]).astype(float)
        values = np.asarray(sidecar["value"], dtype=float) if "value" in sidecar else None
        return cls(np.asarray(sidecar["treePos"], dtype=float).reshape(n, 2), np.asarray(sidecar["canopyRadius"], dtype=float),
                   attrs, values, None)


# --------------------------------------------------------------------------------------------------
# Memory
# --------------------------------------------------------------------------------------------------

class Memory(Component):
    """Dense per-bush records indexed by bush id (arrays of length n; `known` says which are in memory) plus the reward
    list of every fruit taken from each bush. This base class starts empty and does not forget; subclasses set what is
    known at the start or apply limits.

    Readers: `known`, `pos` (n, 2), `radius`, `attrs` (n, 3: shape, color, moisture), `depleted` (seen spent or emptied
    by the agent), `taken` (fruits the agent took from each bush), `rewards[j]` (list, one per fruit taken from bush j),
    `experiences()`. `map_version` increases whenever a bush is added to the map; `experience_version` whenever a reward
    is recorded (a critic refits when it changes).
    """
    omniscient = False    # True for memories that are granted the world's own knowledge (see grant)

    def begin(self, task):
        """Start empty. `task` supplies only the capacity (the number of bush ids) and the fruit count per bush."""
        n = task.n_bushes
        self.n = n
        self.fruit_count = task.fruit_count
        self.known = np.zeros(n, dtype=bool)
        self.pos = np.zeros((n, 2))
        self.radius = np.zeros(n)
        self.attrs = np.zeros((n, 3))
        self.depleted = np.zeros(n, dtype=bool)
        self.taken = np.zeros(n, dtype=int)
        self.rewards = [[] for _ in range(n)]
        self.map_version = 0
        self.experience_version = 0

    def fresh(self):
        """A new, empty memory of the same kind (the Interlude starts one). A memory with constructor arguments overrides this."""
        return type(self)()

    def observe(self, obs):
        """Take in an Observation (perception.Observation): the bushes in view this moment, with their attributes and whether each
        looks spent."""
        if len(obs.ids) == 0:
            return
        new = obs.ids[~self.known[obs.ids]]
        if len(new):
            self.known[new] = True
            sel = np.isin(obs.ids, new)
            self.pos[obs.ids[sel]] = obs.pos[sel]
            self.radius[obs.ids[sel]] = obs.radius[sel]
            self.attrs[obs.ids[sel]] = obs.attrs[sel]
            self.map_version += 1
        self.depleted[obs.ids[obs.depleted]] = True

    def record_reward(self, bush, reward):
        self.rewards[bush].append(float(reward))
        self.taken[bush] += 1
        self.experience_version += 1

    def mark_depleted(self, bush):
        self.depleted[bush] = True

    def total_reward(self):
        return float(sum(map(sum, self.rewards)))

    def mean_reward(self):
        """Mean reward per fruit over every fruit taken so far (0 before the first)."""
        taken = int(self.taken.sum())
        return self.total_reward() / taken if taken else 0.0

    def experiences(self):
        """(attrs (m, 3), rewards (m,), ids (m,)): one row per fruit the agent has taken (and still remembers)."""
        ids = np.array([j for j in range(self.n) for _ in self.rewards[j]], dtype=int)
        rewards = np.array([r for j in range(self.n) for r in self.rewards[j]], dtype=float)
        return self.attrs[ids], rewards, ids

    def bush_stats(self):
        """(ids, attrs, n, mean, var) for every bush the agent has taken fruit from: fruits taken, their mean reward and the
        (unbiased) variance within the bush (0 with a single fruit). The statistics a critic learns from at bush level."""
        ids = np.array([j for j in range(self.n) if self.rewards[j]], dtype=int)
        n = np.array([len(self.rewards[j]) for j in ids], dtype=int)
        mean = np.array([np.mean(self.rewards[j]) for j in ids], dtype=float)
        var = np.array([np.var(self.rewards[j], ddof=1) if len(self.rewards[j]) > 1 else 0.0 for j in ids], dtype=float)
        return ids, self.attrs[ids], n, mean, var

    def fruits_left(self):
        return self.fruit_count - self.taken


class FullKnowledge(Memory):
    """Preloaded with every bush's position, size and attributes (no rewards): what the oracle agents start with. It is
    granted the world's knowledge, so it is flagged omniscient."""
    omniscient = True

    def grant(self, knowledge):
        self.known[:] = True
        self.pos[:] = knowledge.pos
        self.radius[:] = knowledge.radius
        self.attrs[:] = knowledge.attrs
        self.map_version = 0


class FullMemory(Memory):
    """Starts empty; remembers every bush it has seen and every reward it has received, perfectly and forever."""


# --------------------------------------------------------------------------------------------------
# Critic
# --------------------------------------------------------------------------------------------------

class Critic(Component):
    """Value representation and learning rule. `value(attrs, ids=None) -> (mean, sd)` per bush: expected reward per fruit
    and the critic's uncertainty about it. `ids` identify the bushes (a participant can tell the bushes it has seen apart);
    learned critics use the attributes only, and an oracle may look the ids up in what it was granted (in the Interlude only an
    omniscient critic is given ids: the session's bush ids mean nothing there). `version` changes whenever the value function
    does: `update` bumps it after every refit of a critic that learns (one that overrides `_fit`)."""
    version = 0
    frozen = False
    omniscient = False    # True for critics that are granted the world's own knowledge (see grant)
    update_on = "fruit"   # when ComposedAgent calls `update`: after every "fruit", or when a visit to a "bush" ends

    def begin(self, task):
        pass

    def update(self, memory):
        """Learn from what memory now holds, unless frozen. A critic that learns (overrides `_fit`) has changed afterwards, so
        its `version` is bumped here and an actor that caches work on it (the planner) knows to redo it."""
        if not self.frozen and type(self)._fit is not Critic._fit:
            self._fit(memory)
            self.version += 1

    def _fit(self, memory):
        pass

    def freeze(self):
        """Stop learning (the Interlude shows no outcomes, so humans do not learn there either)."""
        self.frozen = True

    def value(self, attrs, ids=None):
        raise NotImplementedError

    def sample(self, attrs, rng):
        """One draw of the values of `attrs` from the critic's belief (a critic with no uncertainty reports its mean). The values of the
        bushes in one draw are jointly consistent: a draw is one possible reward function, not independent guesses."""
        return self.value(attrs)[0]


class OracleCritic(Critic):
    """Full knowledge of the reward function: R_bush of each bush (looked up by id in what it was granted, else computed from
    the attributes with the reward function), with no uncertainty. It is granted the world's knowledge, so it is flagged
    omniscient."""
    omniscient = True

    def grant(self, knowledge):
        self.values = knowledge.values
        self.reward_function = knowledge.reward_function

    def value(self, attrs, ids=None):
        attrs = np.asarray(attrs, dtype=float)
        if ids is not None and self.values is not None:
            mean = np.asarray(self.values, dtype=float)[np.asarray(ids)]
        else:
            mean = np.asarray(bush_value(self.reward_function, attrs[:, 0], attrs[:, 1], attrs[:, 2]), dtype=float)
        return mean, np.zeros(len(mean))


# --------------------------------------------------------------------------------------------------
# A learning critic: prediction-error (delta rule) learning on a feature representation of the attributes
# --------------------------------------------------------------------------------------------------

class Prior(Component):
    """What a learning critic believes where its features say nothing (before any data, far from every bush it has tried): a
    baseline `value(memory)`, the same for every bush. Swappable (an optimistic prior would be an exploration mechanism)."""

    def value(self, memory):
        raise NotImplementedError


class NeutralPrior(Prior):
    """No opinion: `initial` (a small positive number) until a bush has been harvested, then the mean of the bush means so far.
    The scale of `initial` does not matter for a rate utility (every bush is then worth the same), only that it is positive."""

    def __init__(self, initial=1.0):
        self.initial = float(initial)

    def value(self, memory):
        _, _, _, mean, _ = memory.bush_stats()
        return float(mean.mean()) if len(mean) else self.initial


class ConstantPrior(Prior):
    """A fixed baseline, whatever has been seen: the weights then carry the whole level of the values, and a region with no experience
    looks like `level`. The default of DeltaRuleCritic (0.1). (NeutralPrior follows the mean of the bush means instead.)"""

    def __init__(self, level=1.0):
        self.level = float(level)

    def value(self, memory):
        return self.level


class Features(Component):
    """A representation of the attributes: `features(attrs (n, 3)) -> (n, dim)`, rows scaled to unit length, so that
    `phi(x) . phi(x')` is a kernel with k(x, x) = 1 and one delta-rule step of size alpha moves the prediction at x' by
    alpha * error * k(x, x')."""

    def __call__(self, attrs):
        phi = np.asarray(self._raw(np.asarray(attrs, dtype=float)), dtype=float)
        return phi / np.maximum(np.linalg.norm(phi, axis=1, keepdims=True), 1e-12)

    def _raw(self, attrs):
        raise NotImplementedError

    @property
    def dim(self):
        return self(np.zeros((1, 3))).shape[1]


class RBFFeatures(Features):
    """Gaussian bumps of width `length_scale` on a grid of `n_centers` per attribute over [0, 1]. additive=True (default): each
    attribute has its own bumps and the features are concatenated, so the learned function is a sum of one function per attribute
    (the structure of the reward function). additive=False: bumps on the joint grid (n_centers ** 3), which can represent
    interactions but needs far more data."""

    def __init__(self, length_scale=0.3, n_centers=8, additive=True):
        self.length_scale = float(length_scale)
        self.centers = np.linspace(0.0, 1.0, int(n_centers))
        self.additive = additive
        if not additive:
            grid = np.meshgrid(*[self.centers] * 3, indexing="ij")
            self._joint = np.stack([g.ravel() for g in grid], axis=1)

    def _raw(self, attrs):
        s2 = 2.0 * self.length_scale ** 2
        if self.additive:
            d = attrs[:, :, None] - self.centers[None, None, :]
            return np.exp(-d ** 2 / s2).reshape(len(attrs), -1)
        d2 = ((attrs[:, None, :] - self._joint[None, :, :]) ** 2).sum(-1)
        return np.exp(-d2 / s2)


class Replay(Component):
    """How a critic that learns online presents what memory holds again, after it has learned from the bush it just finished: `indices(errors)`
    returns which stored bushes (indices into the stored-bush arrays, ordered by bush id, which the world shuffles, so the order carries no
    structure) to learn from once more, in order. `errors` are the stored bushes' current prediction errors (bush mean minus value), which a
    policy may use or ignore. Swappable, like Prior and Features; the delta-rule critic takes one (None: no replay, and no entry in its spec)."""

    def begin(self):
        """Called when a session starts (a policy with its own random stream restarts it here)."""

    def indices(self, errors):
        raise NotImplementedError


class FullSweeps(Replay):
    """`epochs` extra passes over every stored bush, in a fixed order. With many passes a fixed-step online rule converges to the least-squares
    fit of its model; the number of passes then sets how far it is pulled to the data (early stopping acts as regularisation)."""

    def __init__(self, epochs=1):
        self.epochs = int(epochs)

    def indices(self, errors):
        return np.tile(np.arange(len(errors)), self.epochs)


class SampledReplay(Replay):
    """`steps` stored bushes drawn uniformly with replacement per update, from its own stream (restarted each session, so a run is reproducible
    from `seed`)."""

    def __init__(self, steps=20, seed=0):
        self.steps, self.seed = int(steps), int(seed)
        self._rng = np.random.default_rng(self.seed)

    def begin(self):
        self._rng = np.random.default_rng(self.seed)

    def indices(self, errors):
        return self._rng.integers(0, len(errors), self.steps) if len(errors) else np.zeros(0, dtype=int)


class PrioritizedReplay(Replay):
    """The `steps` stored bushes with the largest current prediction error, largest first: the ones the critic fits worst."""

    def __init__(self, steps=5):
        self.steps = int(steps)

    def indices(self, errors):
        return np.argsort(-np.abs(errors), kind="stable")[:self.steps]


class DeltaRuleCritic(Critic):
    """TD(0) with nothing to bootstrap from (a bush's state does not change while it is harvested), i.e. the Rescorla-Wagner delta
    rule: value(x) = prior + w . phi(x), and after each bush, w += alpha * (bush mean reward - value(x_bush)) * phi(x_bush).
    The default prior is a small fixed baseline (ConstantPrior(0.1)): the weights then carry the whole level of the values, and a region
    with no experience looks like 0.1 (small but positive, so the rate utility still ranks unseen bushes by travel time; a larger
    constant acts as an optimism bonus, which belongs to the actor). NeutralPrior, the running mean of the bush means, is the
    alternative: the features then learn deviations from a moving level, and the first bush harvested teaches the baseline and nothing
    else. Learns once per bush (a fruit
    list is summarized by its mean), from the bush's own fruits taken since the last update; a bush that is visited again is
    learned from again, against its mean over all fruits taken. No uncertainty is reported (sd = 0). (A read-out `gain` on the learned deviation
    existed to test whether under-scaled values held the learner back; it was removed once replay showed the cause was convergence.)"""
    update_on = "bush"

    def __init__(self, features=None, prior=None, alpha=0.5, replay=None):
        self.features = features if features is not None else RBFFeatures()
        self.prior = prior if prior is not None else ConstantPrior(0.1)
        self.alpha = float(alpha)
        self.replay = replay
        self.w = np.zeros(self.features.dim)
        self._baseline = None
        self._learned = np.zeros(0, dtype=int)

    def params(self):
        p = {"features": self.features, "prior": self.prior, "alpha": self.alpha}
        if self.replay is not None:
            p["replay"] = self.replay           # absent when there is none, so the spec (and hash) of a critic without replay is what it was
        return p

    def begin(self, task):
        self.w = np.zeros(self.features.dim)
        self._baseline = None
        self._learned = np.zeros(task.n_bushes, dtype=int)
        if self.replay is not None:
            self.replay.begin()

    def _fit(self, memory):
        self._baseline = self.prior.value(memory)
        ids, attrs, n, mean, _ = memory.bush_stats()
        for i, j in enumerate(ids):
            if n[i] > self._learned[j]:
                phi = self.features(attrs[i:i + 1])[0]
                error = mean[i] - (self._baseline + self.w @ phi)
                self.w = self.w + self.alpha * error * phi
                self._learned[j] = n[i]
        if self.replay is not None and len(ids):
            phis = self.features(attrs)
            for i in self.replay.indices(mean - (self._baseline + phis @ self.w)):
                self.w = self.w + self.alpha * (mean[i] - (self._baseline + self.w @ phis[i])) * phis[i]

    def value(self, attrs, ids=None):
        attrs = np.asarray(attrs, dtype=float)
        base = self._baseline if self._baseline is not None else 0.0
        return base + self.features(attrs) @ self.w, np.zeros(len(attrs))


# --------------------------------------------------------------------------------------------------
# A Bayesian critic: a Gaussian process over the attributes, with its uncertainty
# --------------------------------------------------------------------------------------------------

class Kernel(Component):
    """Similarity of two sets of attributes (in [0, 1]^3), `matrix(a, b) -> (len(a), len(b))`, with k(x, x) = 1. Swappable for the GP critic."""

    def matrix(self, a, b):
        raise NotImplementedError


class RBFKernel(Kernel):
    """Gaussian kernel of width `length_scale` (attribute units). additive=True (default): the mean of one 1-D Gaussian kernel per
    attribute, so the learned function is a sum of one smooth function per attribute (the structure of the reward function) and what is
    learned about one attribute carries over to bushes that differ in the others; additive=False: one isotropic kernel on the three
    attributes jointly (Wu et al. 2018), which can represent interactions but needs far more data."""

    def __init__(self, length_scale=0.3, additive=True):
        self.length_scale = float(length_scale)
        self.additive = bool(additive)

    def matrix(self, a, b):
        d2 = (np.asarray(a, dtype=float)[:, None, :] - np.asarray(b, dtype=float)[None, :, :]) ** 2
        s2 = 2.0 * self.length_scale ** 2
        return np.exp(-d2 / s2).mean(axis=2) if self.additive else np.exp(-d2.sum(axis=2) / s2)


class FeatureKernel(Kernel):
    """The similarity of a set of `features` (default RBFFeatures): `phi(x) . phi(x')`, with unit-length features so that k(x, x) = 1. A GP with this
    kernel is Bayesian linear regression on those features: the same model as the delta-rule critic with the same features, solved exactly."""

    def __init__(self, features=None):
        self.features = features if features is not None else RBFFeatures()

    def matrix(self, a, b):
        if len(a) == 0 or len(b) == 0:
            return np.zeros((len(a), len(b)))          # no data yet
        return self.features(np.asarray(a, dtype=float)) @ self.features(np.asarray(b, dtype=float)).T


MIN_NOISE_VAR = 1e-4    # the GP critic's observation-noise variance never goes below this (Wu et al. 2018 fix 1e-4)


class GPCritic(Critic):
    """Gaussian-process regression of a bush's mean reward per fruit on its attributes, with `kernel`. Each bush is one observation, the
    mean of the fruits taken from it, with noise variance sigma^2 / n (n fruits). Everything the prior and the noise need comes from
    what the memory holds: the prior mean is the mean of the bush means so far (`prior_mean` fixes it instead), the prior sd is the
    spread of the bush means beyond what the noise explains (at least `min_std`), and sigma^2 is the within-bush variance pooled over
    the bushes with two or more fruits. Before there is enough to estimate them (no bush, fewer than three bushes, no bush with two
    fruits) it uses `initial_mean`, `initial_std` and `initial_noise_std`. The value of an attribute vector is the posterior mean and
    its uncertainty the posterior sd of the function (not of a fruit, so the reward noise does not look like something to explore).
    `sample` draws a whole function from the posterior (one draw is jointly consistent across bushes), for Thompson sampling. Learns once
    per bush, as the delta-rule critic.

    The estimates can be switched off to match another critic: `prior_std` and `noise_std` fix the prior sd and the noise sd (the ratio is the
    regularisation: how far a bush pulls the fit towards its own mean), and `weight_by_count=False` treats every bush as the mean of a full
    bush's fruits (noise variance sigma^2 / fruit count) whatever the number actually taken, so what changes is the relative weight of a partly
    harvested bush, not the overall noise scale."""
    update_on = "bush"

    def __init__(self, kernel=None, prior_mean=None, initial_mean=0.1, initial_std=1.0, initial_noise_std=0.3, min_std=0.1,
                 weight_by_count=True, prior_std=None, noise_std=None):
        self.kernel = kernel if kernel is not None else RBFKernel()
        self.prior_mean = None if prior_mean is None else float(prior_mean)
        self.initial_mean, self.initial_std = float(initial_mean), float(initial_std)
        self.initial_noise_std, self.min_std = float(initial_noise_std), float(min_std)
        self.weight_by_count = bool(weight_by_count)
        self.prior_std = None if prior_std is None else float(prior_std)
        self.noise_std = None if noise_std is None else float(noise_std)
        self._reset()

    def params(self):
        return {"kernel": self.kernel, "prior_mean": self.prior_mean, "initial_mean": self.initial_mean, "initial_std": self.initial_std,
                "initial_noise_std": self.initial_noise_std, "min_std": self.min_std, "weight_by_count": self.weight_by_count,
                "prior_std": self.prior_std, "noise_std": self.noise_std}

    def _reset(self):
        self._X = np.zeros((0, 3))
        self._m0 = self.initial_mean
        self._s0 = self.prior_std if self.prior_std is not None else self.initial_std
        self._noise2 = (self.noise_std if self.noise_std is not None else self.initial_noise_std) ** 2
        self._L, self._alpha = np.zeros((0, 0)), np.zeros(0)       # no data: the posterior is the prior

    def begin(self, task):
        self._reset()

    def _fit(self, memory):
        _, X, n, mean, var = memory.bush_stats()
        dof = n - 1
        if self.noise_std is not None:
            noise2 = self.noise_std ** 2
        else:
            noise2 = max(float((dof * var).sum() / dof.sum()), MIN_NOISE_VAR) if (dof > 0).any() else self.initial_noise_std ** 2
        self._noise2 = noise2
        observed = noise2 / n if self.weight_by_count else np.full(len(n), noise2 / memory.fruit_count)      # noise variance of each bush's mean
        self._m0 = self.prior_mean if self.prior_mean is not None else (float(mean.mean()) if len(mean) else self.initial_mean)
        if self.prior_std is not None:
            self._s0 = self.prior_std
        elif len(mean) >= 3:
            self._s0 = float(np.sqrt(max(np.var(mean, ddof=1) - np.mean(observed), self.min_std ** 2)))
        else:
            self._s0 = self.initial_std
        self._X = np.array(X, dtype=float)
        K = self._s0 ** 2 * self.kernel.matrix(self._X, self._X) + np.diag(observed)
        self._L = np.linalg.cholesky(K)
        self._alpha = np.linalg.solve(self._L.T, np.linalg.solve(self._L, mean - self._m0))

    def _posterior(self, attrs, full_cov=False):
        attrs = np.asarray(attrs, dtype=float)
        Ks = self._s0 ** 2 * self.kernel.matrix(attrs, self._X)
        mean = self._m0 + Ks @ self._alpha
        V = np.linalg.solve(self._L, Ks.T)
        if full_cov:
            return mean, self._s0 ** 2 * self.kernel.matrix(attrs, attrs) - V.T @ V
        return mean, self._s0 ** 2 - (V * V).sum(axis=0)

    def value(self, attrs, ids=None):
        mean, var = self._posterior(attrs)
        return mean, np.sqrt(np.maximum(var, 0.0))

    def sample(self, attrs, rng):
        mean, cov = self._posterior(attrs, full_cov=True)
        w, v = np.linalg.eigh((cov + cov.T) / 2.0)
        return mean + v @ (np.sqrt(np.maximum(w, 0.0)) * rng.standard_normal(len(mean)))


# --------------------------------------------------------------------------------------------------
# Choice rules (part of the actor)
# --------------------------------------------------------------------------------------------------

class ChoiceRule(Component):
    """Maps a utility vector (-inf = not a candidate) to a pick. `probs` is the distribution the rule samples from, so
    likelihoods of observed choices can be computed later."""

    def probs(self, utilities, random_ties=False):
        raise NotImplementedError

    def pick(self, utilities, rng, random_ties=False):
        """Index of the pick, or None when nothing is a candidate."""
        u = np.asarray(utilities, dtype=float)
        if not np.isfinite(u).any():
            return None
        return self._pick(u, rng, random_ties)

    def _pick(self, u, rng, random_ties):
        return int(rng.choice(len(u), p=self.probs(u, random_ties)))


class Argmax(ChoiceRule):
    """Hard-max. Ties go to the lowest index (as the original agents did) unless `random_ties`."""

    def probs(self, utilities, random_ties=False):
        u = np.asarray(utilities, dtype=float)
        p = np.zeros(len(u))
        if not np.isfinite(u).any():
            return p
        if random_ties:
            top = np.flatnonzero(u >= u.max() - 1e-12)
            p[top] = 1.0 / len(top)
        else:
            p[int(np.argmax(u))] = 1.0
        return p

    def _pick(self, u, rng, random_ties):
        if random_ties:
            return int(rng.choice(np.flatnonzero(u >= u.max() - 1e-12)))
        return int(np.argmax(u))


class Softmax(ChoiceRule):
    """P(i) proportional to exp(u_i / temperature) over the candidates."""

    def __init__(self, temperature=1.0):
        if temperature <= 0:
            raise ValueError("softmax temperature must be positive")
        self.temperature = temperature

    def probs(self, utilities, random_ties=False):
        u = np.asarray(utilities, dtype=float)
        p = np.zeros(len(u))
        ok = np.isfinite(u)
        if not ok.any():
            return p
        z = (u[ok] - u[ok].max()) / self.temperature
        e = np.exp(z)
        p[ok] = e / e.sum()
        return p


class RelativeSoftmax(Softmax):
    """Softmax on utilities scaled by the best one (so the temperature means the same whatever the unit and size of the utilities: at
    temperature 0.1 a bush with 80% of the best utility is picked with relative probability exp(-2)). If the best utility is not positive
    the utilities are used as they are (the scale then changes when the best crosses zero). With no bush inside the walking window the actor passes
    `-t` (minus the travel time), the best of which is negative, so the choice is then the quickest bush whatever the temperature."""

    def probs(self, utilities, random_ties=False):
        u = np.asarray(utilities, dtype=float)
        ok = np.isfinite(u)
        top = u[ok].max() if ok.any() else 0.0
        return super().probs(u / top if top > 0.0 else u, random_ties)


# --------------------------------------------------------------------------------------------------
# What an actor sees
# --------------------------------------------------------------------------------------------------

class Task:
    """What the participant is told or can learn about the task itself: speeds, durations, the harvest range and how many
    fruits a bush has."""

    def __init__(self, world):
        p = world.params
        self.speed = world.move_speed
        self.fruit_duration = world.fruit_duration
        self.fruit_count = world.fruit_count
        self.session_duration = world.session_duration
        self.gap_base = p.harvest_range_gap_base
        self.gap_per_radius = p.harvest_range_gap_per_radius
        self.max_angle = costs.max_angle(p)   # the harvest cone's half-angle
        self.n_bushes = len(world.pos)       # capacity of a memory (how many bush ids exist), not where they are

    def for_bushes(self, n_bushes):
        """The same task with another number of bush ids (the Interlude has its own bush table)."""
        other = copy.copy(self)
        other.n_bushes = n_bushes
        return other

    def reach(self, radius):
        """Center distance within which a bush of this canopy radius can be harvested."""
        return radius + self.gap_base + self.gap_per_radius * radius


class View:
    """Read-only view for the actor: its body (position, heading, time left, score), memory, critic and task. Value and rate
    utilities are computed from the critic here, so an actor cannot see the true rewards."""

    def __init__(self, body, memory, critic, task, in_interlude=False):
        self.body, self.memory, self.critic, self.task = body, memory, critic, task
        self.in_interlude = in_interlude
        self._equalized = None       # (candidate ids, tolerance) once equalize_times has been applied

    @property
    def time_elapsed(self):
        return self.task.session_duration - self.body.time_left

    def average_rate(self):
        """The agent's average reward per second of the session so far, from the rewards its memory holds (0 before any time has passed):
        what the marginal-value rule compares a bush with."""
        return self.memory.total_reward() / self.time_elapsed if self.time_elapsed > 0.0 else 0.0

    def candidates(self):
        """Mask of bushes the agent knows about and has not seen spent."""
        return self.memory.known & ~self.memory.depleted

    def reach(self):
        return self.task.reach(self.memory.radius)

    def travel_times(self):
        """(n,) seconds from here until the first fruit of each bush could be taken: turning to it, the key presses and the
        walking to its harvest range (costs.approach, the arithmetic the engine charges); inf for bushes not available."""
        m = self.memory
        _, _, turn, press, walking, _ = costs.approach(self.body.pos, self.body.heading, m.pos, m.radius, self.reach(),
                                                       self.task.speed, self.task.max_angle)
        t = turn + press + walking
        t[~self.candidates()] = float("inf")
        if self._equalized is not None:
            ids, tolerance = self._equalized
            if np.isfinite(t[ids]).all() and np.ptp(t[ids]) < tolerance:
                t[ids] = t[ids].mean()
        return t

    def equalize_times(self, candidates, tolerance):
        """A copy of this view in which the travel times of `candidates` count as one (their mean) when they differ by less than `tolerance`
        seconds: an Interlude pair is built to be equal in the terms the harvest rules use, and turning to the centre of a wider canopy
        still takes a few milliseconds more, which must not decide a choice."""
        other = copy.copy(self)
        other._equalized = (np.asarray(candidates, dtype=int), float(tolerance))
        return other

    def values(self):
        """(n,) the critic's expected reward per fruit for every bush in memory (and its uncertainty)."""
        m = self.memory
        # In the Interlude a bush's id means nothing to a critic that learned in the session (the ids are another table's), so
        # only a critic that was granted the Interlude's own table is given them.
        ids = None if self.in_interlude and not getattr(self.critic, "omniscient", False) else np.arange(m.n)
        return self.critic.value(m.attrs, ids)


# --------------------------------------------------------------------------------------------------
# Utilities (functions of the view; value-based ones come from the critic)
# --------------------------------------------------------------------------------------------------

def utility_nearest(view):
    """Negative walking time: ignores value entirely."""
    return -view.travel_times()


def utility_value(view):
    """Expected reward remaining on the bush: critic mean per fruit times fruits left."""
    mean, _ = view.values()
    return mean * view.memory.fruits_left()


def rate_of(view, value):
    """Reward remaining per second of (walk + harvest) time for every bush, if each bush's reward per fruit is `value`."""
    left = view.memory.fruits_left()
    return value * left / (view.travel_times() + left * view.task.fruit_duration)


def utility_rate(view):
    """Expected reward remaining per second of (walk + harvest) time."""
    mean, _ = view.values()
    return rate_of(view, mean)


UTILITIES = {"nearest": utility_nearest, "value": utility_value, "rate": utility_rate}


# --------------------------------------------------------------------------------------------------
# Actors
# --------------------------------------------------------------------------------------------------

class Actor(Component):
    """The policy. `act(view)` returns an action (or None to stop), `keep_harvesting(view, bush, reward)` is asked after
    every fruit but the last, and `choose_between(view, candidates, rng)` picks one of a few bushes (used by the
    Interlude evaluation). The default leaves a bush only when it is empty."""

    choice = Argmax()
    deadline_dependent = False    # True for an actor whose choices depend on how much of the session is left (it plans for the end): its checkpoints are within-session, not shorter sessions

    def begin(self, task, rng):
        self.task = task
        self.rng = rng

    def act(self, view):
        raise NotImplementedError

    def keep_harvesting(self, view, bush, reward):
        return True

    def choose_between(self, view, candidates, rng):
        """Index into `candidates` of the bush the actor prefers, from the critic's value, greedily (ties broken at random)."""
        u = utility_value(view)[np.asarray(candidates)]
        return Argmax().pick(u, rng, random_ties=True)


class UtilityActor(Actor):
    """Pick the known, unharvested bush with the best utility and harvest it until it is empty.

    `utility` is one of UTILITIES (or a function of the view); `max_walk_time` limits the candidates to bushes within that
    many seconds of walking (falling back to the quickest-to-reach bush when none is, so the agent keeps moving); `choice`
    is the ChoiceRule. With utility "nearest" and Argmax this is the nearest-bush forager.

    The default, `rate` within 15 s of walking, is the standard actor: in the battery `rate` was never worse than `value` at any window (24
    of 24 comparisons, both critics, S1-S4), the window hardly mattered to `rate`, and `value` without a tight window walks across the map
    for the best bush and does worse than the blind nearest-bush forager (docs/DECISIONS.md, "One actor default")."""

    def __init__(self, utility="rate", max_walk_time=15.0, choice=None):
        self.utility = UTILITIES[utility] if isinstance(utility, str) else utility
        self.max_walk_time = max_walk_time
        if choice is not None:
            self.choice = choice

    def params(self):
        """The constructor arguments, with the choice rule in effect (subclasses that fix the utility inherit this)."""
        p = super().params()
        if not isinstance(p.get("utility", ""), str):
            raise SpecError("a UtilityActor built from a function has no spec (use one of UTILITIES by name)")
        if "choice" in p:
            p["choice"] = self.choice
        return p

    def act(self, view):
        t = self._times(view)
        if not np.isfinite(t).any():
            return None
        return self._act_on(view, t, self._utilities(view, t))

    def _times(self, view):
        """Seconds until the first fruit of each bush (infinite for the ones this actor will not go to); a subclass removes bushes here."""
        return view.travel_times()

    def _utilities(self, view, t):
        """The utility of every bush (t: seconds until its first fruit); a subclass changes what the actor optimises here."""
        return np.asarray(self.utility(view), dtype=float)

    def _act_on(self, view, t, u):
        """The harvest of the best bush by utility `u` within the walking window (t: seconds until the first fruit of each bush)."""
        if self.max_walk_time is not None:
            in_range = t <= self.max_walk_time
            if not in_range.any():
                u = -t                  # nothing close enough: the quickest to reach, by the same choice rule
            else:
                u = np.where(in_range, u, -np.inf)
        else:
            u = np.where(np.isfinite(t), u, -np.inf)
        j = self.choice.pick(u, self.rng)
        return None if j is None else Harvest(j)

    def choose_between(self, view, candidates, rng):
        view = view.equalize_times(candidates, INTERLUDE_TIME_TIE)
        u = np.asarray(self.utility(view), dtype=float)[np.asarray(candidates)]
        return Argmax().pick(u, rng, random_ties=True)       # greedy whatever the choice rule: the Interlude measures the critic, not the actor's noise


class PosteriorActor(UtilityActor):
    """The rate actor on a value per bush taken from the critic's posterior: `mean + beta * sd`, a bonus for what the critic is unsure of
    (UCB, Wu et al. 2018, who fitted beta about 0.5); with `sample`, one joint posterior draw over the bushes in the walking window takes the
    place of the mean (one possible reward function, not independent guesses): Thompson sampling at beta 0, the hybrid of Gershman 2018 (the
    best account of human two-armed bandit choices) above it. `temperature` chooses by a RelativeSoftmax (random exploration; 0.05: 0.1 was
    too loose in the softmax scan), None by a hard max (the sampling's noise shrinks as the critic learns)."""

    def __init__(self, beta=0.5, sample=False, temperature=None, max_walk_time=15.0):
        super().__init__("rate", max_walk_time, None if temperature is None else RelativeSoftmax(temperature))
        self.beta, self.sample = float(beta), bool(sample)
        self.temperature = None if temperature is None else float(temperature)

    def _utilities(self, view, t):
        mean, sd = view.values()
        if self.sample:
            # one draw over the bushes inside the walking window only: the eigen-decomposition over every known bush would be slow, and nothing
            # outside the window is chosen unless the window is empty (then the quickest bush is, whatever its drawn value)
            near = view.candidates() & (t <= (np.inf if self.max_walk_time is None else self.max_walk_time))
            mean = np.array(mean, dtype=float)
            if near.any():
                mean[near] = view.critic.sample(view.memory.attrs[near], self.rng)
        return rate_of(view, mean + self.beta * sd)


class SoftmaxActor(UtilityActor):
    """The standard rate actor with a softmax choice (random exploration): `RelativeSoftmax` at `temperature` on the utilities relative to
    the best one. With `horizon` the temperature shrinks with the fraction of the session left (`temperature * time left / session`), so
    choices are loose early and nearly greedy at the end, as people explore more with a longer horizon (Wilson et al. 2014); such an
    actor depends on the session's length (`deadline_dependent`)."""

    def __init__(self, temperature=0.05, horizon=False, max_walk_time=15.0):
        super().__init__("rate", max_walk_time, RelativeSoftmax(temperature))
        self.temperature = float(temperature)
        self.horizon = bool(horizon)
        self.deadline_dependent = self.horizon

    def act(self, view):
        if self.horizon:
            self.choice = RelativeSoftmax(max(self.temperature * view.body.time_left / view.task.session_duration, 1e-3))
        return super().act(view)


class CuriousActor(UtilityActor):
    """The rate actor with a curiosity bonus in attribute space and, optionally, a hedge. Each bush's value gets a bonus
    `beta * m / sqrt(1 + n)`, where `m` is the mean reward per fruit so far (so `beta` is a fraction of the running mean value, whatever the
    session's scale) and `n` is how many bushes the agent has harvested near it in attribute space (the sum of `kernel` between this bush
    and every harvested bush): attributes it has little experience with look worth a visit, and the bonus fades as they are sampled.
    `peek_fruits` (None = harvest every bush to empty) makes the agent leave a bush after that many fruits when the bush's own rate (its
    mean reward per fruit over the fruit time) is below `margin` times the average rate so far (the marginal-value rule): a cheap look at an
    unfamiliar bush, not a full harvest. `beta=0` with `peek_fruits` is the hedge alone."""

    def __init__(self, beta=0.3, kernel=None, peek_fruits=None, margin=1.0, max_walk_time=15.0, choice=None):
        super().__init__("rate", max_walk_time, choice)
        self.beta = float(beta)
        self.kernel = kernel if kernel is not None else RBFKernel()
        self.peek_fruits = None if peek_fruits is None else int(peek_fruits)
        self.margin = float(margin)

    def params(self):
        return {**super().params(), "kernel": self.kernel}

    def begin(self, task, rng):
        super().begin(task, rng)
        self._left = set()

    def _times(self, view):
        t = view.travel_times()
        t[list(self._left)] = np.inf          # a bush left early is not returned to: standing in its range it would cost only a key press and win every time
        return t

    def _bonus(self, view):
        scale = view.memory.mean_reward()
        if self.beta == 0.0 or scale <= 0.0:
            return 0.0
        harvested = view.memory.bush_stats()[1]
        n = self.kernel.matrix(view.memory.attrs, harvested).sum(axis=1) if len(harvested) else 0.0
        return self.beta * scale / np.sqrt(1.0 + n)

    def _utilities(self, view, t):
        return rate_of(view, view.values()[0] + self._bonus(view))

    def keep_harvesting(self, view, bush, reward):
        m = view.memory
        if self.peek_fruits is None or m.taken[bush] < self.peek_fruits:
            return True
        if float(np.mean(m.rewards[bush])) / view.task.fruit_duration >= self.margin * view.average_rate():
            return True
        self._left.add(int(bush))
        return False


class AreaRestrictedActor(UtilityActor):
    """Area-restricted search in attribute space. After each bush: if its mean reward per fruit beat the mean of everything harvested so far it
    is a hit, and the agent restricts its next choices to bushes within attribute distance `radius` of it (Euclidean, attributes in
    [0, 1]); a miss widens the restriction by the factor `growth`, until the radius covers everything. A new hit starts again at `radius`. If
    no bush in the walking window lies inside the radius the restriction is dropped for that choice."""

    def __init__(self, radius=0.5, growth=2.0, max_walk_time=15.0, choice=None):
        super().__init__("rate", max_walk_time, choice)
        self.radius, self.growth = float(radius), float(growth)

    def begin(self, task, rng):
        super().begin(task, rng)
        self._anchor, self._reach, self._last = None, self.radius, None

    def _after_visit(self, view):
        m, j = view.memory, self._last
        self._last = None
        if j is None or not m.rewards[j]:
            return
        if float(np.mean(m.rewards[j])) > m.mean_reward():
            self._anchor, self._reach = m.attrs[j].copy(), self.radius
        elif self._anchor is not None:
            self._reach *= self.growth

    def act(self, view):
        self._after_visit(view)
        action = super().act(view)
        self._last = None if action is None else action.bush
        return action

    def _utilities(self, view, t):
        u = super()._utilities(view, t)
        if self._anchor is None:
            return u
        window = np.inf if self.max_walk_time is None else self.max_walk_time
        near = view.candidates() & (t <= window) & (np.linalg.norm(view.memory.attrs - self._anchor, axis=1) <= self._reach)
        return np.where(near, u, -np.inf) if near.any() else u


class PlannerActor(Actor):
    """Plans one route over the bushes in memory, then follows it. The objective is expected reward: the sum over the route of
    (the critic's mean per fruit * fruits taken), with whole-bush harvesting (no early leaving) and no reward noise. The last
    bush may be partly harvested if the clock runs out. Time is simulated exactly as the engine charges it (costs.approach:
    turning to the bush from the current heading, the key presses, a straight walk to the edge of its harvest range, position and
    heading tracked), so the plan's value equals what the engine pays when rewards equal the critic's values. Bushes the critic
    values at zero or less are left out: visiting one only costs time.

    The plan is made at the first decision and made again only when the map in memory or the critic has changed since (a
    full-knowledge oracle therefore plans once); a re-plan starts from the current position and time and treats bushes that
    are partly harvested or spent as gone.

    method="exact": depth-first branch-and-bound, pruned by a fractional-knapsack upper bound and started from a
        beam-search incumbent. Optimal for this objective unless `max_nodes` is hit (then `self.exact` is False
        and the result is the best route found).
    method="beam":  beam search keeping the `beam_width` best partial routes per depth. Fast, near-optimal, no proof.

    After planning: `plan` (bush ids in visiting order), `plan_value` (expected reward), `exact` (proven optimal),
    `nodes` (search nodes expanded, summed over plans).
    """

    deadline_dependent = True      # the plan is made for the whole session, so a session cut short at t is not the first t seconds of it

    def __init__(self, method="exact", beam_width=300, max_nodes=2_000_000, incumbent_width=150):
        if method not in ("exact", "beam"):
            raise ValueError(f"unknown method '{method}'")
        self.method = method
        self.beam_width = beam_width
        self.max_nodes = max_nodes
        self.incumbent_width = incumbent_width

    def begin(self, task, rng):
        super().begin(task, rng)
        self.nodes = 0
        self.exact = False
        self.plan = []
        self.plan_value = 0.0
        self._next = 0
        self._planned_at = None

    def act(self, view):
        key = (view.memory.map_version, view.critic.version)
        if self._planned_at != key:
            self._make_plan(view)
            self._planned_at = key
        if self._next >= len(self.plan):
            return Stop()
        j = self.plan[self._next]
        self._next += 1
        return Harvest(j)

    # ---- planning ------------------------------------------------------------------------------

    def _make_plan(self, view):
        m = view.memory
        task = self.task
        mean, _ = view.values()
        ids = np.flatnonzero(m.known & ~m.depleted & (m.taken == 0))
        self._ids = ids[mean[ids] > 0.0]
        self.F = task.fruit_count
        self.fd = task.fruit_duration
        self.T = task.session_duration
        self.P = m.pos[self._ids]
        self.reach = view.reach()[self._ids]
        self.rad = m.radius[self._ids]
        self.max_angle = task.max_angle
        self.start_heading = float(view.body.heading)
        self.value = mean[self._ids]
        self.speed = task.speed
        self.start = np.array(view.body.pos, dtype=float)
        self.t0 = view.time_elapsed
        if len(self._ids) == 0:
            self.plan, self.plan_value, self.exact = [], 0.0, True
            self._next = 0
            return
        self._prepare_bound()
        if self.method == "beam":
            plan, self.plan_value = self._beam(self.beam_width)
            self.plan = [int(self._ids[j]) for j in plan]
        else:
            plan, value = self._beam(self.incumbent_width)
            plan, self.plan_value, self.exact = self._branch_and_bound(plan, value)
            self.plan = [int(self._ids[j]) for j in plan]
        self._next = 0

    # ---- shared primitives (same arithmetic as sim.run_episode) -----------------------------------

    def _step_all(self, pos, heading, t, visited):
        """For every bush: (distance, walk, time the first fruit could start, harvestable fruits k, heading after) from `pos`
        facing `heading` at time `t`. k == 0 where the bush is visited, or cannot be reached with time for one fruit."""
        dist, walk, turn, press, walking, new_heading = costs.approach(pos, heading, self.P, self.rad, self.reach, self.speed,
                                                               self.max_angle)
        arrive = t + turn + press + walking
        k = np.minimum(self.F, np.floor((self.T - arrive) / self.fd + 1e-9)).astype(int)
        k[visited] = 0
        k = np.maximum(k, 0)
        return dist, walk, arrive, k, new_heading

    def _move(self, pos, dist, walk, j):
        if walk[j] > 0.0:
            return pos + (self.P[j] - pos) / dist[j] * walk[j]
        return pos

    # ---- upper bound: fractional knapsack over unvisited bushes ---------------------------------

    def _prepare_bound(self):
        n = len(self.P)
        pts = np.vstack([self.P, self.start[None, :]])
        d = pts[:, None, :] - pts[None, :, :]
        D = np.sqrt((d ** 2).sum(-1))              # (n+1, n+1) center distances; row/column n is the start
        # cheapest possible walk into each bush from any other bush's stop or from the start (lower bound)
        into = np.maximum(0.0, D[:n, :n] - self.reach[:, None] - self.reach[None, :]) / self.speed
        np.fill_diagonal(into, np.inf)
        from_start = np.maximum(0.0, D[n, :n] - self.reach) / self.speed
        m = np.minimum(into.min(axis=0), from_start)
        cost = self.F * self.fd + m + costs.HARVEST_PRESS_TIME      # (turning and the W press can be zero: a lower bound)
        val = self.value * self.F
        order = np.argsort(-(val / cost))
        self._order = order
        self._rank = np.empty(n, dtype=int)
        self._rank[order] = np.arange(n)
        self._cost_s = cost[order]
        self._val_s = val[order]

    def _bound(self, visited_sorted, remaining):
        """Upper bound on additional reward from `remaining` seconds, given visited flags in bound order."""
        free = ~visited_sorted
        cs = np.cumsum(self._cost_s * free)
        cv = np.cumsum(self._val_s * free)
        k = int(np.searchsorted(cs, remaining, side="right"))
        total = cv[k - 1] if k > 0 else 0.0
        if k < len(cs):
            prev = cs[k - 1] if k > 0 else 0.0
            total += self._val_s[k] * (remaining - prev) / self._cost_s[k]
        return float(total)

    # ---- beam search ------------------------------------------------------------------------------

    def _beam(self, width):
        n = len(self.P)
        # state: (score, reward, t, pos, last, visited bool array, plan list, heading)
        start_vis = np.zeros(n, dtype=bool)
        beam = [(0.0, 0.0, self.t0, self.start.copy(), -1, start_vis, [], self.start_heading)]
        best_reward, best_plan = 0.0, []
        while beam:
            children = {}
            for _, reward, t, pos, last, visited, plan, heading in beam:
                dist, walk, arrive, k, new_heading = self._step_all(pos, heading, t, visited)
                for j in np.flatnonzero(k > 0):
                    new_reward = reward + self.value[j] * k[j]
                    t_new = arrive[j] + k[j] * self.fd
                    vis = visited.copy()
                    vis[j] = True
                    new_plan = plan + [int(j)]
                    if new_reward > best_reward + 1e-12:
                        best_reward, best_plan = new_reward, new_plan
                    if k[j] < self.F:
                        continue            # partly harvested: clock is out, nothing follows
                    self.nodes += 1
                    score = new_reward + self._bound(vis[self._order], self.T - t_new)
                    key = (j, vis.tobytes())
                    old = children.get(key)
                    if old is None or t_new < old[2]:
                        children[key] = (score, new_reward, t_new, self._move(pos, dist, walk, j), j, vis, new_plan, float(new_heading[j]))
            beam = sorted(children.values(), key=lambda s: -s[0])[:width]
        return best_plan, best_reward

    # ---- branch and bound -------------------------------------------------------------------------

    def _branch_and_bound(self, incumbent_plan, incumbent_value):
        n = len(self.P)
        best = {"value": incumbent_value, "plan": list(incumbent_plan)}
        visited = np.zeros(n, dtype=bool)
        capped = {"hit": False}

        def recurse(pos, heading, t, reward, plan):
            if capped["hit"]:
                return
            self.nodes += 1
            if self.nodes > self.max_nodes:
                capped["hit"] = True
                return
            if reward > best["value"] + 1e-12:
                best["value"], best["plan"] = reward, list(plan)
            bound = reward + self._bound(visited[self._order], self.T - t)
            if bound <= best["value"] + 1e-9:
                return
            dist, walk, arrive, k, new_heading = self._step_all(pos, heading, t, visited)
            cand = np.flatnonzero(k > 0)
            if len(cand) == 0:
                return
            gain = self.value[cand] * k[cand]
            rate = gain / (arrive[cand] - t + k[cand] * self.fd)
            for idx in np.argsort(-rate):
                j = int(cand[idx])
                new_reward = reward + gain[idx]
                if k[j] < self.F:
                    if new_reward > best["value"] + 1e-12:
                        best["value"], best["plan"] = new_reward, plan + [j]
                    continue
                visited[j] = True
                plan.append(j)
                recurse(self._move(pos, dist, walk, j), float(new_heading[j]), arrive[j] + k[j] * self.fd, new_reward, plan)
                plan.pop()
                visited[j] = False

        recurse(self.start.copy(), self.start_heading, self.t0, 0.0, [])
        return best["plan"], best["value"], not capped["hit"]


# --------------------------------------------------------------------------------------------------
# Composition
# --------------------------------------------------------------------------------------------------

class ComposedAgent:
    """Actor + critic + memory (+ an optional percept override), the protocol sim.run_episode drives. Attributes the agent does not define
    (for the planner: `plan`, `plan_value`, `exact`, `nodes`) are read from the actor. The agent never keeps the world: it is
    given a Task, observations and a Body, and the omniscient components alone are granted the world's knowledge."""

    def __init__(self, actor, critic, memory, percept=None):
        self.actor, self.critic, self.memory, self.percept = actor, critic, memory, percept
        self.interlude_memory = None

    def __getattr__(self, name):
        if name in ("actor", "critic", "memory", "percept"):
            raise AttributeError(name)
        return getattr(self.actor, name)

    def spec(self):
        """The agent as data: its four components' specs (percept None = the environment's own sensor). `spec_hash` of it is the
        agent's identity."""
        return {"memory": self.memory.spec(), "critic": self.critic.spec(), "actor": self.actor.spec(),
                "percept": None if self.percept is None else self.percept.spec()}

    def spec_hash(self):
        return spec_hash(self.spec())

    @property
    def active_memory(self):
        """The Interlude's memory once one has begun, else the session's."""
        return self.interlude_memory if self.interlude_memory is not None else self.memory

    def _start(self, memory, task, knowledge, new_critic=True):
        memory.begin(task)
        if new_critic:
            self.critic.begin(task)
        for component in (memory, self.critic):
            if getattr(component, "omniscient", False):
                component.grant(knowledge)

    def begin_session(self, world, rng):
        self.interlude_memory = None
        self.task = Task(world)
        self._start(self.memory, self.task, WorldKnowledge.from_world(world))
        self.actor.begin(self.task, rng)
        self.critic.update(self.memory)

    def begin_interlude(self, knowledge):
        """After the session: freeze the critic (an Interlude shows no outcomes, so nothing is learned there) and start a fresh
        memory for the Interlude's own bushes (the session's bush ids mean nothing there); `knowledge` is the Interlude's bush
        table, granted only to omniscient components. The session's memory is left as it was."""
        self.critic.freeze()
        self.interlude_memory = self.memory.fresh()
        # The critic carries over: `begin` would let one that starts empty there forget what it learned in the session.
        self._start(self.interlude_memory, self.task.for_bushes(knowledge.n), knowledge, new_critic=False)

    def view(self, body):
        return View(body, self.active_memory, self.critic, self.task, in_interlude=self.interlude_memory is not None)

    def observe(self, obs):
        self.active_memory.observe(obs)

    def record_reward(self, bush, reward):
        self.memory.record_reward(bush, reward)
        if self.critic.update_on == "fruit":
            self.critic.update(self.memory)

    def end_visit(self, bush):
        """A visit to `bush` is over (it is empty, the actor left, or the clock ran out): a critic that learns per bush learns now."""
        if self.critic.update_on == "bush":
            self.critic.update(self.memory)

    def mark_depleted(self, bush):
        self.memory.mark_depleted(bush)

    def act(self, body):
        return self.actor.act(self.view(body))

    def keep_harvesting(self, body, bush, reward):
        return self.actor.keep_harvesting(self.view(body), bush, reward)

    def choose_between(self, body, candidates, rng):
        """Index into `candidates` (bush ids in the active memory) of the bush the actor prefers."""
        return self.actor.choose_between(self.view(body), candidates, rng)


def build_agent(spec, extra=None):
    """The agent a spec describes (`ComposedAgent.spec()` is its inverse). `extra` maps class names to components defined outside
    the library."""
    return ComposedAgent(build(spec["actor"], extra), build(spec["critic"], extra), build(spec["memory"], extra),
                         build(spec["percept"], extra))


def oracle_agent(actor, percept=None):
    """An actor with full knowledge: the oracle critic and a map preloaded with every bush."""
    return ComposedAgent(actor, OracleCritic(), FullKnowledge(), percept)


def _oracle(actor, whole_map):
    """The oracle critic with the map from the sensor (the view cone, the default) or, with `whole_map`, preloaded with every bush."""
    return oracle_agent(actor) if whole_map else ComposedAgent(actor, OracleCritic(), FullMemory())


def NearestAgent(whole_map=False):
    """Walk to the bush that is quickest to reach, harvest it until exhausted, repeat. "Closest" is by walking time to the
    edge of the bush's harvest range (so a wide canopy counts as nearer than its center distance suggests). Ignores bush
    value entirely. Like every standard agent it sees through the view cone; `whole_map=True` gives it every bush from the start."""
    return _oracle(UtilityActor("nearest", None), whole_map)


def GreedyAgent(max_walk_time=15.0, score="rate", whole_map=False):
    """The oracle critic (true values) with the one-step greedy actor: among bushes reachable within `max_walk_time` seconds of walking, go
    to the best one, harvest it until exhausted, repeat. No path planning. score="value": highest expected reward remaining on the bush
    (critic mean * fruits left); score="rate": highest expected reward remaining per second of (walk + harvest) time. If
    nothing is within range, falls back to the quickest-to-reach bush so the agent keeps moving. The map comes from the view cone
    unless `whole_map` (the full-information benchmark of the older results)."""
    if score not in ("value", "rate"):
        raise ValueError(f"unknown score '{score}'")
    return _oracle(UtilityActor(score, max_walk_time), whole_map)


def PlannerAgent(method="exact", **kwargs):
    """Full information and the whole map: plans one route for the session at the start, then follows it (see PlannerActor)."""
    return oracle_agent(PlannerActor(method, **kwargs))


def DeltaRuleAgent(score="rate", max_walk_time=15.0, features=None, prior=None, alpha=0.5):
    """The simplest learner: starts with an empty map (what the sensor shows it) and learns a value for the attributes by the delta
    rule on `features` (default RBFFeatures), then goes to the bush it values best (one-step greedy, as GreedyAgent). It has no
    exploring actor yet, so it only visits bushes it has seen."""
    return ComposedAgent(UtilityActor(score, max_walk_time), DeltaRuleCritic(features, prior, alpha), FullMemory())


def LearnerAgent(actor, **critic):
    """The standard learner (delta-rule critic) with another actor: what changes is the policy only."""
    return ComposedAgent(actor, DeltaRuleCritic(**critic), FullMemory())


def GPAgent(actor=None, **critic):
    """A learner whose critic is a Gaussian process (`GPCritic(**critic)`) and whose actor is `actor` (default: the standard rate actor
    on the posterior mean); the map comes from the view cone."""
    return ComposedAgent(actor if actor is not None else UtilityActor(), GPCritic(**critic), FullMemory())


REGISTRY["nearest"] = NearestAgent
REGISTRY["oracle"] = GreedyAgent                  # the standard actor (rate, 15 s), true values, map from the view cone
REGISTRY["learner"] = DeltaRuleAgent              # the same actor with the delta-rule critic, map from the view cone
REGISTRY["softmax"] = lambda: LearnerAgent(SoftmaxActor(0.05))                        # random exploration
REGISTRY["softmax_horizon"] = lambda: LearnerAgent(SoftmaxActor(0.1, horizon=True))   # ... shrinking with the time left
REGISTRY["curious"] = lambda: LearnerAgent(CuriousActor())                            # an attribute-space novelty bonus
REGISTRY["peek"] = lambda: LearnerAgent(CuriousActor(beta=0.0, peek_fruits=2))        # leave a poor bush after two fruits (marginal value)
REGISTRY["curious_peek"] = lambda: LearnerAgent(CuriousActor(peek_fruits=2))          # curiosity hedged by peeking
REGISTRY["ars"] = lambda: LearnerAgent(AreaRestrictedActor())                         # area-restricted search in attribute space
REGISTRY["gp_joint"] = lambda: GPAgent(kernel=RBFKernel(0.3, additive=False))        # the joint (isotropic 3-D) kernel instead of the additive one
REGISTRY["gp_softmax"] = lambda: GPAgent(SoftmaxActor(0.05))                         # the GP critic with each exploration policy of the delta-rule agents
REGISTRY["gp_softmax_horizon"] = lambda: GPAgent(SoftmaxActor(0.1, horizon=True))
REGISTRY["gp_curious"] = lambda: GPAgent(CuriousActor())
REGISTRY["gp_peek"] = lambda: GPAgent(CuriousActor(beta=0.0, peek_fruits=2))
REGISTRY["gp_curious_peek"] = lambda: GPAgent(CuriousActor(peek_fruits=2))
REGISTRY["gp_ars"] = lambda: GPAgent(AreaRestrictedActor())
_MATCHED = dict(prior_mean=0.1, weight_by_count=False, prior_std=1.0, noise_std=0.3)
REGISTRY["gp_fixmean"] = lambda: GPAgent(prior_mean=0.1)                                                   # the ladder from gp_mean to the delta rule: the
REGISTRY["gp_equalw"] = lambda: GPAgent(prior_mean=0.1, weight_by_count=False)                             # reversion value fixed at the delta rule's 0.1,
REGISTRY["gp_fixhyper"] = lambda: GPAgent(**_MATCHED)                                                      # every bush weighted alike, the prior and noise
REGISTRY["gp_matched"] = lambda: GPAgent(kernel=FeatureKernel(RBFFeatures()), **_MATCHED)                  # fixed, then the delta rule's own features as the kernel
REGISTRY["replay_len0_5"] = lambda: LearnerAgent(UtilityActor(), features=RBFFeatures(length_scale=0.5), replay=FullSweeps(100))     # the best replay delta rule
REGISTRY["gp_matched_len0_5"] = lambda: GPAgent(kernel=FeatureKernel(RBFFeatures(length_scale=0.5)), prior_mean=0.1, weight_by_count=False,
                                                prior_std=1.0, noise_std=0.1)       # ... and the GP with the same features, baseline and weights
REGISTRY["gp_mean"] = GPAgent                                   # the GP critic with the standard actor (no exploration)
REGISTRY["gp_ucb"] = lambda: GPAgent(PosteriorActor(0.5, temperature=0.05))                # UCB with a softmax (Wu et al. 2018)
REGISTRY["gp_thompson"] = lambda: GPAgent(PosteriorActor(0.0, sample=True))      # Thompson sampling
REGISTRY["gp_hybrid"] = lambda: GPAgent(PosteriorActor(0.5, sample=True))          # a posterior draw plus the UCB bonus (Gershman 2018)
for _score in ("value", "rate"):
    REGISTRY[f"delta_{_score}_10"] = (lambda s: lambda: DeltaRuleAgent(s, 10.0))(_score)
for _score in ("value", "rate"):
    for _t in (5, 10, 15, 20, 30):
        REGISTRY[f"greedy_{_score}_{_t}"] = (lambda t, s: lambda: GreedyAgent(t, s, whole_map=True))(_t, _score)   # the full-information benchmarks
REGISTRY["plan_exact"] = lambda: PlannerAgent("exact")
REGISTRY["plan_beam"] = lambda: PlannerAgent("beam")
