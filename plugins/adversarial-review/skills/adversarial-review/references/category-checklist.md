# L4: Category sweep

Areas that reviews often miss. Walk every heading. For each, either note a
candidate concern or note "not relevant" in your head and move on. Depth
depends on the criticality set in SKILL.md section 0: a prototype gets a
quick pass, a money or security path gets every line.

## Security and authorisation

- Who can call this, and where is that checked? Is the check on the server,
  or only in the UI?
- Can one tenant, user or org reach another's data by changing an ID?
- Are secrets read from a secret store, or hard-coded, logged, or put in a
  URL?
- Does any input reach a shell, a query, a template or a file path without
  escaping?
- Does the change widen a permission, a network rule or a token scope? Is the
  wider scope needed?

## Data lifecycle and migration

- Does it change a schema, a file format or a message shape? Can old and new
  code both read the data during the rollout?
- Is the migration reversible? What happens to rows written after it ran if
  it is rolled back?
- How long does the migration take on production volume? Does it lock a
  table?
- Who owns the data? Does this code read or write data another component
  owns?
- When is the data deleted, archived or expired? Is there a retention or
  privacy rule?

## Failure and retry behaviour

- What happens when a call fails half way? Is the operation idempotent?
- Are retries bounded, with backoff? Can they cause a retry storm?
- Is a failure surfaced, or swallowed and logged at debug level?
- What does the user see on failure?
- Are timeouts set on every outbound call?

## Concurrency

- Can two instances, workers or requests run this at the same time?
- Is there a read-then-write gap another writer can slip into?
- Are locks released on every path, including errors?
- Does ordering matter, and is it guaranteed?

## Scale

- What is the expected volume now and in a year? What happens at ten times?
- Is there an unbounded loop, list, query or payload?
- Does memory or connection use grow with input size?
- Are there per-tenant or per-account limits on a third-party service?

## Observability

- If this breaks at 3am, which metric, log or alert shows it?
- Can one request be traced end to end?
- Do logs leak secrets or personal data?
- Is there a way to tell "working but slow" from "broken"?

## Deployment and rollback

- What is the deploy order across services, and does it matter?
- Is there a feature flag or another way to turn it off without a deploy?
- Has rollback been tried? Does it need a data step as well as a code step?
- Does the change need a manual step, and is that step written down?

## Environment differences

- Which config, secret, flag or resource must exist in each environment?
- Do staging and production differ in data size, network rules, versions or
  permissions in a way that matters here?
- Does anything depend on a local setting, a developer machine or a cached
  credential?

## Integration contracts

- Which other systems call this or are called by it? Does the change alter
  any field, status code, event name or timing they rely on?
- Is the contract versioned? Do consumers pin a version?
- Are breaking changes announced, and is there a deprecation window?

## Multi-tenancy

Walk this section when more than one customer, org or account shares the
system. The question about reaching another tenant's data by ID sits under
security, above.

- **Scoping:** is every query, cache key, queue, topic and object-store path
  scoped by tenant? Check each one, not just the main query. A cache key
  without the tenant ID leaks data as surely as a query without a filter.
- **Noisy neighbours:** can one tenant's load slow or starve the others?
  Look for shared pools, queues and rate limits. Is there a per-tenant quota,
  a per-tenant rate limit, or fair scheduling between tenants?
- **Per-tenant migrations and backfills:** what happens if the job fails
  half way, on tenant 40 of 300? Can it resume, and does order matter? How
  long does the largest tenant take, not the average one?
- **Deletion and export:** when a tenant leaves or asks for its data, does
  every store follow? Include caches, search indexes, logs, analytics,
  queues and backups.
- **Per-tenant config and flags:** what happens when a tenant has no entry?
  Is the default safe, or does it fall through to another tenant's value or
  to "everything on"?
- **Tests and fixtures:** do the tests run with at least two tenants, so a
  leak or a wrong filter shows up? A suite with one tenant cannot catch a
  cross-tenant bug.

## Edge cases in inputs

- Empty, null, missing, zero, negative, very large.
- Unicode, mixed case, leading or trailing spaces, very long strings.
- Duplicates, out-of-order items, items that refer to deleted records.
- Dates at month end, leap days, daylight saving changes, time zones.
- Precision and rounding in money or measurements.
