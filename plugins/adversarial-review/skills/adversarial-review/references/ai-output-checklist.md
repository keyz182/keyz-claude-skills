# L5: AI-output sweep

Run this lens when an AI model produced the plan, design or code, including
output from another skill or agent in this conversation. Each item lists
what the fault looks like and a quick way to test for it.

## Happy-path-only reasoning

- Looks like: the plan describes what happens when every call succeeds.
  Error branches are missing, or say "handle errors appropriately".
- Test: pick the two most likely failures (a timeout, a bad record) and trace
  them through the plan. If the plan is silent, raise it.

## Scope accepted without question

- Looks like: the proposal does exactly what was asked, even where the ask
  conflicts with the codebase, the data or an earlier decision.
- Test: restate the original request. Is there a simpler change that meets
  the real need? Does the request clash with anything the AI had access to?

## Confident claims that were not checked

- Looks like: "this API returns X", "this flag exists", "the table has an
  index on Y", "tests pass", with no command output, file read or link.
- Test: list every factual claim the plan depends on. For each one, find the
  evidence in the conversation. A claim with no evidence is a hidden
  assumption (L3) at best, and a likely error at worst.

## Familiar pattern that does not fit

- Looks like: a textbook structure (a new service, a queue, a cache, a
  generic base class) dropped in where the codebase does something simpler
  or different.
- Test: find how the codebase already solves the nearest similar problem.
  If the proposal ignores that without saying why, raise it.

## Symptom patched, cause left

- Looks like: a null check, a retry, a sleep, a broader exception catch or a
  special case that makes the error go away.
- Test: ask why the bad state happened in the first place. If the proposal
  cannot answer, the cause is still there.

## Tests changed to pass

- Looks like: assertions loosened, expected values updated to match new
  output, tests skipped or deleted, mocks widened, in the same change as the
  fix.
- Test: for each changed test, ask whether the old expectation was wrong or
  the new code is. If the answer is not clear from the diff, raise it.

## Drift over a long session

- Looks like: the output breaks a constraint, reverses a decision or
  misquotes a file that was settled earlier in the same session. Common
  after many turns, a context reset or a summary.
- Test: list the constraints and decisions stated earlier in the session.
  Check the output against each one. Re-read any file the output quotes or
  edits and compare it with what the output says is there.

## Clash with the existing codebase

- Looks like: new code uses a different library, layer, naming scheme or
  error style from the code that already does the same job in this repo.
- Test: find two or three places in the repo that solve the same kind of
  problem. Compare the new code with them. If it differs and the proposal
  does not say why, raise it.

## Solving the stated request, not the need

- Looks like: the user asked for a means (X), and the output builds X with
  care. Nobody checked that X serves the real goal (Y).
- Test: write Y in one line, without naming X. Then ask whether X is the
  best route to Y, or only the route the user named. If X misses part of Y,
  or a simpler route reaches Y, raise it. Pair this with lens L10.

## Too much structure too early

- Looks like: an interface with one implementation, a factory that builds
  one type, a config layer for values that never change, a generic helper
  with one caller.
- Test: count the callers and the planned second uses. If there is one
  caller and no second use in sight, raise it. Ask what the direct version
  would look like and what it would cost to add the structure later.

## Security bolted on late or not at all

- Looks like: input is trusted, authorisation is missing or only in the UI,
  secrets sit in code or config, sensitive data reaches logs. Or security
  appears as a final step ("add auth later", "harden before release").
- Test: for each new entry point, find where input is checked, where the
  caller's rights are checked, where secrets come from, and what is logged.
  A missing answer is a concern. Use the security section of
  `category-checklist.md` for depth.

## Thoroughness for show

- Looks like: a long list of generic risks ("consider scalability", "ensure
  proper error handling") with no file, line or plan step against any of
  them.
- Test: for each item, ask "where, exactly?". An item with no place is
  noise. Real thoroughness names specific places.
- Apply this test to this review's own output too, before reporting. Drop
  or sharpen any concern that fails it.

## Other signs worth a look

- Code or config that references a function, flag, field or file that does
  not exist in the repository.
- A plan that grew new files or interfaces not in the agreed scope.
- Comments or docs that describe behaviour the code does not have.
