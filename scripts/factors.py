"""The factors of a session as realised in a generated world (docs/SESSION_FACTORS_PLAN.md, milestone 1): what to measure on a world, so that a knob's target can be compared with what was made.

    ./venv/bin/python scripts/factors.py measure FOR_S1 [--seeds 0-9]
    ./venv/bin/python scripts/factors.py calibrate FOR_S1 --travel-time 8 --diversity 0.5 [--seeds 0-19]

`measure(world)` takes a world from `world.generate_world` and returns the patch factors (travel time, contrast between tiles, diversity within a tile), the mean bush value (anchor a of the
plan), the bush Gini, the realised per-fruit noise and the descriptors of the reward map (`value_maps.descriptors`, the part that does not depend on the world's draw). A tile is a patch: its
cluster of bushes. `measure` changes nothing; the calibrators (`travel_time_settings`, `diversity_settings`, `calibrate`) go the other way, from a target to the generator settings that make it, and
`verify` generates worlds from those settings and reports the realised value against the target and what else moved.
"""

import argparse
import math

import numpy as np

import tiles
import value_maps
from world import REWARDS, _camel, bush_value, generate_world, load_session, stage_names

NOISE_FLOOR_SDS = 3.0        # the realised noise is read from bushes paying at least this many noise SDs, where the clip at 0 does not bite


def map_descriptors(params):
    """The value-map descriptors (`value_maps.descriptors`) of a session's reward function, on the unit plane."""
    axis = np.linspace(0.0, 1.0, value_maps.GRID)
    return value_maps.descriptors(axis, bush_value(params.reward_function, axis[:, None], axis[None, :]))


def measure(world):
    """The realised factors of a world.

    Patch factors:
      `travel_time` (s) = the walk across the gap between two neighbouring clusters (centre to centre `tile pitch` less two cluster radii) over the player's speed; `travel_time_nearest_bush` the
      same with the median, over neighbouring pairs, of the distance between their nearest bushes; `travel_time_centres` centre to centre.
      `contrast` = SD across tiles of the tile's mean bush value (reward units); `neighbour_difference` = the mean |difference| of the mean values of neighbouring tiles.
      `diversity` = the mean over tiles of the SD of the bush values inside a tile.
    Also: `mean_bush_value` (anchor a), `bush_gini`, `max_bush_value`, `noise_sd` (the SD of a fruit's pay about its bush value, nan when no bush pays enough to read it), `n_tiles`, `n_bushes`,
    `walk_visits` (the visits a session could make by walking alone: `session_duration` over `travel_time`, a ceiling, harvesting takes time too)."""
    params, grid = world.params, world.terrain.tiles
    ts = tiles.TileSet(grid, world.pos)
    v, speed = np.asarray(world.value, dtype=float), float(params.player_move_speed)
    means = np.array([v[ts.tile_of == t].mean() for t in range(ts.n_tiles)])
    within = np.array([v[ts.tile_of == t].std(ddof=1) for t in range(ts.n_tiles)])
    pairs = [(t, u) for t in range(ts.n_tiles) for u in ts.neighbours[t] if t < u]
    nearest = [np.hypot(*(world.pos[ts.tile_of == t][:, None, :] - world.pos[ts.tile_of == u][None, :, :]).T).min() for t, u in pairs]
    gap = grid.pitch - 2.0 * grid.cluster_radius
    rich = v >= NOISE_FLOOR_SDS * float(params.reward_std)
    noise = world.fruit_reward[rich] - v[rich, None]
    return {"travel_time": gap / speed, "travel_time_nearest_bush": float(np.median(nearest)) / speed, "travel_time_centres": grid.pitch / speed,
            "contrast": float(means.std()), "neighbour_difference": float(np.mean([abs(means[t] - means[u]) for t, u in pairs])), "diversity": float(within.mean()),
            "mean_bush_value": float(v.mean()), "bush_gini": value_maps.gini(v), "max_bush_value": float(v.max()),
            "noise_sd": float(noise.std()) if noise.size > 1 else float("nan"),
            "max_fruit": float(world.fruit_reward.max()), "share_fruit_over_cap": float(np.mean(world.fruit_reward > FRUIT_CAP)),
            "n_tiles": int(ts.n_tiles), "n_bushes": int(len(v)), "walk_visits": float(params.session_duration) / (gap / speed)}


# --------------------------------------------------------------------------------------------------
# Calibrators: a target factor to the generator settings (snake_case names, `load_session` overrides; `fields` gives the serialized names a design module passes on)
# --------------------------------------------------------------------------------------------------

def travel_time_settings(params, seconds):
    """`tile_radius` at which the walk across the gap between two neighbouring clusters takes `seconds` at the player's speed: the tile pitch is sqrt(3) * radius, the gap the pitch less two cluster
    radii, so radius = (seconds * speed + 2 * cluster radius) / sqrt(3). Closed form and exact. Refused when the gap is narrower than the ramp between plateaus (the cluster would not fit its plateau)."""
    gap = float(seconds) * float(params.player_move_speed)
    if gap < float(params.tile_ramp_width):
        raise ValueError(f"a travel time of {seconds} s is a gap of {gap:.1f} units, less than the ramp between plateaus ({params.tile_ramp_width}): at least {params.tile_ramp_width / params.player_move_speed:.2f} s")
    return {"tile_radius": (gap + 2.0 * float(params.tile_cluster_radius)) / math.sqrt(3.0)}


