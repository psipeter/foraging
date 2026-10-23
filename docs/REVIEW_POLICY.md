# docs/REVIEW_POLICY.md — what code review optimizes, and who decides

Used by the adversarial review (`/adversarial-review`: the **red-team**, **simplifier** and **arbiter** agents in `.claude/agents/`).
The red-team argues for more (guards, tests, handling); the simplifier argues for less. This file is what the arbiter weighs them
against. `CLAUDE.md` is the source of truth for conventions and hard research constraints; this file adds the priorities and the
complexity budget. The person owns it: edit it when the goals change.

---

## What the code is for (in priority order)

1. **Participant data is complete, correct and replayable.** The logs plus the world file must reproduce what happened
   (`scripts/replay.py`). A bug that loses or corrupts a session is the worst kind; a silent one is worse than a loud one.
2. **Results stay comparable over time.** Simulated results are keyed by environment and code hashes; a change that silently
   changes what a stored number means (or that moves the hashes for no reason) costs more than its line count suggests.
3. **Research tool first, game second.** Ecological validity, perceptual clarity of bush attributes and unambiguous reward feedback
   outrank polish and gameplay. Changes to the visual channels, reward system, data format and session flow are scientific design.
4. **The agent ladder is trustworthy.** The simulator mirrors the game closely enough that agent-versus-human comparisons mean
   something, and what an agent may know is enforced by the interfaces, not by habit.
5. **A researcher can read it.** Small, plain code that one person can hold in their head; documentation that says *why*.

When two of these pull apart, the lower number gives way, except that a clarity cost never justifies removing a check that protects 1 or 2.

## The complexity budget

Complexity is spent where a failure is silent, expensive or unrecoverable, and saved everywhere else.

- **Validate at boundaries, where files, logs, configs and humans enter** (loaders, manifests, world files, `SessionConfig`): fail
  loudly, with a message that says what to do. These checks are cheap and are worth their lines.
- **Check internal invariants with tests, not runtime machinery.** A property test (time is conserved, the planner equals a brute
  force, the Python rule equals the C# rule on generated input) beats a defensive branch. A single `raise` is justified only where the
  alternative is a silent wrong answer or a hang that would corrupt a whole batch.
- **Mirrored code gets a test that compares the two sides**, not a comment asking people to keep them in sync (a comment is
  still required where the mirror is not testable, e.g. C# against Python).
- **No speculative generality.** A parameter, hook, class or option needs a second user today, or a value a researcher will vary
  (then it belongs in `SessionConfig` or `costs.py`, per `CLAUDE.md`). "It might be useful when we add X" is not a reason.
- **A fix pays for itself.** Anything costing more than about 30 lines, a new concept, or a new file must name the failure it prevents
  and say how it would happen. Below that, adopt a red-team fix when its severity is medium or higher, or when it is a line or two.
- **A test must be able to fail.** A test that survives every plausible mutant of the rule it names (see `scripts/mutation_check.py`)
  should be strengthened or deleted. Tests assert behavior, not implementation.
- **Docs say why.** Record non-obvious constraints and rejected alternatives in `docs/DECISIONS.md`; do not restate code in comments.
  A doc that no longer matches the code is a defect, not a nit.

## Severity and what to do

| Severity | Meaning | Default action |
|---|---|---|
| blocker | corrupts or loses data or results | fix before committing |
| high | wrong behavior a user will hit | fix before committing |
| medium | wrong in a plausible case, or fails silently | fix, or record as known-and-deferred with a reason |
| low | latent, cosmetic, or needs an unlikely setup | batch, or defer |
| nit | taste | skip unless free |

## Escalate to the person (never decide)

- Anything touching **scientific design**: visual channels, the reward system, data logging columns or paths, session flow, task
  parameters, what is counted as a response.
- Changes to what stored results mean, or that move the code hashes of `ENGINE_FILES` / `AGENT_FILES`, unless the change is already
  being made for another reason (then say so).
- A disagreement about a **goal** rather than a means.
- Anything the arbiter cannot decide with confidence from this repository; say what fact would settle it.

## Tie-breaks

When the options are otherwise equal, take the smaller change. When a check protects data or comparability, keep it even if it
is ugly. When a past decision in `docs/DECISIONS.md` rejected an alternative, a reviewer who wants it back must say what changed.
Reviewers propose; nothing is applied without the person's go-ahead (the simplifier's small, behavior-preserving tier included,
when it runs under `/adversarial-review`).

## Known and deferred (reviewers: do not re-report; the person maintains this list)

Re-raise one only with new evidence or because the code around it changed.

- `replay.verify` compares float32 game timing against double replay: spurious one-frame fruit mismatches (about 0.1-0.3 per 1000
  fruits) are possible; `TIME_TOL` is the only absorber.
- `trial_start` is applied one frame early in `replay.py` and `visibility.py` (the row at that time still has the old pose).
- `WorldKnowledge.from_sidecar` drops the reward function, so an oracle over a sidecar without a `value` entry cannot compute values.
- Every S1/S2 Interlude has one free "either" trial, so chance accuracy there is 0.6, not 0.5 (matches the game's bonus rule).
- Visibility samples 1.8% of canopy points below the terrain; a few count as visible.
- Non-finite critic utilities (`inf`, `nan`) are not rejected by the choice rules.
- The actor's RNG exposes the world seed. The information boundary guards against accidents, not against a deliberate cheat.
- `costs.py`: the W-press time is a guess and every constant is fitted to the developer's debug sessions, not participants. The
  decision time between actions is not modelled.
- The simulator pays about 0.9 more fruits per 60 s than the game (frame quantisation): compare agents to humans as paired
  differences.
