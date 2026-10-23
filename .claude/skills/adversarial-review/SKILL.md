---
name: adversarial-review
description: Review new or changed code adversarially before the person commits. Runs the red-team (finds defects, test gaps, doc drift, by evidence) and the simplifier (finds needless complexity) in parallel on the same diff, lets them answer each other, sends unresolved conflicts to the arbiter agent for a decision against the project's goals, and escalates scientific-design questions to the person. Reports; applies nothing until the person says so. Usage - /adversarial-review [--since REF] [--no-rebuttal] [--save] [paths...]
---

You orchestrate an adversarial review of this repository's code. Subagents cannot spawn subagents, so you (the main session) run the protocol. The three agents are in `.claude/agents/`: `red-team` (argues for more checks, tests, handling), `simplifier` (argues for less complexity), `arbiter` (decides conflicts against `docs/REVIEW_POLICY.md`). Read `docs/REVIEW_POLICY.md` and `CLAUDE.md` yourself first; you apply the escalation rules too.

Arguments (`$ARGUMENTS`): `--since REF` (default `HEAD`: uncommitted and untracked changes), `--no-rebuttal` (skip step 4), `--save` (write the final report to `docs/reviews/<date>-<slug>.md`), and optional paths to restrict the scope.

## 1. Scope and intent

- List the target: `git diff --stat <ref>` plus `git ls-files --others --exclude-standard`, restricted to the given paths. Ignore `.meta`, generated files (`*.world`, `*.interlude.json`), `Library/`, `ForagingData/` and the person's Inspector churn (`.asset`/`.mat`), but name generated files if their source changed (staleness is a finding).
- If nothing is in scope, say so and stop.
- State the **intent** of the change in two or three sentences for the reviewers (from the conversation, the draft commit message, or the `docs/DECISIONS.md` entry; ask the person one question only if it cannot be inferred). Reviewers judge a change against its intent.
- Note which files are **hash-sensitive** (`ENGINE_FILES`, `AGENT_FILES`) or **mirrored** (CLAUDE.md), and the **temporary settings** in `docs/SCIENCE.md`, so the reviewers know.
- Make a scratch directory under your scratchpad for the reports.

## 2. Round one: red-team and simplifier in parallel

Send both Agent calls in one message. Each brief contains: the scope (the exact `git diff` command and file list), the intent, the hash-sensitive and mirrored notes, the path to write its report to, and "read `docs/REVIEW_POLICY.md`, including **Known and deferred**: do not re-report those".

- **red-team:** mutation testing is optional and low priority. Tell it to run `scripts/mutation_check.py` only if the diff changes engine, planner, replay or other rule code with thresholds (not docs, tooling or glue), and to prefer hand mutants of specific rules.
- **simplifier:** tell it explicitly: *"Dry-run mode. Do not apply any change, including the small tier; list every change you would make with file:line, why, the behavior-preservation argument and the verification you would run. Do not edit the project."* (Its default is to apply small fixes; under this review nothing is applied until the person agrees.)
- Both must give each finding or proposal a stable ID (`RT-n`, `SM-n`) and say whether it touches scientific design.

Do not paraphrase their findings when you read them; keep the reports as files.

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

A rerun after changes is cheap if you give the reviewers the previous **Checked and held up** lists (from a saved report) and tell them to focus on what changed since. Findings the person declined go in **Known and deferred** so they are not re-reported.

## Cost

Round one is two long-running Opus-level reviews in parallel; the rebuttal is a short continuation of each; the arbiter runs only when a conflict remains. For a small diff, running only the red-team (or only the simplifier) directly is fine; use the full protocol before committing anything that touches the engine, the logger, the replay or the agents.
