"""The fruit colour ramp: how it was chosen and where its stops come from (docs/DECISIONS.md, "Fruit colour ramp").

    ./venv/bin/python scripts/fruit_ramp.py                # score the candidate ramps (table)
    ./venv/bin/python scripts/fruit_ramp.py --stops        # the chosen ramp as the SessionConfig.fruitColorRamp stops
    ./venv/bin/python scripts/fruit_ramp.py --stops --ramp viridis   # another matplotlib colour map
    ./venv/bin/python scripts/fruit_ramp.py --stops --ramp warm_arc   # warm_arc / cool_arc: the two constant-lightness hue arcs (below)
    ./venv/bin/python scripts/fruit_ramp.py --png out.png  # swatches under normal, protan, deutan and tritan vision

A ramp maps the colour attribute (0..1) to a fruit colour. The aim is equal perceptual steps along the ramp (CIE-like distance in
OKLab), steps that survive colour-vision deficiency and lighting changes, and a mix of hue and lightness. `ramp(name)` returns the
ramp re-spaced so that equal attribute steps are equal OKLab distances, as `STOPS` evenly spaced sRGB colours that Unity
interpolates linearly. Not an engine file: nothing here is read by the simulator.
"""

import argparse

import matplotlib
import numpy as np

STOPS = 21
CHOSEN = "plasma"

# OKLab (Ottosson) from linear sRGB.
_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566], [0.0883024619, 0.2817188376, 0.6299787005]])
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099], [0.0259040371, 0.7827717662, -0.8086757660]])

# Colour-vision deficiency simulation (Machado, Oliveira and Fernandes 2009, severity 1.0), applied to linear sRGB.
CVD = {"normal": np.eye(3),
       "protan": np.array([[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]]),
       "deutan": np.array([[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]]),
       "tritan": np.array([[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]])}
# Lighting conditions as per-channel multipliers of linear light.
LIGHT = {"neutral": (1, 1, 1), "dim": (.6, .6, .6), "bright": (1.3, 1.3, 1.3), "warm dusk": (1.1, .95, .7), "cool": (.85, 1, 1.2)}
# Approximate canopy and ground colours (sRGB) the fruit must stand out against.
BACKGROUNDS = {"dark canopy": (0.15, 0.35, 0.15), "light canopy": (0.35, 0.55, 0.25), "ground": (0.55, 0.5, 0.35)}


def to_linear(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(lin):
    lin = np.clip(lin, 0, 1)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)


def oklab(lin):
    return (_M2 @ np.cbrt(_M1 @ np.asarray(lin, float).T)).T


def distance(a, b):
    """Perceptual distance (OKLab x 100) between two linear-RGB colours."""
    return 100 * float(np.linalg.norm(oklab(np.clip(a, 0, 1)) - oklab(np.clip(b, 0, 1))))


def _colormap(name, n=41):
    cmap = matplotlib.colormaps[name]
    return to_linear([cmap(x)[:3] for x in np.linspace(0, 1, n)])


def _equal_steps(lin):
    """The path `lin` (linear RGB) resampled so equal parameter steps are equal OKLab distances."""
    lab = oklab(lin)
    along = np.r_[0, np.cumsum(np.linalg.norm(np.diff(lab, axis=0), axis=1))]
    index = np.interp(np.linspace(0, 1, STOPS), along / along[-1], np.arange(len(lin)))
    low = np.floor(index).astype(int)
    high = np.minimum(low + 1, len(lin) - 1)
    frac = (index - low)[:, None]
    return lin[low] * (1 - frac) + lin[high] * frac


# Candidates from the comparison (ramps 5 and 6 and the diverging ones were built from OKLCH anchors in the scratch
# prototype; only the library colour maps are kept here, since they are what was chosen between).
CANDIDATES = ("viridis", "cividis", "plasma", "YlGnBu_r", "PuOr_r")

# Two hue-arc ramps for alternating colour sets across sessions: constant OKLab lightness, hue sweeping 120 degrees at 92% of the
# largest chroma the sRGB gamut allows, so lightness carries no information. name: (lightness, start hue in degrees, sweep in degrees).
# warm_arc runs red-coral, orange, yellow-olive, green (hue 20 to 140); cool_arc teal, blue, violet, magenta (215 to 335): 75 degrees
# of wheel between them. See docs/DECISIONS.md, "Hue-arc colour sets".
ARCS = {"warm_arc": (0.65, 20, 120), "cool_arc": (0.65, 215, 120)}
ARC_CHROMA_FILL = 0.92


def _lin_from_oklab(lab):
    return (np.linalg.inv(_M1) @ ((np.linalg.inv(_M2) @ np.asarray(lab, float).T) ** 3)).T


def _lch(lightness, chroma, hue_deg):
    h = np.radians(hue_deg)
    return np.stack([np.full_like(h, lightness), chroma * np.cos(h), chroma * np.sin(h)], axis=-1)


