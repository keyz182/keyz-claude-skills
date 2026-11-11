# Lens questions: L6 to L12

Same rules as `lens-questions.md`. These questions start the thinking. They
are not a form. Skip a question that does not apply. Every answer that points
at a problem becomes a candidate concern and goes through the filter in
SKILL.md section 3.

L9 and L10 run on every review. The others run when the artifact kind calls
for them (see the table in SKILL.md section 2). Run L12 last, because it
starts from the worst failure the other lenses found.

## L6: Pin down the claim

Find every promise the proposal makes. Rewrite each one so a test, a metric
or a reviewer could say yes or no to it.

- Which words carry the promise without a number? Look for "fast",
  "secure", "scalable", "simple", "robust", "real-time", "minimal",
  "seamless", "easy to extend".
- "Fast": at what percentile, under what load, measured where? What is the
  number today?
- "Secure": against whom, protecting what, checked by which control?
- "Scalable": to what volume, along which axis (users, tenants, rows,
  requests), and what breaks first?
- "Simple": simple for whom? Fewer lines, fewer moving parts, or fewer
  concepts for the next reader?
- What does "done" look like? Which check passes on the day it ships that
  fails today?
- If two people read the claim, would they test the same thing?
- Which claim, if it turned out to be half true, would sink the proposal?

## L7: Ask for the evidence

For each key claim, find out how the author knows it. Sort the answers into
three groups: measured, read (in code, docs or a contract), or assumed.

- Was this number measured, on which data, and when? Is the sample like
  production?
- Was this behaviour read in the code? Which file and line? Is that the code
  path the request actually takes?
- Was this read in vendor docs? For which version? Does the deployed version
  match?
- Is this claim from memory, a naming convention, or "it usually works like
  that"? Then it is assumed.
- Did a test prove it, or does a test only exist near it? What does the test
  assert?
- Which claims rest on another claim? If the base claim is assumed, so is
  everything on top.
- What is the cheapest check that would turn the riskiest assumed claim into
  a measured or read one?

## L8: Other seats at the table

Read the proposal again from five seats. Each seat asks what it needs and
what it fears.

- **On-call engineer at 3am:** how do I know it is broken? What do I turn
  off? Is there a runbook? Can I roll back without the author?
- **Security reviewer:** what new input, endpoint, permission or secret does
  this add? What is logged? Who can reach it who could not before?
- **New team member in six months:** can I find out why it was built this
  way? Is the odd part explained? Can I change it without breaking a hidden
  rule?
- **Heavy user:** what happens with my volume, my oldest data, my odd
  settings? Does it get slower for me first?
- **Attacker:** where is the cheapest way in? Can I replay, enumerate,
  flood or escalate? Which error message tells me too much?
- Which seat did the author clearly not sit in? Start there.

## L9: Follow it forward

Take the change two or three steps into the future. Ask what it makes
easier, what it makes harder, and what it commits the team to.

- If this ships, what is the obvious next request? Does the design carry it,
  or block it?
- What will be hard to undo once real data or real callers depend on it? A
  schema, a public API, an event name, a URL, a file format.
- What new thing must now be kept running: a job, a queue, a cache, a
  dependency, a vendor contract? Who owns it?
- Does this set a pattern others will copy? Is it a pattern worth copying?
- What does this make harder to change later: the data model, the deploy
  order, a library upgrade, a move to another region or provider?
- What happens at the second and third use? Does each one need a copy of
  this work, or does it reuse it cleanly?
- What cost grows over time: storage, licence seats, on-call load, test
  runtime?

## L10: Question the framing

Step back from the solution. Check that it answers the right question.

- What is the real need behind the request? State it without naming the
  solution.
- Is the problem real today, or expected later? What evidence shows it?
- Would a smaller change meet the need: a config value, a doc fix, a manual
  step, deleting code?
- Would a different change meet it better: fixing the cause upstream, using
  something the codebase already has, buying instead of building?
- What happens if nobody does anything? Is that acceptable for a while?
- Who asked for this, and would they agree with how it was framed?
- Is the proposal solving the problem, or making the symptom quieter?

## L11: Separate the thinking modes

Do four short passes, one at a time. Do not mix them. Mixing lets a
favoured option hide its weak facts, or lets a worry pass as a fact.

1. **Facts only.** What do we know for sure? What do we not know? Write no
   opinions in this pass.
2. **Risks only.** What could go wrong? Write no fixes and no defences in
   this pass.
3. **Alternatives only.** What else could meet the need? Write at least two
   options, including "do less". Do not judge them yet.
4. **Quality of this review.** Look at the concerns found so far.
   - Does each one name a file, line or step? A concern that could apply to
     any project is noise.
   - Did one lens find almost everything? Then the others were run too
     lightly.
   - Is any concern a matter of taste dressed up as risk?
   - Did the review check the code the request actually runs, or a nearby
     copy?

## L12: Chain of causes, run forwards

Take the worst failure found so far. Ask "and that would happen because
...?" four or five times, until the answer is a design choice, not an
event.

Example chain:

1. Customers were charged twice. Because ...
2. The job charged an invoice that was already paid. Because ...
3. The invoice still showed as unpaid after the charge. Because ...
4. The job was killed between the charge and the status update. Because ...
5. The design treats "charge" and "mark paid" as two separate steps with no
   shared key. **Root design choice.**

Questions for each link:

- Is this link certain, or one of several possible causes? If several,
  follow the most likely one and note the others.
- Does the proposal break the chain at this link already? If so, stop and
  check the next worst failure.
- At the root: does the action in the concern fix the root, or only the top
  link? Prefer the action that fixes the root, and say so in the concern.
