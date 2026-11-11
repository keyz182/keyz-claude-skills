# Ledger format

The ledger records every concern across review rounds. Later rounds do not
repeat settled points, a walkthrough cut short can resume, and the loop ends
on time.

## Location

`${XDG_STATE_HOME:-~/.local/state}/adversarial-review/<slug>.md`

Do not put the ledger under `~/.claude/`. Claude Code treats that tree as
sensitive, so every write there needs a permission prompt, or is blocked in
a headless run.

Work out the slug like this:

```bash
artifact="/abs/path/to/plan.md"   # or the literal word: inline
printf '%s|%s' "$artifact" "$PWD" | sha256sum | cut -c1-8
```

Then add `-` and a short kebab-case subject, for example
`3f9a1c2e-nightly-billing-job.md`. Create the directory if it is missing.
If the caller names a different ledger path, use that instead.

## Rules

- Append only. Never edit or delete an earlier row, even to fix a typo, a
  resolution or a severity. Write a new row that supersedes it.
- The latest row for a concern ID is its current state.
- Write as you go. Each row lands in the file before the next question is
  asked. Never hold rows back until the verdict.
- A concern is resolved only when the row's resolving artifact exists (the
  commit is in history, or the plan line is still in the plan) and no later
  change has touched it. If a later change touched it, the concern is open
  again. Note that in the next row.
- An ID never changes. If a re-check raises the severity, the ID keeps its
  first letter and the Severity column shows the new level.

## File layout

Each round has three parts, written in this order:

1. **Records.** The full concern record (SKILL.md section 6) for every
   concern found this round. Written once: at the start of the walkthrough
   in interactive mode, or with the report in report mode. A resumed
   walkthrough reads its records from here.
2. **Rows.** One table. New rows go on the end of the table as events
   happen.
3. **Verdict line.** `Verdict: <PROCEED | AMEND | RETHINK>`, written last,
   under the table. A round with no verdict line was cut short.

Older ledgers have six columns and no Note column. Read a missing Note as
empty.

## When to write a row

| Event | Mode | Row to append |
|-------|------|---------------|
| Walkthrough starts | interactive | One `pending` row per concern to be walked, in walk order |
| User answers a concern | interactive | One row for that ID with the chosen resolution, straight after the answer |
| Report is written | report | One `open` row per concern |
| End-of-round re-check (round 2 and later) | both | One row per checked concern, with the result in Note |
| Verdict is given | both | The verdict line under the table |

## Resume a walkthrough that was cut short

At set-up, look at the newest round. If the latest row for any ID there is
`pending`, the walkthrough stopped part way.

1. Do not re-run the lenses. Do not re-rank.
2. Read that round's records.
3. Continue from the first `pending` ID, in the order the pending rows were
   written. Skip IDs that already have a decision row.
4. Do not write new `pending` rows. Append decision rows to the same table.
5. If the artifact changed since the round started, say so in the first
   line of output, then resume anyway. The next round's re-check catches the
   effect of the change.

In report mode, do not ask. List each `pending` concern under OPEN
DECISIONS and leave its rows as they are.

## End-of-round re-check

In round 2 and later, after the new concerns have a resolution and before
the verdict. Check every ID whose latest row is `deferred`, `risk-accepted`,
`pending` or `open` against the current artifact and code. Skip an ID whose
latest Note already says "no longer applies".

| Result | Severity | Resolution | Note |
|--------|----------|------------|------|
| Still applies | unchanged | unchanged | `re-check: still applies` |
| No longer applies | unchanged | unchanged | `re-check: no longer applies - <reason>` |
| Got worse | raised | `pending` (interactive) or `open` (report) | `re-check: worse - <reason>` |

A concern that got worse needs a fresh decision. In interactive mode, walk it
before the verdict and append the decision row. In report mode, list it under
OPEN DECISIONS. It is carried over, not new, so it does not count as new for
exit rule 1, but it blocks if it is now High or Critical. A `risk-accepted`
concern is raised again only through this path.

