# Worked example: no reachable trigger means at most High

The rule: a concern is Critical only if the reviewer names one concrete
failure event (trigger, how it fails, how far the damage spreads) and the
trigger is reachable in the proposal as written. If no reachable trigger can
be named, the concern is at most High.

## The proposal

A plan adds a nightly job that reads unpaid invoices and charges each
customer's saved card. Step 4 says: "For each invoice, call the payment
provider's charge endpoint, then mark the invoice paid."

## First draft of the concern

> **C1: Double charge if the job runs twice.** Two copies of the job could
> charge the same invoice twice. Money path, so Critical.

## Check the trigger

Ask: how would two copies run at once, in the proposal as written?

- The plan schedules the job with the platform's cron feature, and section 2
  of the plan sets `concurrencyPolicy: Forbid`. A second run cannot start
  while the first is still going.
- There is no manual "run now" button or API in the plan.
- The job takes about four minutes on current volume, and the schedule is
  every 24 hours.

No path in the proposal starts a second copy. The double-run trigger is not
reachable as written. The concern cannot be Critical.

## Is it still a real concern?

Yes, for a different reason. Step 4 charges first and marks paid second. If
the job crashes or is killed between those two calls, the invoice stays
unpaid. Next night, the job charges it again. A node drain or an
out-of-memory kill is a realistic cause.

That is a named, realistic scenario that causes harm, so the concern is
High. The counter-argument ("concurrency is already forbidden") is true, and
it is why the original framing fails. It does not cover a crash between the
two calls.

## Final record

```
### H1: Crash between charge and mark-paid causes a second charge next night
- Severity: High | Scenario: job is killed after the charge call returns and
  before the invoice is marked paid -> next nightly run charges the same
  invoice again
- Lens: L1 Failure in hindsight
- Counter-argument: Forbid policy stops two runs at once. Fails because the
  repeat comes from the next scheduled run, not a parallel one.
- Evidence: plan step 4 ("call the charge endpoint, then mark the invoice paid")
- If ignored: customers are charged twice after any mid-run crash; refunds
  and support load follow
- Action: send an idempotency key derived from the invoice ID with each
  charge, and check the provider's record before charging
- Status: blocking
```

## What would make it Critical

If the plan also added an admin endpoint that starts the job on demand, with
no lock, an operator clicking it during the nightly run is a reachable
trigger. Then the reviewer could write the event in full: "Admin triggers a
manual run at 02:01 while the 02:00 run is in progress; both read the same
unpaid set; every invoice in it is charged twice; every customer with an
unpaid invoice that night is affected." That meets the Critical bar.
