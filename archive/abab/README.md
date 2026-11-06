# ABAB design (archived 2026-11-06)

An optional session design in which two complete feature sets (A: `warm_arc` colours + height-only capsule canopies; B: `cool_arc` + width-only) alternate
from session to session, built so that what a participant learns about one session's reward mapping cannot carry over to the next. After playtesting, the PI
kept the default design (the shared aspect axis and the plasma ramp on every session), so the code was removed from the project. Why it was built, what
was learned and what to revisit: `docs/DECISIONS.md` ("ABAB ..." entries) and `docs/SCIENCE.md`.

Contents
- `feature_sets.py`, `shape_sets.py`, `build_sessions.py` (the Python side, from `scripts/`), their tests `test_*.py`.
- `DesignVariant.cs`, `AbabSequences.cs` (from `Assets/Scripts/Session/`; the `.meta` files were not kept, Unity makes new ones).
- `removal.patch`: what was taken out of files that stay (`Tree.cs` capsule canopy, `SessionConfig.cs` `CanopyForm` / `FruitSizeFollows` fields,
  `GameManager.cs` design toggle, `OnlineSettings.cs` `-design`, `world.py` field defaults, `fruit_ramp.py` hue-arc ramps, `ladder.py` helpers, `.gitignore`).
  Re-apply it in reverse from the repository root: `patch -R -p1 < archive/abab/removal.patch`, then restore the files above, then
  `scripts/build_sessions.py <sessions> --wire` (it also needs `scripts/fruit_ramp.py` arcs and `AbabSequences` created through the Unity CLI).
  Generated files (variant assets `<S>_A`, `<S>_B`, their worlds, `Resources/AbabSequences.asset`) were deleted; rebuild them with the script.
- The capsule canopy and the shape sets were first committed in d6f3576 (`git show d6f3576:Assets/Scripts/Trees/Tree.cs` has the earlier shape-set code
  but not the capsule canopy, which only exists in `removal.patch`).
