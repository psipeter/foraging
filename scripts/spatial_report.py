"""How much does spatial balancing improve the evenness of a session's reward, and is it better than just choosing another seed?

    ./venv/bin/python scripts/spatial_report.py S2 S7 [--seeds 20] [--best-of 5] [--target 0.3]

For each session, `--seeds` random worlds (seeds 0, 1, ...) are measured as drawn (Off), after the tile-balanced assignment (Tiles) and after that plus swaps
(TilesAndSwaps, to `--target`), with the metrics of `spatial.py` (cost 1 = a random world, lower = more even). "Best of K" takes the most even of every K consecutive random
seeds, which is what choosing a new seed (a seed search) gives. Only the records are rearranged, so the same worlds are compared.
"""

import argparse

import numpy as np

import spatial
import world


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("sessions", nargs="+")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--best-of", type=int, default=5)
    parser.add_argument("--target", type=float, default=spatial.TARGET)
    args = parser.parse_args()
    print(f"cost (1 = random world), local-mean spread ratio at scales {spatial.SCALES}, largest cluster of top-decile bushes; mean over {args.seeds} seeds")
    for name in args.sessions:
        params = world.load_session(name, spatial_balance=0)
        rows = {"Off": [], "Tiles": [], "Tiles+swaps": []}
        for seed in range(args.seeds):
            w = world.generate_world(params, seed)
            rng = np.random.default_rng(seed + 10_000)
            index = spatial.tile_assignment(w.pos, w.value, rng)
            swapped, _ = spatial.optimise(w.pos, w.value, rng, start=index, target=args.target)
            for key, values in (("Off", w.value), ("Tiles", w.value[index]), ("Tiles+swaps", w.value[swapped])):
                rows[key].append(spatial.metrics(w.pos, values))
        print(f"\n{name}")
        for key, ms in rows.items():
            cost = np.array([m["cost"] for m in ms])
            scales = " ".join(f"{np.mean([m[s]['local_value'] for m in ms]):.2f}" for s in spatial.SCALES)
            print(f"  {key:12s} cost {cost.mean():.2f} (sd {cost.std():.2f})  local {scales}  cluster {np.mean([m['cluster'] for m in ms]):.1f}")
        base = np.array([m["cost"] for m in rows["Off"]])
        k = args.best_of
        best = [base[i:i + k].min() for i in range(0, len(base) - k + 1, k)]
        print(f"  best of {k} seeds  cost {np.mean(best):.2f}  (the most even of every {k} random worlds)")


if __name__ == "__main__":
    main()
