"""Patch-foraging benchmarks: what to harvest in a patch when the values are known (docs/DECISIONS.md, "Patch-foraging benchmarks").

Four agents with global knowledge of every bush's value and tile and average costs of walking, turning and key presses (`average_costs`), on the tiles world:

    dp_finite    optimal stopping by dynamic programming over the time left: in a patch it takes the next best bush when that, and the best that follows, is worth more than leaving for a fresh
                 patch (the value of which is the world's tiles' average, the finite-horizon backward induction on the session clock). Exact under the model: fresh patches are the world's
                 own, one `c_travel` away, and a bush costs its harvest plus the average step to it.
    dp_average   the same on an infinite horizon: the stationary policy that maximises the long-run rate `rho` (relative value iteration, found by bisection on `rho`).
    mvt          the marginal value theorem (Charnov 1976): leave when the next bush's rate (its points over its time) is below the environment's average rate `rho`, here the optimal one.
    mvt_running  the marginal value rule with the rate the agent has experienced so far (its points over the session time, started from a prior of `PRIOR_SECONDS` at the rate of an average bush),
                 as in average-reward accounts of patch leaving (Constantino and Daw 2015).

On sorted bushes with the costs of a bush the same within a patch, `mvt` with the optimal `rho` takes what `dp_average` takes. The agents differ in the time horizon (`dp_finite` takes more at the end, when leaving no longer
pays) and in where the rate comes from. Each agent picks the bushes of a tile (`pick`) and leaves; the tile and the order are `tile_calibration.TilePolicy`'s (the next tile is the one whose picked bushes pay the
most per second, the bushes in a tile best rate first).
"""

import numpy as np

import agents
import costs
import sim
import tile_calibration as tc

TIME_STEP = 0.25            # seconds: the grid of the finite-horizon DP
PRIOR_SECONDS = 30.0        # the running rate starts as this many seconds at the rate of an average bush
RHO_BISECTIONS = 60


def average_costs(pos, radius, reach, tile_of, speed, max_angle, fruit_count, fruit_duration):
    """The average costs of the tiles world, in seconds: `harvest` a whole bush (its fruits), `c_in` the step from one bush of a patch to another (turning, the key presses and the walk to its harvest range,
    `costs.approach`, averaged over the ordered pairs of a tile's bushes with the view toward the bush just left from the tile's middle) and `c_travel` the step from a patch to the nearest bush of a neighbouring one
    (averaged over the ordered pairs of neighbouring tiles; the tiles of the world's edge with no neighbour count as the others)."""
    tiles_ = np.unique(tile_of)
    centre = {t: pos[tile_of == t].mean(axis=0) for t in tiles_}
    inside = []
    for t in tiles_:
        idx = np.flatnonzero(tile_of == t)
        for i in idx:
            heading = float(costs.bearing(*(pos[i] - centre[t])))
            others = idx[idx != i]
            if len(others) == 0:
                continue
            _, _, turn, press, walking, _ = costs.approach(pos[i], heading, pos[others], radius[others], reach[others], speed, max_angle)
            inside.append(float(np.mean(turn + press + walking)))
    cs = np.array([centre[t] for t in tiles_])
    pitch = np.sort(np.hypot(*(cs[:, None, :] - cs[None, :, :]).transpose(2, 0, 1)), axis=1)[:, 1].min()
    between = []
    for a, t in enumerate(tiles_):
        for b, u in enumerate(tiles_):
            if a == b or np.hypot(*(cs[a] - cs[b])) > 1.05 * pitch:
                continue
            ti, ui = np.flatnonzero(tile_of == t), np.flatnonzero(tile_of == u)
            i = ti[np.argmin(np.hypot(*(pos[ti] - centre[u]).T))]
            j = ui[np.argmin(np.hypot(*(pos[ui] - pos[i]).T))]
            heading = float(costs.bearing(*(pos[i] - centre[t])))
            _, _, turn, press, walking, _ = costs.approach(pos[i], heading, pos[[j]], radius[[j]], reach[[j]], speed, max_angle)
            between.append(float(turn[0] + press[0] + walking[0]))
    return {"harvest": fruit_count * fruit_duration, "c_in": float(np.mean(inside)) if inside else 0.0, "c_travel": float(np.mean(between)) if between else 0.0}


