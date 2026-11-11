---
name: adversarial-review
description: This skill should be used when the user asks to "challenge this plan", "red-team this", "what could go wrong", "pre-mortem this", "adversarial review", "poke holes", "stress-test this design", "find the flaws", or "review this before I build it". It looks for the reasons a plan, design, diff, decision or another skill's output will fail, ranks the concerns against a fixed severity bar, and ends with one verdict (PROCEED, AMEND or RETHINK). Runs interactively by default, or in report mode with no questions when called by a worker agent or when the caller asks for "report mode".
version: 0.2.0
---

# Adversarial review

Find the reasons a proposal will fail before anyone acts on it. Produce ranked,
actionable concerns and one verdict. Never implement anything. Never loop past
the round limit.

## 0. Set up

1. **Pick the mode.** `report` when the caller says so (for example
   "adversarial-review in report mode"), or when running inside a subagent,
   worker or headless run with no human to answer. Signs: the task arrived
   as a delegated prompt, there is no question tool, or the caller asked for
   a file or a word-limited summary. `interactive` in every other case.
2. **Find the artifact.** It is one of: a file path, a diff range, a pasted
   plan, or "the thing just produced in this conversation". If more than one
   candidate fits, name the one chosen in the first line of output.
   If none was given and nothing recent is an obvious candidate: in
   interactive mode, ask which artifact is meant, offering the most recent
   output in this conversation, a file or diff the user names, or an
   approach the user describes. In report mode, stop and say that no
   artifact was given.
3. **Set the criticality:** prototype, internal tool, production, or money
   or security path. Interactive: if it is unclear and would change how hard
   to push, ask once. Report: assume production and say so. Criticality sets
   the depth of the category sweep. It never moves the severity bar.
4. **Check for a ledger.** Work out the ledger path (see section 11). If a
   ledger exists for this artifact, read `references/ledger-format.md`.
   - If the latest row for any ID in the newest round is `pending`, a
     walkthrough was cut short. Resume it: skip sections 1 to 5, read the
     stored records and continue section 8 from the first `pending` concern.
     Do not re-run the lenses or re-rank. Report mode lists them under OPEN
     DECISIONS instead.
   - Otherwise this is a later round. Follow section 11.

## 1. Make the best case first

Before any concern, write two or three sentences on why the proposal is
reasonable: the problem it solves and the constraints it respects. If this
cannot be written, the proposal is not yet understood. Read more first.

## 2. Generate candidate concerns

Load a lens's reference file when you reach that lens. Run L12 last.

| # | Lens | Use | Reference |
|---|------|-----|-----------|
| L1 | Failure in hindsight: it shipped and caused an outage; trace back | Always | `references/lens-questions.md` |
| L2 | Reverse the goal: list what would guarantee failure; check which are present | Always | `references/lens-questions.md` |
| L3 | Hidden assumptions: name each; ask what happens if it is false | Always | `references/lens-questions.md` |
| L4 | Category sweep of commonly missed areas | Always | `references/category-checklist.md` |
| L5 | AI-output sweep for typical AI faults | Always, when an AI produced it | `references/ai-output-checklist.md` |
| L6 | Pin down the claim: make vague words checkable | By kind | `references/lens-questions-extended.md` |
| L7 | Ask for the evidence: measured, read, or assumed? | By kind | `references/lens-questions-extended.md` |
| L8 | Other seats: on-call, security, newcomer, heavy user, attacker | By kind | `references/lens-questions-extended.md` |
| L9 | Follow it forward two or three steps | Always | `references/lens-questions-extended.md` |
| L10 | Question the framing: right problem, smaller change? | Always | `references/lens-questions-extended.md` |
| L11 | Separate passes: facts, risks, alternatives, review quality | By kind | `references/lens-questions-extended.md` |
| L12 | Chain of causes from the worst failure to its root design choice | By kind | `references/lens-questions-extended.md` |