## Worked example

Round 1 finds four concerns. The user decides C1 and H1, then stops. The
ledger now holds two decided rows and two `pending` rows:

```markdown
# Adversarial review ledger: nightly billing job

Artifact: /home/dev/plans/billing-job.md
Working directory: /home/dev/billing
Criticality: money or security path

## Round 1 (2026-10-12)

### Records

### C1: Manual run overlaps nightly run
- Severity: Critical | Failure event: admin starts a run at 02:01 during
  the 02:00 run -> both charge the same unpaid set -> every unpaid customer
  is charged twice
- Lens: L2 Reverse the goal
...
(H1, M1 and M2 records follow in the same shape)

### Rows

| Round | ID | Severity | Title | Resolution | Resolved by | Note |
|-------|----|----------|-------|------------|-------------|------|
| 1 | C1 | Critical | Manual run overlaps nightly run | pending | - | |
| 1 | H1 | High | Crash between charge and mark-paid | pending | - | |
| 1 | M1 | Medium | No metric for charges per run | pending | - | |
| 1 | M2 | Medium | Log line includes card suffix | pending | - | |
| 1 | C1 | Critical | Manual run overlaps nightly run | accepted | plan step 2a | |
| 1 | H1 | High | Crash between charge and mark-paid | modified | plan step 4 | Key on invoice ID and run date |
```

A new review of the same artifact finds M1 `pending`. It skips the lenses,
reads the records and resumes at M1, the third concern. The user
risk-accepts M1 and defers M2. The round closes:

```markdown
| 1 | M1 | Medium | No metric for charges per run | risk-accepted | - | Finance reconciles daily |
| 1 | M2 | Medium | Log line includes card suffix | deferred | - | |

Verdict: AMEND
```

Round 2 reviews the fix. It finds one new High. At the end of the round,
the re-check finds M1 unchanged, but the change now logs the whole provider
response, so M2 got worse:

```markdown
## Round 2 (2026-10-13)

Round 2 | carried open: none | new last round: 1 Critical, 1 High

### Records

### H2: Idempotency key reused across retries of a new invoice
...

### Rows

| Round | ID | Severity | Title | Resolution | Resolved by | Note |
|-------|----|----------|-------|------------|-------------|------|
| 2 | H2 | High | Idempotency key reused across retries of a new invoice | pending | - | |
| 2 | H2 | High | Idempotency key reused across retries of a new invoice | accepted | e4f5a6b | |
| 2 | M1 | Medium | No metric for charges per run | risk-accepted | - | re-check: still applies |
| 2 | M2 | High | Log line includes card suffix | pending | - | re-check: worse - step 5 now logs the full provider response, including card data |
| 2 | M2 | High | Log line includes card suffix | accepted | 7c8d9e0 | |

Verdict: AMEND
```

The verdict output for round 2 ends with:

```
Known risks
- M1: No metric for charges per run (risk-accepted in round 1)
```

## Resolution values

| Value | Meaning |
|-------|---------|
| pending | Interactive only. Written when the walkthrough starts. The user has not answered yet. |
| open | Report mode only. Found, not yet decided by a human. A later row records the decision. |
| accepted | The user agreed. The fix is in the resolving artifact. |
| modified | The user changed the action or scope, then agreed. |
| rejected | The user judged that the concern does not apply. Do not raise it again unless the change touches the same area. |
| risk-accepted | The concern is real. The user chooses to live with it, and nobody will fix it now. Not blocking. Raised again only if a re-check finds the risk got larger. Listed under "Known risks" in every verdict. |
| deferred | Kept as a watch-item, to fix later. Not blocking. |

## Round header

Every round after the first starts with one line:

```
Round <N> | carried open: <Critical and High IDs still open> | new last round: <n> Critical, <n> High
```

Use this line to apply the exit rules in SKILL.md section 11.