class PatchModel:
    """The patch-leaving problem of one world: each tile's bush values (points per fruit, best first), `fruits` a bush, `harvest` seconds a bush, `c_in` and `c_travel` the average steps, `horizon` the session seconds.
    Taking the j-th bush of a patch costs `c_in + harvest` seconds (`harvest` for the first: the way in was paid when the patch was chosen) and pays `fruits * value`; leaving costs `c_travel` and ends in a fresh patch,
    which is a tile of the world drawn with equal chances."""

    def __init__(self, values_by_tile, fruits, harvest, c_in, c_travel, horizon, dt=TIME_STEP):
        self.n_tiles = len(values_by_tile)
        self.width = max(len(v) for v in values_by_tile)
        self.values = np.zeros((self.n_tiles, self.width))
        self.size = np.array([len(v) for v in values_by_tile])
        for t, v in enumerate(values_by_tile):
            self.values[t, :len(v)] = np.sort(np.asarray(v, dtype=float))[::-1]
        self.fruits, self.harvest, self.c_in, self.c_travel, self.horizon, self.dt = fruits, harvest, c_in, c_travel, horizon, dt
        self.cost = np.array([harvest] + [c_in + harvest] * (self.width - 1))        # seconds to take the j-th bush of a patch
        self._finite = None
        self._rho = None

    # ---- the finite horizon ------------------------------------------------------------------------

    def finite_horizon(self):
        """(V, cont): V[k] the expected points of arriving at a fresh patch with k * dt seconds left, and cont[t, k, j] whether tile t's j-th best bush is worth taking with k * dt left (the points it pays and the
        best that follows, against leaving)."""
        if self._finite is not None:
            return self._finite
        K, n, w, dt = int(round(self.horizon / self.dt)), self.n_tiles, self.width, self.dt
        steps = np.ceil(self.cost / dt - 1e-9).astype(int)
        s_travel = max(int(np.ceil(self.c_travel / dt - 1e-9)), 1)
        gain = self.fruits * self.values                                          # (n, w) points of taking the whole bush
        V = np.zeros(K + 1)
        W = np.zeros((n, K + 1, w + 1))
        cont = np.zeros((n, K + 1, w), dtype=bool)
        for k in range(K + 1):
            leave = V[k - s_travel] if k >= s_travel else 0.0
            W[:, k, w] = leave
            for j in range(w - 1, -1, -1):
                frac = min(1.0, k * dt / self.cost[j]) if k < steps[j] else 1.0           # the clock runs out in the bush: the share of its fruits it can take
                after = W[:, k - steps[j], j + 1] if k >= steps[j] else 0.0
                take = gain[:, j] * frac + after
                take = np.where(j < self.size, take, -np.inf)
                cont[:, k, j] = take > leave + 1e-12
                W[:, k, j] = np.maximum(take, leave)
            V[k] = W[:, k, 0].mean()
        self._finite = (V, cont)
        return self._finite

    # ---- the infinite horizon ----------------------------------------------------------------------

    def _stationary(self, rho):
        """(mean of the tiles' value on arriving, cont[t, j]) at long-run rate `rho`: points less `rho` times the seconds, leaving worth -rho * c_travel (a fresh patch is worth 0 by the choice of `rho`)."""
        n, w = self.n_tiles, self.width
        leave = -rho * self.c_travel
        W = np.full((n, w + 1), leave)
        cont = np.zeros((n, w), dtype=bool)
        for j in range(w - 1, -1, -1):
            take = self.fruits * self.values[:, j] - rho * self.cost[j] + W[:, j + 1]
            take = np.where(j < self.size, take, -np.inf)
            cont[:, j] = take > leave + 1e-12
            W[:, j] = np.maximum(take, leave)
        return float(W[:, 0].mean()), cont

    def stationary(self):
        """(rho, cont): the long-run rate (points per second) the best stationary policy earns, and cont[t, j] whether to take tile t's j-th best bush (bisection on `rho` until a fresh patch is worth 0)."""
        if self._rho is None:
            lo, hi = 0.0, float(self.fruits * self.values.max() / min(self.harvest, 1.0)) + 1.0
            for _ in range(RHO_BISECTIONS):
                mid = 0.5 * (lo + hi)
                if self._stationary(mid)[0] > 0.0:
                    lo = mid
                else:
                    hi = mid
            rho = 0.5 * (lo + hi)
            self._rho = (rho, self._stationary(rho)[1])
        return self._rho

    def average_bush_rate(self):
        """The points per second of an average bush taken one after another: what a forager knowing only the bushes' average would expect."""
        mean = float(self.fruits * self.values[self.values > 0].mean())
        return mean / (self.c_in + self.harvest)


