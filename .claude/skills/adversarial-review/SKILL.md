---
name: adversarial-review
description: Review new or changed code adversarially before the person commits. Runs the simplifier (finds needless complexity, rates readability, lists the biggest simplifications) and then the red-team (finds defects, test gaps, doc drift, by evidence) on the same code, lets them answer each other, sends unresolved conflicts to the arbiter agent for a decision against the project's goals, and escalates scientific-design questions to the person. Reports; applies nothing until the person says so. Usage - /adversarial-review [--since REF] [--no-rebuttal] [--save] [paths...] | /adversarial-review --component "<name or description>" | /adversarial-review --module <paths...>
---

You orchestrate an adversarial review of this repository's code. Subagents cannot spawn subagents, so you (the main session) run the protocol. The three agents are in `.claude/agents/`: `red-team` (argues for more checks, tests, handling), `simplifier` (argues for less complexity), `arbiter` (decides conflicts against `docs/REVIEW_POLICY.md`). Read `docs/REVIEW_POLICY.md` and `CLAUDE.md` yourself first; you apply the escalation rules too.

Arguments (`$ARGUMENTS`): `--since REF` (default `HEAD`: uncommitted and untracked changes), `--no-rebuttal` (skip step 4), `--save` (write the final report to `docs/reviews/<date>-<slug>.md`), and optional paths to restrict the scope.

Two modes review code that already exists, with no diff. Both need the person's intent to be "is this the right balance of simplicity and robustness?", judged against `docs/REVIEW_POLICY.md`:
- `--module <paths...>`: the named files are the scope.
- `--component "<name or description>"`: a game component or functionality that may span many files (for example "harvest rules", "the Interlude", "world generation"). Step 1b builds the file list.
Without either flag the scope is a diff, as below.

## 1. Scope and intent