"By kind" lenses, by artifact kind:

| Artifact kind | Add these lenses |
|---------------|------------------|
| Small diff or bug fix | None |
| Feature diff or multi-step plan | L6, L7, L12 |
| Design, RFC, or decision between options | L6, L7, L8, L11, L12 |
| Output of another skill or agent | Use the row for what it produced |

Read the real code, config or plan lines a concern depends on. A concern
built on a guess about the code is not evidence.

## 3. Filter

Apply all four tests to each candidate. Drop a candidate that fails any.

1. **Consequence:** if nobody acts on it, what actually happens? "Nothing
   much" means drop it.
2. **Counter-argument:** write the strongest reason it is not a real issue
   (the code already covers it, it lies outside this change, or it does no
   damage). If that reason holds, drop it. If the concern survives, keep the
   counter-argument and state why it fails.
3. **Actionable:** there must be a concrete action. No action means drop it.
4. **Not a duplicate:** drop anything already reported by another review
   step in this conversation, by the caller's brief, or in the ledger.

## 4. Rate severity

The bar is fixed. Mode, criticality, round and time pressure do not move it.

- **Critical:** state one concrete failure event: the trigger, how it fails,
  and how far the damage spreads. The trigger must be reachable in the
  proposal as written. **If no reachable trigger can be named, the concern
  is at most High.** See `references/severity-downgrade-example.md`.
- **High:** a named, realistic scenario in which it causes harm.
- **Medium:** worth fixing. No failure event is needed.

Mark each concern **blocking** (must be fixed before the work goes ahead) or
**watch-item** (track it, do not hold the work for it).

## 5. Budget

- Report every Critical and every High in full.
- Report the top three Mediums in full. List any other Mediums on one line:
  the count, then a short label for each. Never drop a Medium silently.
- **If Critical plus High is more than five, stop the detailed review.** The
  verdict is RETHINK, with a recommendation to split the proposal into
  smaller parts. List the Critical and High titles only.

## 6. Concern record

Every reported concern has all of these fields:

```
### H1: <one-line title>
- Severity: High | Failure event: <trigger> -> <how it fails> -> <blast radius>
- Lens: L3 Hidden assumptions
- Counter-argument: <strongest case against the concern>. Fails because <reason>.
- Evidence: <file:line | plan step | quoted decision>
- If ignored: <what happens>
- Action: <the concrete change>
- Status: blocking | watch-item
```

IDs use the severity letter and a number: C1, H1, M1. An ID never changes,
in any round. Medium records may write `Failure event: n/a`.

## 7. Verdict

End every review with exactly one verdict:

- **PROCEED:** no blocking concerns. Notes may follow.
- **AMEND:** the approach is sound; fix the listed blocking concerns first.
- **RETHINK:** a fundamental flaw, or the budget in section 5 was exceeded.

Under the verdict, add a **Known risks** heading. List every concern whose
latest ledger row is `risk-accepted`, from any round, with its ID, title and
round. If there are none, write "Known risks: none". They never block.

## 8. Interactive mode

1. Show the best case (section 1).
2. Before the first question, write the concern records and one `pending`
   ledger row per concern to be walked (see the ledger reference).
3. Raise a single concern per turn, most severe first. The user chooses
   **accept**, **reject**, **modify**, **risk-accept** or **defer**.
   - If a structured question tool exists (`AskUserQuestion` in Claude Code,
     `question` in OpenCode),
     use it, one concern per question, with the whole record in the question
     text so it stays on screen. If the tool caps the options, offer accept,
     reject, risk-accept and defer, and take modify as free text.
   - Modify: take the user's change, then treat the concern as accepted in
     its new form. Reject: the concern does not apply. Risk-accept: the
     concern is real, the user lives with it, nobody fixes it now; not
     blocking. Defer: a watch-item, to fix later.
   - **Append the ledger row straight after each answer,** before the next
     question. Do not wait for the verdict.
