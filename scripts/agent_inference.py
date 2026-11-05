"""Can the participants' analysis recover what an agent has learned from its choices?

An agent is shown what one participant experienced in a session (`human_agents.replay_into_agent`, fast mode), then makes choices in that
participant's Interlude, and `human_analysis.py`'s Interlude method (a logistic regression of the choice on the attribute differences,
right minus left, no intercept, with a small ridge) is applied to those choices unchanged. The weights it recovers are set beside two
references, both as least-squares weights on (shape, color, moisture):

    learned   the agent's own critic, read out on the Interlude's bushes: what the agent actually believes there
    ideal     the session's true reward on the session's bushes (`human_analysis.ideal`): what there was to learn

The agent chooses by a softmax on its critic's value difference with a temperature relative to the spread of its values over the Interlude's
bushes, since a greedy agent's choices are separable (the fit diverges) and its scale would not be recovered anyway. The scale of a choice
model is free, so weights are compared by their cosine, as `human_analysis.py` does. `draws` picks are sampled per trial from the agent's
choice probabilities; many draws take the sampling noise of the agent's choices out, which leaves the method's own error.

Only the Interlude is covered; the session's first-visit choices (`prior_carryover.py`) are not yet.

    ./venv/bin/python scripts/agent_inference.py [--agents learner,gp_mean,replay_len0_5] [--sessions S1,S2,S3,S4,S5] [--temperature 0.25] [--draws 200]
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agents  # noqa: E402
import human_agents  # noqa: E402
import human_analysis as ha  # noqa: E402
import replay  # noqa: E402
from idle_analysis import finished_runs  # noqa: E402

ATTRS = ha.ATTRS


def least_squares_weights(attrs, values):
    """Weight of each attribute (per unit) in the least-squares line `values ~ attrs + constant`, as `human_analysis.ideal` does for the true rewards."""
    X = np.column_stack([np.asarray(attrs, dtype=float), np.ones(len(attrs))])
    return np.linalg.lstsq(X, np.asarray(values, dtype=float), rcond=None)[0][:3]


def interlude_bushes(rows):
    """(attrs (m, 3), mean (m,)): each bush the Interlude's trials showed once, with the agent's critic value for it."""
    seen = {}
    for r in rows:
        for i in range(2):
            seen[r["ids"][i]] = (r["attrs"][i], r["mean"][i])
    return np.array([a for a, _ in seen.values()]), np.array([m for _, m in seen.values()])


def choice_sets(rows, temperature, draws, rng):
    """The agent's noisy Interlude choices as `human_analysis`'s sets [(attributes of left and right - 0.5, chosen index 1 = right, offset)]:
    `draws` per trial from a softmax on (value right - value left) / (temperature x the spread of the agent's values over the Interlude's bushes)."""
    _, mean = interlude_bushes(rows)
    scale = max(temperature * float(np.std(mean)), 1e-9)
    sets = []
    for r in rows:
        p_right = expit((r["mean"][1] - r["mean"][0]) / scale)
        X = np.array(r["attrs"], dtype=float) - 0.5
        sets.extend((X, int(c), np.zeros(2)) for c in rng.random(draws) < p_right)
    return sets


def recover(agent, folder, ideal, temperature=0.25, draws=200, ridge=0.1, seed=0):
    """Run the agent (which has learned from the session) through the participant's Interlude in `folder`, fit the participants' method to
    its choices and compare with what it learned. Returns the fitted weights and the cosines to the learned and the ideal weights."""
    rows = human_agents.interlude_comparison(agent, folder)
    attrs, mean = interlude_bushes(rows)
    learned = least_squares_weights(attrs, mean)
    beta, se, _, n = ha.fit(choice_sets(rows, temperature, draws, np.random.default_rng(seed)), [0, 1, 2], ridge)
    return {"fitted": beta, "se": se, "learned": learned, "ideal": ideal,
            "cos_fit_learned": ha.cosine(beta, learned), "cos_fit_ideal": ha.cosine(beta, ideal), "cos_learned_ideal": ha.cosine(learned, ideal),
            "agent_accuracy": human_agents.summarize_interlude(rows)["agent_accuracy"]}


def noise_points(rows, predictor="critic"):
    """[(x, picked right)] for the trials the participant answered: x is the value difference (right minus left) over the spread of values across
    the Interlude's bushes, so the scale matches `choice_sets`. `predictor` is "critic" (what the agent that learned from their session believes)
    or "true" (the bushes' true reward)."""
    if predictor == "critic":
        _, values = interlude_bushes(rows)
        diff = lambda r: r["mean"][1] - r["mean"][0]
    else:
        seen = {}
        for r in rows:
            seen[r["ids"][0]], seen[r["ids"][1]] = r["value_left"], r["value_right"]
        values = np.array(list(seen.values()))
        diff = lambda r: r["value_right"] - r["value_left"]
    sd = max(float(np.std(values)), 1e-9)
    return [(diff(r) / sd, r["participant"] == "right") for r in rows if r["participant"] is not None]


def fit_noise(points):
    """Maximum-likelihood (tau, lapse, log-likelihood, n, log-likelihood of coin flips) of  P(right) = lapse / 2 + (1 - lapse) * sigmoid(x / tau)
    for `points` [(x, picked right)]: the softmax temperature in the units `choice_sets` uses and the share of picks that are random. A participant
    whose choices run against the predictor has no such tau (it is infinite): the fit then reports a large one."""
    x, y = np.array([p[0] for p in points]), np.array([p[1] for p in points], dtype=float)

    @np.errstate(over="ignore", divide="ignore")
    def nll(theta):
        p = np.clip(expit(theta[1]) / 2 + (1 - expit(theta[1])) * expit(x / np.exp(theta[0])), 1e-9, 1 - 1e-9)
        return -float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))

    best = min((minimize(nll, [np.log(t), l], method="Nelder-Mead") for t in (0.1, 0.5, 2.0) for l in (-3.0, 0.0)), key=lambda r: r.fun)
    return float(np.exp(best.x[0])), float(expit(best.x[1])), -float(best.fun), len(x), len(x) * float(np.log(0.5))


