# Adversarial Review Plugin

Adds an `adversarial-review` skill that looks for the reasons a proposal will fail before anyone acts on it, and ends with one verdict.

## What this plugin does

The skill reviews a plan, design, diff, decision, or the output of another skill. It first states the best case for the proposal. Then it looks for problems through up to twelve lenses. Seven run every time: failure in hindsight, reversing the goal, hidden assumptions, a sweep of commonly missed categories (including multi-tenancy), a sweep for typical faults in AI-generated work, following the change forward, and questioning the framing. The rest (pinning down vague claims, asking for evidence, other people's viewpoints, separate thinking passes, and a chain of causes) are added for larger plans, designs and decisions. Each concern must pass a filter (real consequence, survives a counter-argument, has a concrete action, not a duplicate) and is rated against a fixed severity bar. A Critical needs a reachable trigger; without one, the concern is at most High.

The review ends with PROCEED, AMEND or RETHINK, followed by a list of known risks the user chose to live with. Whenever a concern was accepted or modified, the skill restates the whole plan with the changes built in, then waits for a go-ahead. It never implements anything itself.

It has two modes. **Interactive** (default) shows concerns one at a time and asks the user to accept, reject, modify, risk-accept or defer each. Each decision is written to the ledger as soon as it is made, so a walkthrough that is cut short resumes where it stopped. **Report** asks no questions and suits worker agents: it returns ranked concerns, a verdict and a list of open decisions. Repeat reviews keep an append-only ledger, re-check deferred and risk-accepted concerns at the end of each round, and stop after four rounds at most. If no artifact is given, the skill asks which one is meant (interactive) or stops (report).

**Triggers include:** "challenge this plan", "red-team this", "what could go wrong", "pre-mortem this", "adversarial review", "poke holes", "adversarial-review in report mode".

## The Flow

| Step | What happens |
|------|--------------|
| 1 | Pick the mode, find the artifact (ask, or stop in report mode, if there is none), set the criticality, check for a ledger |
| 2 | If the ledger shows a walkthrough cut short, resume at the first pending concern and skip to step 8 |
| 3 | State the best case for the proposal in two or three sentences |
| 4 | Generate candidate concerns: seven lenses always, more for plans, designs and decisions |
| 5 | Filter: consequence, counter-argument, actionability, duplicates |
| 6 | Rate severity (Critical, High, Medium) and mark each blocking or watch-item |
| 7 | Apply the budget: more than five Critical plus High means RETHINK and split the proposal |
| 8 | Interactive: write pending rows, then resolve each concern with the user and record each decision at once. Report: list concerns and open decisions |
| 9 | Round 2 and later: re-check deferred, risk-accepted, pending and open concerns, and append the result |
| 10 | Give one verdict (PROCEED, AMEND or RETHINK) and list known risks |
| 11 | If any concern was accepted or modified (interactive only), restate the revised plan with an integration table, then stop |
| 12 | Append the verdict to the ledger. Later rounds review only what changed. Hard limit of four rounds |

## Skill contents

| File | Purpose |
|------|---------|
| `skills/adversarial-review/SKILL.md` | Core skill: process, lens choice by artifact kind, severity bar, budget, modes, verdict, known risks, rounds and exit rules |
| `skills/adversarial-review/references/lens-questions.md` | Question banks for failure in hindsight, reverse the goal, and hidden assumptions |
| `skills/adversarial-review/references/lens-questions-extended.md` | Question banks for L6 to L12: pin down the claim, ask for the evidence, other seats, follow it forward, question the framing, separate thinking modes, chain of causes |
| `skills/adversarial-review/references/category-checklist.md` | Checklist of commonly missed areas, from security and multi-tenancy to input edge cases |
| `skills/adversarial-review/references/ai-output-checklist.md` | Typical faults in AI-generated plans and code, including session drift and thoroughness for show, with a quick test for each |
| `skills/adversarial-review/references/severity-downgrade-example.md` | Worked example of a Critical downgraded to High for lack of a reachable trigger |
| `skills/adversarial-review/references/ledger-format.md` | Ledger path, slug, row format, resolution values (including pending and risk-accepted), per-decision writes, resume, end-of-round re-check and round header, with a worked example |

## Install

```text
/plugin marketplace add keyz182/keyz-claude-skills
/plugin install adversarial-review@keyz-claude-skills
```

## Requirements

None. If the host offers a structured question tool, interactive mode uses it. The ledger is written under `${XDG_STATE_HOME:-~/.local/state}/adversarial-review/`. It is not under `~/.claude/`, because Claude Code asks permission for every write there.