4. When every concern has a resolution, run the re-check (section 11) in
   round 2 and later. Then give the verdict and Known risks (section 7).
5. If at least one concern was accepted or modified, write the revised plan
   (section 10), whatever the verdict.
6. Append the verdict line to the ledger. Stop and wait for an explicit
   go-ahead.

## 9. Report mode

No questions. No waiting. Output in this order:

1. The criticality assumption, if one was made.
2. The best case.
3. All concern records, ranked by severity, within the budget.
4. The verdict, with Known risks from the ledger.
5. **OPEN DECISIONS:** a numbered list. Phrase each item as a decision a
   human can answer, then the recommended option and its trade-off:
   `1. <question> (re C1) Recommend: <option>. Trade-off: <cost or risk>.`

If the caller gave a file path, write the full report there. Return only a
summary of 200 words or fewer: the verdict, counts by severity, and the
OPEN DECISIONS titles. Append the records and rows with resolution `open`
(see the ledger reference). Then stop. Report mode never revises the plan.

## 10. Revised plan

Interactive mode only, after every concern has a resolution. Write it
whenever at least one concern was accepted or modified, whatever the
verdict. Skip it only for PROCEED with nothing accepted or modified.

1. Restate the whole plan with the accepted changes built in. Do not just
   list the resolutions.
2. Add an integration table. Mark any accepted or modified concern with no
   matching line as **MISSING**, and say so above the table.

   | Concern | Resolution | Plan line that addresses it |
   |---------|-----------|-----------------------------|
   | C1 | accepted | Step 3: add idempotency key |
   | H2 | modified | **MISSING** |

3. Stop. Wait for an explicit go-ahead. This skill never implements.

## 11. Rounds and termination

- **Ledger path:** `${XDG_STATE_HOME:-~/.local/state}/adversarial-review/<slug>.md`. Read
  `references/ledger-format.md` for the slug and row format before the first
  write.
- The ledger is append-only. Never edit or delete an earlier row.
- A concern is resolved only if its resolving artifact (commit SHA or plan
  line) exists and later changes have not touched it.
- **Start each later round with a header line:**
  `Round N | carried open: C2, H1 | new last round: 1 Critical, 2 High`
- Round 2 and later review only what changed since the last round and what
  that change could affect. A new Critical or High there must be new
  behaviour, in changed material, that would actually fire.
- Do not raise a ledgered concern again unless the change touched the thing
  that resolved it, or a re-check finds it got worse.
- **End-of-round re-check (round 2 and later).** Before the verdict, check
  every concern whose latest row is `deferred`, `risk-accepted`, `pending` or
  `open` against the current artifact and code. Append one row each: still
  applies, no longer applies (with the reason), or got worse (raise the
  severity and say why). A concern that got worse needs a fresh decision:
  walk it (interactive) or list it under OPEN DECISIONS (report). Never
  change old rows.

### Exit rules (hard)

These rules override everything else in this skill.

1. **A later round that adds no new Critical or High ends the loop.** The
   verdict is PROCEED. Open Mediums become watch-items. Carried-over
   Critical or High that are still open are not new, but they still block:
   resolve them in this round (interactive) or list them under OPEN
   DECISIONS (report) before giving the verdict.
2. **If round 3 still finds a new Critical,** challenge how the work is split,
   not the code. Recommend a different breakdown.
3. **Never run more than four rounds.** After round 4, hand every remaining
   blocker to the user as a numbered decision list and stop.

## 12. Tone

- Direct and specific. Write "This fails when ...", not "this might
  potentially cause issues". Lead with the most important concern.
- Name the lens on every concern, so readers learn the method.
- If the proposal is good, say so plainly and give PROCEED.
- Do not invent concerns to look thorough. Every concern names a file, line
  or plan step; a generic risk with no place is dropped.
- Do not rewrite the code under review. Describe the change; leave the
  writing to whoever acts on it.