def _max_chroma(lightness, hue_deg):
    """Largest chroma at this lightness and hue(s) that stays inside the sRGB gamut (bisection)."""
    low, high = np.zeros_like(hue_deg), np.full_like(hue_deg, 0.4)
    for _ in range(30):
        mid = (low + high) / 2
        lin = _lin_from_oklab(_lch(lightness, mid, hue_deg))
        inside = (lin.min(axis=-1) >= 0) & (lin.max(axis=-1) <= 1)
        low, high = np.where(inside, mid, low), np.where(inside, high, mid)
    return low


def _arc(lightness, start, sweep):
    """The hue arc as a dense linear-RGB path."""
    hue = (start + np.linspace(0, sweep, 201)) % 360
    return np.clip(_lin_from_oklab(_lch(lightness, _max_chroma(lightness, hue) * ARC_CHROMA_FILL, hue)), 0, 1)


def ramp(name=CHOSEN):
    """The ramp `name` (a matplotlib colour map, or one of ARCS) as STOPS linear-RGB colours at equal perceptual steps."""
    return _equal_steps(_arc(*ARCS[name]) if name in ARCS else _colormap(name))


def at(lin_ramp, t):
    """Linear-RGB colour at attribute value(s) `t` (linear interpolation between stops, as Unity does in sRGB)."""
    index = np.clip(np.asarray(t, float) * (len(lin_ramp) - 1), 0, len(lin_ramp) - 1)
    low = np.floor(index).astype(int)
    high = np.minimum(low + 1, len(lin_ramp) - 1)
    return lin_ramp[low] * (1 - (index - low)[:, None]) + lin_ramp[high] * (index - low)[:, None]


def seen(lin_ramp, vision="normal", light="neutral", n=21):
    return np.array(LIGHT[light]) * at(lin_ramp, np.linspace(0, 1, n)) @ CVD[vision].T


def steps(lin_ramp, vision="normal", light="neutral", gap=0.1):
    """Distances between attribute values `gap` apart (the smallest is what a participant has to rely on)."""
    colours = seen(lin_ramp, vision, light)
    k = round(gap * (len(colours) - 1))
    return np.array([distance(colours[i], colours[i + k]) for i in range(len(colours) - k)])


def score(lin_ramp):
    """Summary numbers of a ramp: step sizes per vision type, the worst over vision x lighting, the hue share of the change,
    and how much the contrast with the canopy and ground varies along the ramp."""
    colours = seen(lin_ramp)
    lab = oklab(np.clip(colours, 0, 1))
    k = 2
    d_light = 100 * np.abs(lab[k:, 0] - lab[:-k, 0])
    d_hue = 100 * np.linalg.norm(lab[k:, 1:] - lab[:-k, 1:], axis=1)
    contrast = np.array([min(distance(c, to_linear(b)) for b in BACKGROUNDS.values()) for c in colours])
    return {"normal": steps(lin_ramp).min(), "protan": steps(lin_ramp, "protan").min(), "deutan": steps(lin_ramp, "deutan").min(),
            "tritan": steps(lin_ramp, "tritan").min(),
            "worst": min(steps(lin_ramp, v, l).min() for v in CVD for l in LIGHT),
            "mean": steps(lin_ramp).mean(), "hue_share": d_hue.sum() / (d_hue.sum() + d_light.sum()),
            "contrast_min": contrast.min(), "contrast_spread": (contrast.max() - contrast.min()) / contrast.mean()}


def png(path):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(len(CANDIDATES), 4, figsize=(9, 1.1 * len(CANDIDATES) + 0.6))
    for row, name in enumerate(CANDIDATES):
        for col, vision in enumerate(CVD):
            axes[row, col].imshow(to_srgb(seen(ramp(name), vision, n=11))[None], aspect="auto")
            axes[row, col].set_xticks([])
            axes[row, col].set_yticks([])
            if row == 0:
                axes[row, col].set_title(vision, fontsize=9)
        axes[row, 0].set_ylabel(name, fontsize=8, rotation=0, ha="right", va="center")
    plt.tight_layout()
    plt.savefig(path, dpi=120)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--stops", action="store_true", help="print the chosen ramp's sRGB stops")
    parser.add_argument("--ramp", default=CHOSEN, help="colour map for --stops (default: the chosen ramp)")
    parser.add_argument("--png", help="write swatches of the candidates")
    args = parser.parse_args()
    if args.stops:
        print(", ".join("(%.4f, %.4f, %.4f)" % tuple(c) for c in to_srgb(ramp(args.ramp))))
    elif args.png:
        png(args.png)
    else:
        print("ramp | min step: normal / protan / deutan / tritan | worst vision x lighting | mean step | hue share | canopy contrast min, spread")
        for name in CANDIDATES:
            s = score(ramp(name))
            print(f"{name} | {s['normal']:.1f} / {s['protan']:.1f} / {s['deutan']:.1f} / {s['tritan']:.1f} | {s['worst']:.1f} | "
                  f"{s['mean']:.1f} | {s['hue_share']:.0%} | {s['contrast_min']:.0f}, {s['contrast_spread']:.2f}")


if __name__ == "__main__":
    main()