def noise_main(args):
    """Per participant and agent: the temperature and lapse rate that best describe the participant's real Interlude picks, with the agent's
    critic and with the true reward as the predictor, pooled over the sessions and then per session."""
    index = {f"S{i}": f"{2 * i:02d}" for i in range(1, 6)}
    rows_by = {}
    for who, run in finished_runs().items():
        for name in args.sessions.split(","):
            folder = replay.DATA_DIR / run / index[name]
            log = replay.load_session_log(folder)
            world = human_agents.session_world(log)
            for agent_name in args.agents.split(","):
                fed = human_agents.replay_into_agent(agents.REGISTRY[agent_name](), log, world=world, fast=True)
                rows_by[(who, name, agent_name)] = human_agents.interlude_comparison(fed.agent, human_agents.interlude_folder(folder))
    pd.set_option("display.width", 200)
    out = []
    for who in sorted({k[0] for k in rows_by}):
        for agent_name in args.agents.split(","):
            for predictor in ("critic", "true"):
                if predictor == "true" and agent_name != args.agents.split(",")[0]:
                    continue                        # the true reward does not depend on the agent
                pooled = [pt for (w, _, a), r in rows_by.items() if w == who and a == agent_name for pt in noise_points(r, predictor)]
                tau, lapse, ll, n, ll0 = fit_noise(pooled)
                out.append({"who": who, "agent": agent_name if predictor == "critic" else "-", "predictor": predictor, "n": n, "tau": tau, "lapse": lapse,
                            "loglik gain over coin": ll - ll0})
    print(pd.DataFrame(out).round(2).to_string(index=False))
    print("\nper session (critic of the first agent)")
    first, per = args.agents.split(",")[0], []
    for (who, name, a), r in rows_by.items():
        if a == first:
            tau, lapse, ll, n, ll0 = fit_noise(noise_points(r, "critic"))
            acc = np.mean([y == (x > 0) for x, y in noise_points(r, "critic")])
            per.append({"who": who, "session": name, "tau": tau, "lapse": lapse, "critic predicts pick": acc})
    print(pd.DataFrame(per).round(2).to_string(index=False))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Recover an agent's learned attribute weights from its Interlude choices with the participants' method.")
    ap.add_argument("--agents", default="learner,gp_mean,replay_len0_5")
    ap.add_argument("--sessions", default="S1,S2,S3,S4,S5")
    ap.add_argument("--temperature", type=float, default=0.25)
    ap.add_argument("--draws", type=int, default=200)
    ap.add_argument("--ridge", type=float, default=0.1)
    ap.add_argument("--noise", action="store_true", help="instead: estimate the participants' choice temperature and lapse rate from their Interlude picks")
    args = ap.parse_args(argv)
    if args.noise:
        return noise_main(args)
    runs = finished_runs()
    index = {f"S{i}": f"{2 * i:02d}" for i in range(1, 6)}          # a session's folder in the run (P is 00, its Interlude 01)
    rows = []
    for who, run in runs.items():
        for name in args.sessions.split(","):
            folder = replay.DATA_DIR / run / index[name]
            log = replay.load_session_log(folder)
            world = human_agents.session_world(log)
            ideal = ha.ideal(world)
            for agent_name in args.agents.split(","):
                fed = human_agents.replay_into_agent(agents.REGISTRY[agent_name](), log, world=world, fast=True)
                r = recover(fed.agent, human_agents.interlude_folder(folder), ideal, args.temperature, args.draws, args.ridge)
                rows.append({"who": who, "session": name, "agent": agent_name, **{k: r[k] for k in ("cos_fit_learned", "cos_fit_ideal", "cos_learned_ideal", "agent_accuracy")},
                             **{f"fit {a[:5]}": r["fitted"][i] for i, a in enumerate(ATTRS)}, **{f"learned {a[:5]}": r["learned"][i] for i, a in enumerate(ATTRS)}})
    table = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(table.round(2).to_string(index=False))
    print("\nmean over participants")
    print(table.groupby(["session", "agent"])[["cos_fit_learned", "cos_fit_ideal", "cos_learned_ideal", "agent_accuracy"]].mean().round(2).to_string())


if __name__ == "__main__":
    main()
