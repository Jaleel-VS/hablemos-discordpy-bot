---
name: plan-code-judge
description: "Three-step multi-model workflow: plan with Fable 5 (or the current session's model), implement with Codex CLI on a subscription, adversarially review the diff. Use when the user wants to run a feature through the plan/implement/judge loop, mentions using Codex to implement a plan, or references this repo's plan→codex→review pattern."
trigger: /plan-code-judge
---

# /plan-code-judge

Runs a feature through three deliberately separated steps so the
token-hungry implementation step lands on a flat-rate subscription
(Codex CLI) instead of metered API billing, while the token-light
planning and review steps stay on the strongest available model.

Rationale (don't re-derive this every run — it's already decided):
coding burns far more tokens than planning or reviewing a diff, so the
expensive model should only ever see small inputs/outputs. See
`plans/` for prior art on this repo's plan-doc conventions — this
skill writes into the same directory, same flat naming, no new
subdirectory for plans (only `plans/reviews/` for review verdicts, to
avoid cluttering the flat plan list with a second doc per feature).

## When to use

Invoke on `/plan-code-judge <feature description>`, or when the user
describes a feature and asks to use this repo's plan/implement/review
flow. Skip it for trivial one-line fixes — the point of this skill is
amortizing model-switch overhead over work substantial enough to
justify a written spec.

## Step 1 — Plan (this session's model, not Codex)

Write a full implementation spec to `plans/<feature-slug>.md`,
matching the style of existing files in `plans/` (see
`plans/wcbet-odds.md` for the target density: verified source facts,
a product-decisions table, and phased implementation steps — not a
vague paragraph).

The spec must be detailed enough that an implementer with **no other
context** can execute it without coming back to ask questions — that
is the single biggest lever on whether this workflow actually saves
money (see `docs/` or ask the user if unsure about a project
convention; don't guess and leave it out of the spec).

Include explicitly:
- Exact files to touch, and what changes in each
- Edge cases and how to handle them
- What "done" looks like (a concrete acceptance check, not "it works")
- Any project conventions the implementer must follow (this repo:
  AGENTS.md — ruff clean, tests updated, docs updated in the same
  commit, `None`-handling rules, no hardcoded IDs)

Do not proceed to Step 2 until the spec file exists and you've shown
its path to the user for a quick look — a bad plan is not worth
implementing cheaply.

## Step 2 — Implement (Codex CLI, subscription-billed)

Hand the plan file to Codex non-interactively. Do **not** paste the
plan content into the prompt — point Codex at the file so it reads
full context itself and so the plan stays the single source of truth
if it's revised later.

```bash
codex exec -s workspace-write "Implement plans/<feature-slug>.md exactly as specified. Ask nothing — if something is genuinely ambiguous, make the most conservative choice consistent with this repo's AGENTS.md and note the choice in your final summary."
```

Notes:
- `-s workspace-write` allows file writes in the repo without a
  sandbox-permission prompt per edit; omit `--dangerously-bypass-approvals-and-sandbox`
  entirely — this is not an environment that needs it.
- Default reasoning effort (leave `-c model_reasoning_effort=...`
  unset) is usually right for well-specified implementation work.
  Only raise it (`-c model_reasoning_effort="high"`) if the plan
  itself flags the task as algorithmically hard or high-risk — raising
  effort by default defeats the point of routing this step to the
  cheap tier.
- If Codex's summary flags an ambiguity it resolved on its own,
  surface that to the user before Step 3 — the judge step should know
  about it too.

## Step 3 — Judge (this session's model, adversarial)

Review Codex's actual diff against the plan — never a re-explanation,
always the real diff:

```bash
git diff -- <files Codex touched>
```

Then produce a verdict, written to `plans/reviews/<feature-slug>.md`,
with one of three explicit outcomes so the loop doesn't rely on
eyeballing prose:

- `ship` — diff satisfies the plan, no correctness or convention gaps
- `needs-revision` — lists specific, actionable feedback to hand back
  to Codex for a second pass (do NOT re-run the whole plan step for a
  revision — feed only the specific feedback back to Codex exec)
- `no-ship` — fundamental mismatch with the plan or a correctness bug
  serious enough that revision isn't the right next step; explain why

Review adversarially, not just for spec-compliance — question the
implementation choices, edge cases the plan may have missed, and
whether the diff does what it claims, the same way `/codex:adversarial-review`
(the reverse-direction version of this same idea, already installed
via the `openai-codex` plugin) challenges a Claude-authored change.

On `needs-revision`, re-invoke Codex with only the review's specific
feedback (not the original plan again):

```bash
codex exec -s workspace-write "Address this review feedback on your prior change to <files>: <feedback>. Keep the rest of the implementation as-is."
```

Then re-review the updated diff. Loop until `ship` or `no-ship`.

## What this skill deliberately does not do

- It does not manage a ledger, ranked executor tiers, or a subagent
  roster — this is a fixed three-step pipeline for exactly two
  models, not a general task router. If broader multi-tier routing is
  ever wanted, that's a different tool
  (`Zihao-Wu06/claude-code-orchestrate` is one such framework) — don't
  grow this skill into that shape.
- It does not run Codex from inside a sandboxed/read-only Codex
  session (e.g. the shared runtime some Claude Code sessions use for
  `/codex:review`) — Step 2 needs real write access, so it must run
  from a normal Codex CLI invocation, not through a plugin session
  that's pinned to read-only.
