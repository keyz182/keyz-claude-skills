# Lens questions: L1 to L3

Use these to start thinking, not as a form to fill in. Skip a question that
does not apply. Every answer that points at a problem becomes a candidate
concern and goes through the filter in SKILL.md section 3.

## L1: Failure in hindsight

Picture the incident review six months after this shipped. Something went
badly wrong and this change is the root cause. Write the first line of that
review, then work back.

- Which alert fired first, and who saw it? If no alert would fire, how was
  the problem found, and how late?
- What did the on-call engineer try first, and why did it not help?
- Which customer or team noticed before the authors did?
- What changed in the world between ship day and incident day? Traffic,
  data volume, a dependency version, a new tenant, a calendar date, a
  certificate expiry.
- Which part of the change did nobody look at closely because it seemed
  trivial?
- What did the rollback do? Did it restore the old state, or leave data in a
  shape the old code cannot read?
- Which manual step in the runbook was skipped or done in the wrong order?
- What did the tests prove, and what did everyone assume they proved?

## L2: Reverse the goal

State the goal in one line. Then ask: if the aim were to make this fail for
certain, what would we arrange? List those conditions. Then check the
proposal for each one.

- Make it fail: deploy it to an environment that differs from where it was
  tested. Is that the plan?
- Make it fail: let two copies run at once. Can that happen?
- Make it fail: feed it the largest, emptiest, oldest or most malformed
  input that exists in production. Has anyone looked at those records?
- Make it fail: remove the one person who understands it. Is the knowledge
  written down anywhere?
- Make it fail: give it partial success. Half the writes land, the other half
  do not. What state is left?
- Make it fail: make the downstream service slow, not down. Does anything
  time out, queue up or retry in a storm?
- Make it fail: ship it on a Friday with no feature flag. Is there a flag?
- Make it fail: let the success metric look green while users suffer. What
  is actually measured?

## L3: Hidden assumptions

Read the proposal line by line. Each time it relies on something it does not
state or check, write that down as "Assumes that ...". Then ask "and if not?"

Common places to find them:

- **Data:** the field is always present; IDs are unique; the table is small;
  timestamps share one time zone; text is ASCII; no row is older than the
  last schema change.
- **Order and timing:** events arrive in order; a job finishes before the
  next one starts; the cache is warm; clocks agree across hosts.
- **Callers:** only our own code calls this; callers send valid input;
  callers retry safely; there is one caller per tenant.
- **Environment:** the secret, flag, bucket, queue or DNS name exists in
  every environment; the service account has the same rights in production
  as in staging; the region has the feature.
- **People and process:** someone will run the migration by hand; the
  reviewer will notice; the docs will be updated later.
- **Dependencies:** the library behaves as its README says; the API version
  will not change; the free tier limit will not be hit.
- **Scope:** "this is only temporary"; "nobody uses that path"; "we can
  clean it up next sprint".

For each assumption, decide:

1. Is it checked anywhere (code, test, config, documented contract)? If yes,
   drop it.
2. If it is false, what breaks, and how would anyone find out?
3. What is the cheapest way to make it explicit: a check, a test, an
   assertion, or a line in the plan?