def diversity_settings(params, target_sd, seed=0):
    """The tile layout and `tile_spread` at which a tile's bushes have a mean reward SD of `target_sd`: tile centres uniform over the plane (between `random`) and each tile's bushes scattered around
    its centre (within `scatter`), the spread solved by `tiles.spread_for_reward_sd` on the session's reward. (Under the default modes, `none` and `pool`, a tile's bushes are a draw from the
    whole map, the spread is not read, and the diversity is the map's own SD: not a knob.) Refused outside the range the reward can give."""
    reward = REWARDS[stage_names(params)[2]]
    return {"tile_value_mode": "random", "tile_within_mode": "scatter", "tile_spread": tiles.spread_for_reward_sd(params, reward, float(target_sd), seed=seed)}


def calibrate(params, travel_time=None, diversity=None):
    """The settings for the stated targets (a target left None is not set): {"tile_radius": ..., "tile_value_mode": ..., "tile_within_mode": ..., "tile_spread": ...}."""
    settings = {}
    if travel_time is not None:
        settings.update(travel_time_settings(params, travel_time))
    if diversity is not None:
        settings.update(diversity_settings(params, diversity))
    return settings


def policy_points(session, agent="nearest", seeds=range(6), **overrides):
    """A proxy for `value_maps.solve_gain`: a function of a ValueMap that returns the mean points the registry agent `agent` earns on one world per seed of `session` (the simulator; `overrides`,
    for example `session_duration`, are `load_session` overrides) when the session pays that map. `nearest` and `oracle` are the reference policies of the plan (anchor c)."""
    import sim
    from agents import REGISTRY

    def points(valuemap):
        return float(sim.run_n(REGISTRY[agent], session, seeds, **{**overrides, **valuemap.compile()}).mean)
    return points


ANCHOR_AGENT = "learner"        # the registry agent whose points the gain holds equal across sessions: a mid-quality learner, whose parameters are to be tuned toward the human data over time (docs/DECISIONS.md, "The anchor is a mid-quality learner")
ANCHOR_POINTS = 750.0           # the points `ANCHOR_AGENT` earns in a 120 s session of the reference (FOR_S1, the additive map at gain 1, the default layout): 754 +- 7 on 40 worlds, rounded
FRUIT_CAP = 9                   # the per-fruit range of every session is 0 to this (PI, 2026-11-17)
MAX_PEAK = 8.0                  # so the best bush is worth at most this: with the noise (SD 0.6) a fruit of the best bush stays at or below FRUIT_CAP


def check(session, valuemap, settings, seeds, agents=("nearest", "oracle"), **overrides):
    """What a realised session is on fresh worlds: for each seed generate the world (the map and the layout `settings` on `session`), measure it and run each registry agent on it.
    Returns {"factors": {name: (mean, standard error)}, "points": {agent: (mean, standard error)}}."""
    import sim
    from agents import REGISTRY
    params = load_session(session, **overrides, **settings, **valuemap.compile())
    worlds = [generate_world(params, s) for s in seeds]
    rows = [measure(w) for w in worlds]
    n = len(rows)
    stats = lambda x: (float(np.nanmean(x)), float(np.nanstd(x, ddof=1) / math.sqrt(n)) if n > 1 else float("nan"))
    return {"factors": {k: stats([r[k] for r in rows]) for k in rows[0]},
            "points": {a: stats(sim.run_n(REGISTRY[a], worlds=worlds).totals) for a in agents}}