class PatchActor(tc.TilePolicy):
    """A tile policy that decides how many bushes of a tile to take with the model of its world, built at the first decision from what the agent was granted (every bush's value and tile, average costs)."""

    model = None
    c_travel = None             # seconds between patches when set (else the average step to the nearest bush of a neighbouring tile)

    def _build(self, view):
        m, task = view.memory, self.task
        mean, _ = view.values()
        tile_ids = np.unique(self.tile_of)
        self.tile_index = {int(t): i for i, t in enumerate(tile_ids)}
        costs_ = average_costs(m.pos, m.radius, view.reach(), self.tile_of, task.speed, task.max_angle, task.fruit_count, task.fruit_duration)
        if self.c_travel is not None:
            costs_["c_travel"] = self.c_travel
        self.model = PatchModel([mean[self.tile_of == t] for t in tile_ids], task.fruit_count, costs_["harvest"], costs_["c_in"], costs_["c_travel"], task.session_duration)
        self.costs = costs_

    def act(self, view):
        if self.model is None:
            self._build(view)
        self.view = view
        return super().act(view)

    def pick(self, members, mean):
        order = members[np.argsort(-mean[members])]
        t = self.tile_index[int(self.tile_of[order[0]])]
        return order[:self.count(t, self.model.size[t] - len(order), order, mean)]


class DPFinite(PatchActor):
    """Optimal stopping on the session clock (see the module)."""

    def count(self, t, offset, order, mean):
        _, cont = self.model.finite_horizon()
        m = self.model
        k = min(int(max(self.view.body.time_left - m.c_travel, 0.0) / m.dt), cont.shape[1] - 1)
        taken = 0
        for j in range(len(order)):
            if not cont[t, k, j + offset]:
                break
            taken += 1
            k = max(k - int(np.ceil(m.cost[j + offset] / m.dt - 1e-9)), 0)
            if k == 0:
                break
        return taken


class DPAverage(PatchActor):
    """The stationary optimum: take the bushes `cont` says to."""

    def count(self, t, offset, order, mean):
        _, cont = self.model.stationary()
        taken = 0
        for j in range(len(order)):
            if not cont[t, j + offset]:
                break
            taken += 1
        return taken


class MVT(PatchActor):
    """The marginal value theorem: take the next bush while its rate (points over seconds) is at least the long-run rate `rho`."""

    def rate(self):
        return self.model.stationary()[0]

    def count(self, t, offset, order, mean):
        m, rho = self.model, self.rate()
        taken = 0
        for j in range(len(order)):
            if m.fruits * mean[order[j]] / m.cost[j + offset] < rho:
                break
            taken += 1
        return taken


class MVTRunning(MVT):
    """The marginal value rule with the rate experienced so far: its points over the session time, with a prior of `PRIOR_SECONDS` at the rate of an average bush."""

    def rate(self):
        elapsed = self.view.time_elapsed
        return (self.view.body.total + PRIOR_SECONDS * self.model.average_bush_rate()) / (elapsed + PRIOR_SECONDS)


FACTORIES = {"dp_finite": DPFinite, "dp_average": DPAverage, "mvt": MVT, "mvt_running": MVTRunning}


def make_agent(name, world, rounds=1):
    """The agent `name` of `FACTORIES` for a tiles world: an oracle (every bush's value) bound to the world's tiles. The step between patches is the average of one rollout of the agent itself (`rounds` times
    over; 0 keeps the analytic estimate of `average_costs`): where the next patch lies depends on which are left, and the first bush of a patch is the best one, not the nearest, so the walk between patches is
    longer than the nearest neighbour's. The cost is taken from the seconds that were not harvesting, less the steps inside the patches, over the patches visited."""
    tile_of, _ = tc.tile_of_world(world)
    c_travel = None
    for _ in range(rounds):
        actor = FACTORIES[name]().bind(tile_of)
        actor.c_travel = c_travel
        result = sim.run_episode(tc.oracle(actor), world)
        stats = tc.route_stats(result, tile_of, world.value)
        if stats["visits"] == 0:
            break
        used = result.walk_time + result.look_time + result.press_time
        c_travel = max((used - (stats["bushes"] - stats["visits"]) * actor.costs["c_in"]) / stats["visits"], 0.0)
    actor = FACTORIES[name]().bind(tile_of)
    actor.c_travel = c_travel
    return tc.oracle(actor)


def run(name, world, rounds=1):
    """The episode of agent `name` on `world` (`sim.run_episode`)."""
    return sim.run_episode(make_agent(name, world, rounds), world)