- List the target: `git diff --stat <ref>` plus `git ls-files --others --exclude-standard`, restricted to the given paths. Ignore `.meta`, generated files (`*.world`, `*.interlude.json`), `Library/`, `ForagingData/` and the person's Inspector churn (`.asset`/`.mat`), but name generated files if their source changed (staleness is a finding).
- If nothing is in scope, say so and stop.
- State the **intent** of the change in two or three sentences for the reviewers (from the conversation, the draft commit message, or the `docs/DECISIONS.md` entry; ask the person one question only if it cannot be inferred). Reviewers judge a change against its intent.
- Note which files are **hash-sensitive** (`ENGINE_FILES`, `AGENT_FILES`) or **mirrored** (CLAUDE.md), and the **temporary settings** in `docs/SCIENCE.md`; the red-team gets these notes, the simplifier does not (step 2).
- Make a scratch directory under your scratchpad for the reports.
- **Existing-code modes (`--module`, `--component`):** the scope is whole files (or the manifest's line ranges), not a diff. Say so in the reviewers' briefs, replace "changed lines" by "this code", and judge it against its stated purpose in `docs/SCIENCE.md` / `docs/DECISIONS.md`. Mutation testing is off unless the person asks for it. Do not stop for "nothing in scope"; stop only if the named files do not exist.

## 1b. Scoping a component (`--component` only)

Ask the **arbiter** (Agent, `subagent_type: arbiter`, fresh each time, read-only) to explore the repository and return a manifest as its reply (it cannot write files; save it to the scratch directory yourself), as data, not a verdict:
- the files and line ranges that implement the component (C# and Python, scenes' relevant components by name, `SessionConfig` fields it reads), the **mirrored pairs** (C# against Python), the tests that cover it, and the `docs/SCIENCE.md` / `docs/DECISIONS.md` entries about it;
- which files are hash-sensitive, and which generated files depend on it;
- a size estimate in lines of code, and what it left out on purpose and why.

Then show the person the manifest and the estimate and let them add or cut files before anything expensive runs. **Size cap:** if the code is over roughly 2,500 lines, have the arbiter split it into sub-components (for example the harvest rules versus the harvest UI) and let the person choose which to run first; several narrow reviews beat one diffuse one. C# can be read but not run: anything that needs Unity goes to Residual as "needs a playtest".

## 2. Round one: simplifier first, then red-team

The simplifier goes first so the red-team can see where code is proposed for deletion and does not add machinery there. Each brief contains: the scope (the exact `git diff` command and file list, or the manifest path in the existing-code modes), the intent, the path to write its report to, and "read `docs/REVIEW_POLICY.md`, including **Known and deferred**: do not re-report those".

**2a. simplifier.** Tell it explicitly: *"Dry-run mode. Do not apply any change, including the small tier; list every change you would make with file:line, why, the behavior-preservation argument and the verification you would run, and test each in a scratch copy. Do not edit the project."* (Its default is to apply small fixes; under this review nothing is applied until the person agrees.) Do not give it the hash-sensitive notes: it judges readability, compactness and preserved behavior, and the hash cost is accounted for here, in the report. It reports readability per module, its five largest simplifications and net lines removable.

**2b. red-team,** when the simplifier's report is written. Add to its brief: the simplifier's report path (read it first), the hash-sensitive (`ENGINE_FILES`, `AGENT_FILES`) and mirrored notes, and the temporary settings in `docs/SCIENCE.md`. Mutation testing is a last resort, not a routine step: tell it to find test gaps by reading and to run at most one or two cheap hand mutants to demonstrate a specific finding, never a sweep; `scripts/mutation_check.py` only if the code has engine, planner or replay rules with thresholds and the person asked for it.

Both give each finding or proposal a stable ID (`RT-n`, `SM-n`) and say whether it touches scientific design. Do not paraphrase their findings when you read them; keep the reports as files.

**Net lines.** In the report to the person, state the net change in lines the accepted items would make (code and tests separately). A review that adds much and removes little is a finding about the review: say which side added what.

## 3. Sort the results

Read both reports. Put every item in exactly one bucket:

- **Red only**, **Simplifier only**: no overlap with the other side.
- **Agreed**: both recommend compatible changes (or one concedes in step 4).
- **Conflict**: the two recommend opposite or incompatible things. Look for: the simplifier would remove, inline or delete code, a test or a guard that a red-team finding relies on or that kills a surviving mutant; the red-team proposes a new guard, abstraction, parameter or file the simplifier flags as speculative or redundant; both want to change the same lines differently; the red-team's fix touches a hashed or mirrored file the simplifier would leave alone (or vice versa).
- **Escalate**: touches scientific design (visual channels, reward system, data columns or paths, session flow, task parameters) or the hash/meaning of stored results. Never goes to the arbiter to be decided; goes to the person with a one-sentence question.

Be fair to both sides: a red-team finding that is real but costly is not a "conflict" unless the simplifier actually objects.

## 4. Round two: rebuttal (skip with `--no-rebuttal`, and when there are no conflicts)

Continue each finished reviewer with SendMessage (same agent, context intact), giving it the other side's items that conflict with its own, verbatim, and asking for each: **accept**, **reject** (with the evidence or reasoning), or **counter** (a smaller or different change). Cap the reply at about five lines per item. Items where one side accepts become **Agreed**. Keep the rest as unresolved conflicts.

## 5. Arbitration

Give the unresolved conflicts to the **arbiter** (Agent, `subagent_type: arbiter`): paths to both reports, the rebuttals, the list of conflicts with both sides' arguments, the intent. Do not tell it which side you favor. Its decisions are ADOPT-RED, ADOPT-SIMPLE, COMPROMISE or ESCALATE; carry ESCALATE items to the person unchanged.

## 6. Report to the person

Write it so the person can act on it without reading the three reports. Put the full reports in the scratchpad and name the paths; if `--save`, write the final report to `docs/reviews/<date>-<slug>.md`.

1. **Verdict:** one line, counts (found / agreed / arbitrated / for you).
2. **Safe to apply (agreed and small):** each with file, what and why, and what you would run to verify.
3. **Decided by the arbiter:** ID, decision, the rationale in a sentence, the change.
4. **For you (escalations and anything unresolved):** each as a question answerable in a sentence, with the two options and the cost of each.
5. **Declined or deferred:** what was rejected and why; propose additions to **Known and deferred** in `docs/REVIEW_POLICY.md` rather than editing it unasked.
6. **Residual:** mutation survivors nobody addressed (if any were run), "could not check" items (anything C# that needs a playtest), hash-sensitivity warnings (which files, what it does to the stored results).

Do **not** apply anything. End by offering to apply sections 2 and 3 (after the person answers section 4). When the person agrees: make the edits, run the verification from the reports (C#: `unity command recompile` and the console; Python: `./venv/bin/python scripts/run_tests.py --all`), report failures plainly, and leave committing to the person.

## Reruns

In the existing-code modes a rerun after changes is cheaper still when it names only the files that changed since the saved report. A rerun after changes is cheap if you give the reviewers the previous **Checked and held up** lists (from a saved report) and tell them to focus on what changed since. Findings the person declined go in **Known and deferred** so they are not re-reported.

## Cost

Round one is two long-running Opus-level reviews, one after the other; the rebuttal is a short continuation of each; the arbiter runs only when a conflict remains. For a small diff, running only the red-team (or only the simplifier) directly is fine; use the full protocol before committing anything that touches the engine, the logger, the replay or the agents.