def realize(session, gini, interaction, klass, travel_time, diversity, anchor=ANCHOR_POINTS, agent=ANCHOR_AGENT, seeds=range(12), check_seeds=range(1000, 1040), tolerance=0.05, steps=4, max_peak=MAX_PEAK, corner=(1.0, 1.0), **overrides):
    """A session from four knobs (milestone 3's calibrators together): the Gaussian with the stated sparsity (`gini`) and complexity (`klass`, `interaction`), the tile layout with the stated `travel_time`
    and within-patch `diversity` (reward units), and the gain at which `agent` earns `anchor` points in a session. Returns {"map": the ValueMap (gain included), "settings": the layout settings,
    "fields": the serialized SessionConfig fields of both, "achieved": `check` on fresh worlds, "within_tolerance": whether the anchor was met, "rounds": how many}.

    The pieces depend on one another: a diversity in points scales with the gain, and the points depend on the layout (a longer walk earns less), so the layout is solved for the current gain and the
    gain for the current layout on the worlds of `seeds`, round after round until the gain changes by less than 5 percent (at most `steps`; ValueError if it does not settle). Those few worlds give
    the points a sampling error of several percent, so a correction pass follows: `check` on the fresh `check_seeds` (40 worlds, common to every session, so sessions are equal on the same worlds; the points of one world vary by a third under a high contrast, so against the population the standard error is about 5 percent), and while the points are off the
    `anchor` by more than `tolerance` (a share) the gain is scaled by anchor / points, the layout re-solved for it and the session checked again (at most twice). `overrides` are `load_session`
    overrides (for example `session_duration`)."""
    base = load_session(session, **overrides)
    shape_map = value_maps.calibrate_map(gini, interaction, klass, std=float(base.reward_std), corner=corner)
    with_gain = lambda g: value_maps.ValueMap(shape_map.bumps, shape_map.noise, {"type": "gain", "value": float(g)})
    current, rounds = shape_map, 0
    for rounds in range(1, steps + 1):
        settings = calibrate(load_session(session, **overrides, **current.compile()), travel_time, diversity)
        solved = value_maps.solve_gain(shape_map, policy_points(session, agent, seeds, **overrides, **settings), anchor, rel_tol=0.03)
        settled = abs(solved.gain() / current.gain() - 1.0) < 0.05
        current = with_gain(solved.gain())
        if max_peak is not None and current.descriptors()["max"] > max_peak * 1.15:
            break                                                     # far over the cap already: no point in refining; the check below refuses it
        if settled:
            break
    else:
        raise ValueError(f"the gain and the layout did not settle in {steps} rounds (gain {current.gain():.3f}); lower the diversity or the travel time, or raise `steps`")
    achieved = check(session, current, settings, check_seeds, agents=tuple(dict.fromkeys(("nearest", "oracle", agent))), **overrides)
    for _ in range(2):
        points = achieved["points"][agent][0]
        if abs(points / anchor - 1.0) <= tolerance:
            break
        current = with_gain(current.gain() * anchor / points)
        settings = calibrate(load_session(session, **overrides, **current.compile()), travel_time, diversity)
        achieved = check(session, current, settings, check_seeds, agents=tuple(dict.fromkeys(("nearest", "oracle", agent))), **overrides)
    within = abs(achieved["points"][agent][0] / anchor - 1.0) <= tolerance
    peak = current.descriptors()["max"]
    if max_peak is not None and peak > max_peak:
        raise ValueError(f"the best bush would be worth {peak:.1f} points (gain {current.gain():.2f}), over the cap of {max_peak}: this sparsity cannot hold the anchor of {anchor:.0f} points within the per-fruit range of 0 to {FRUIT_CAP}")
    return {"map": current, "settings": settings, "fields": {**current.fields(), **fields(settings)}, "achieved": achieved, "within_tolerance": within, "rounds": rounds}


def fields(settings):
    """The SessionConfig field settings (serialized names) of calibrated `settings`, for a design module."""
    return {_camel(k): v for k, v in settings.items()}


def verify(session, settings, seeds, **overrides):
    """Generate a world of `session` with `settings` for each seed and measure it: [measure(world)], one dict per seed."""
    params = load_session(session, **{**overrides, **settings})
    return [measure(generate_world(params, s)) for s in seeds]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["measure", "calibrate"])
    ap.add_argument("session", help="a session asset name, e.g. FOR_S1")
    ap.add_argument("--seeds", default=None, help="world seeds, e.g. 0-9 or 1,2,7 (default: the session's own seed)")
    ap.add_argument("--travel-time", type=float, default=None, help="calibrate: target travel time in seconds")
    ap.add_argument("--diversity", type=float, default=None, help="calibrate: target within-patch reward SD")
    args = ap.parse_args()
    params = load_session(args.session)
    if args.command == "calibrate":
        settings = calibrate(params, args.travel_time, args.diversity)
        print("settings:", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in settings.items()})
        seeds = _parse_seeds(args.seeds) if args.seeds else list(range(10))
        rows = verify(args.session, settings, seeds)
        for key, target in (("travel_time", args.travel_time), ("diversity", args.diversity)):
            if target is not None:
                got = np.array([r[key] for r in rows])
                print(f"  {key}: target {target}, realised {got.mean():.3f} +- {got.std():.3f} over {len(seeds)} worlds ({100 * (got.mean() - target) / target:+.1f}%)")
        print("  what else (mean over the worlds): " + ", ".join(f"{k} {np.mean([r[k] for r in rows]):.3f}" for k in ("contrast", "diversity", "mean_bush_value", "bush_gini", "n_tiles")))
        return
    seeds = _parse_seeds(args.seeds) if args.seeds else [int(params.world_seed)]
    rows = [measure(generate_world(params, s)) for s in seeds]
    print(f"{args.session}, {len(seeds)} world(s), seeds {seeds[0]}" + (f" to {seeds[-1]}" if len(seeds) > 1 else ""))
    for key in rows[0]:
        values = np.array([r[key] for r in rows], dtype=float)
        print(f"  {key:26s} {np.nanmean(values):9.3f}" + (f" +- {np.nanstd(values):.3f}" if len(seeds) > 1 else ""))
    print("map descriptors:")
    for key, value in map_descriptors(params).items():
        print(f"  {key:26s} {value:9.3f}")


def _parse_seeds(text):
    seeds = []
    for part in text.split(","):
        lo, _, hi = part.partition("-")
        seeds.extend(range(int(lo), int(hi or lo) + 1))
    return seeds


if __name__ == "__main__":
    main()
