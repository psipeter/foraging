"""The factors of a session as realised in a generated world (docs/SESSION_FACTORS_PLAN.md, milestone 1): what to measure on a world, so that a knob's target can be compared with what was made.

    ./venv/bin/python scripts/factors.py measure FOR_S1 [--seeds 0-9]

`measure(world)` takes a world from `world.generate_world` and returns the patch factors (travel time, contrast between tiles, diversity within a tile), the mean bush value (anchor a of the
plan), the bush Gini, the realised per-fruit noise and the descriptors of the reward map (`value_maps.descriptors`, the part that does not depend on the world's draw). A tile is a patch: its
cluster of bushes. Nothing here changes a world; it only reads one.
"""

import argparse

import numpy as np

import tiles
import value_maps
from world import bush_value, generate_world, load_session

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
            "n_tiles": int(ts.n_tiles), "n_bushes": int(len(v)), "walk_visits": float(params.session_duration) / (gap / speed)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["measure"])
    ap.add_argument("session", help="a session asset name, e.g. FOR_S1")
    ap.add_argument("--seeds", default=None, help="world seeds, e.g. 0-9 or 1,2,7 (default: the session's own seed)")
    args = ap.parse_args()
    params = load_session(args.session)
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
