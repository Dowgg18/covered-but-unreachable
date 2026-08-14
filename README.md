# reachable

[![ci](https://github.com/Dowgg18/covered-but-unreachable/actions/workflows/ci.yml/badge.svg)](https://github.com/Dowgg18/covered-but-unreachable/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-2d6a4f)](LICENSE)
[![dependencies](https://img.shields.io/badge/runtime%20dependencies-none-CDC733)](pyproject.toml)

**Coverage says the line ran. It does not say production can get there.**

A unit test that calls a function directly executes its branches, and the report
comes back green. Meanwhile the only door real traffic comes through returns
three frames higher up, and that branch has not run for a paying customer in
months. Coverage cannot see the difference, because from its side both look like
the line executing.

```
LIVE           reached from an entrypoint under every production config
PARTIAL        reached under some production configs, not all
PREVIEW-ONLY   reached only under configs nobody is served by
ORPHANED       executed — but never from an entrypoint
SILENT         never executed at all
```

`ORPHANED` is the one worth installing this for. The code demonstrably runs, so
your corpus reaches it; it simply cannot be reached through a door production
uses. That is not a coverage gap. It is a feature that exists in the file, passes
review, and serves nobody.

```python
from reachable import Registry, entered, probe, watch

registry = Registry({"ack.unassigned": "flows.py:2264"})

with watch(registry) as session:
    for tenant in FLEET:
        with session.config(tenant.name, production=tenant.is_live):
            for payload in corpus:
                with entered("webhook"):        # the door production uses
                    handle_inbound(payload, tenant.config)

session.report().assert_live(silent_is="fail")
```

Two calls reach into your app: `probe(name)` on the branch you believe in, and
`entered(name)` around the boundary traffic actually arrives at. `probe` is a
`ContextVar` lookup and an identity check when nothing is watching, so it stays
in shipped code — a probe you strip for performance is a probe that stops telling
you the truth.

---

## Where this came from

A messaging product stopped replying to people, and the report that surfaced it
said **91% of inbound messages in the last seven days received no response at
all** — not from the bot, not from a human. Ninety-five different customers, each
one's conversation ending with their own message.

The acknowledgement they should have received had been written months earlier. It
was in the file. It had a test. It had never once run.

### 1. The guard that made a feature unreachable

```python
# webhook handler
if lead.status in ("assigned", "closed"):
    return                      # an agent owns this; the bot must not talk over them
...
await run_flow(lead, text)
```

```python
# run_flow, ~600 lines away
if lead.status == "assigned":
    if lead.assignee is None:
        return "Thanks — the team has been notified."     # <- never reached
```

Both halves are correct. The guard is genuinely the right instinct, the
acknowledgement is genuinely the right behaviour, and the second one has been
dead since the first was written. Nobody was careless: the branch was reviewed,
it was tested, and the test passed — because the test called `run_flow` directly.

**What finds it:** the acknowledgement is `ORPHANED`. It executed once in the
suite and zero times from the webhook. Coverage reported it covered, and coverage
was right.

### 2. The rewrite that shipped to nobody

There were two implementations of the flow, chosen per tenant by a feature flag:

```python
if config["flow_v2"]:
    return await flow_v2(...)
return await flow_v1(...)
```

Every tenant in the fleet had the flag off. Not "most" — every one. So half the
conversation logic in that codebase served zero users, while remaining fully
covered, fully reviewed, and the first thing anyone opened when they went looking
for the bug.

**What finds it:** `PREVIEW-ONLY`. Those branches are reached from the entrypoint,
but only under a configuration marked `production=False`. Which is why
`session.config(name, production=...)` has no default — whether real users are
served under a configuration is a fact about your fleet, not something the
library can infer, and it is the whole difference between "behind a flag" and
"dead".

And it is where the first attempt at a fix went. `flow_v2` is the modern one, so
the acknowledgement was repaired there: a clean diff, a green suite, a commit
that reads well.

It changed nothing for anybody. The demo reproduces this exactly, and it is the
one finding in the output that is not `PREVIEW-ONLY`:

```
SILENT       helpdesk.py:53  ack.unassigned.v2
    never executed under any configuration in this run
```

Not preview-only — *silent*. The same early return orphans the acknowledgement in
**both** implementations, so the branch in the rewrite is not merely waiting for
a flag. It is unreachable in a flow nobody runs. Fixing the wrong copy of a
duplicated code path is the failure mode that makes this a class of bug rather
than a bug, and a verdict per configuration is what makes it visible before the
deploy rather than a week after.

### 3. The guard was load-bearing for three other things

Deleting the early return made the acknowledgement reachable. It also made
reachable: a sentiment-analysis call that now billed an LLM for every message
from 1,361 stalled conversations, a background fact-extraction job with the same
problem, and an escalation branch that told customers already waiting in the
queue *"I'll get someone for you right now"* a second time.

None of that was written down anywhere. The early return was the specification.

**What finds it:** nothing here — this one is a warning, not a feature. A gate
that tells you a path is dead does not tell you what starts running when you
revive it. What it does buy you is knowing the list of paths that change verdict,
which is a much better place to start reading than the diff.

---

## The verdict with no knob

`assert_live` will not let you allowlist an orphan.

```python
report.assert_live(
    silent_is="fail",
    allow_preview={"checkout.v3"},   # named, so the exemption rots visibly
    allow_partial={"enterprise.sso"},
)
```

`PREVIEW-ONLY` and `PARTIAL` are allowlisted **by probe name** rather than by a
global switch, because "we know about that one" should require saying which one,
and should look wrong in review once the flag finally ships.

`ORPHANED` has no allowlist and will not get one. Every other verdict has an
innocent explanation available — a thin corpus, a flag not yet flipped, a feature
only enterprise tenants buy. An orphan has none: the line ran, so the corpus
reaches it, and it still never went through the door. A flag to silence that is a
flag to silence the library.

## The parameter with no default

```python
report.assert_live()
TypeError: assert_live() missing 1 required keyword-only argument: 'silent_is'
```

`SILENT` means a declared path never executed, and that is genuinely ambiguous.
It can mean the code is dead. It can equally mean your corpus never steered that
way. Only you know which your suite is good enough to distinguish, so the library
refuses to guess, in the one place where guessing would produce a confident
number that is wrong.

`Report` has no `__bool__` for the same reason — five verdicts carrying different
kinds of evidence must not collapse into "is my code fine".

## The demo

A helpdesk with the same shape: an early return in the webhook, two flow
implementations, one flag that is off everywhere real.

```bash
pip install -e ".[dev]"
python -m demo.run_gate     # exits 1, on purpose
pytest                      # the library's own tests
```

```
$ python -m demo.run_gate
reachable: 8 declared path(s) across 3 production and 1 non-production config(s)
ORPHANED     helpdesk.py:37  ack.unassigned.v1
    executed 1x, never from an entrypoint
    something in the suite calls it directly; nothing production runs does
ORPHANED     helpdesk.py:39  ack.assigned.v1
    executed 1x, never from an entrypoint
    something in the suite calls it directly; nothing production runs does
PREVIEW-ONLY helpdesk.py:57  greet.v2
    reached only under non-production config: staging
    dead for everyone actually being served: acme, globex, initech
PREVIEW-ONLY helpdesk.py:60  fallback.v2
    reached only under non-production config: staging
    dead for everyone actually being served: acme, globex, initech
SILENT       helpdesk.py:53  ack.unassigned.v2
    never executed under any configuration in this run
LIVE         helpdesk.py:18  drop.closed
    live in acme, globex, initech via webhook
LIVE         helpdesk.py:43  greet.v1
    live in acme, globex, initech via webhook
LIVE         helpdesk.py:46  fallback.v1
    live in acme, globex, initech via webhook
$ echo $?
1
```

CI asserts that the demo **fails**, and fails with those specific findings. A
demo that quietly starts passing has stopped demonstrating anything.

## What this is not

- **Not a coverage tool.** It does not measure lines, and it will not tell you
  what to test next. It answers one question coverage cannot: can production get
  here.
- **Not static analysis.** There is no call-graph, no solver, no soundness claim.
  It reports what it witnessed.
- **Not a feature-flag manager.** It reads your fleet as data you pass in; it does
  not own flags, roll them out, or clean them up.
- **Not automatic.** Probes are hand-placed. That is the trade — see below.

## Limits, honestly

- **`SILENT` is weak evidence and the library says so, but people will still
  read it as "dead".** It is the verdict most likely to produce a confident wrong
  conclusion, which is why `silent_is` is mandatory rather than defaulted.
- **Probes are hand-placed, so coverage of the tool is your judgement.** A dead
  branch nobody probed is a dead branch nobody hears about. The upside is that the
  registry doubles as a written list of paths the team claims matter; the downside
  is that it is a list someone has to maintain. A `sys.monitoring` backend could
  remove the hand-placement and would trade this limit for a worse one — probing
  everything means grading everything, and a report with four thousand findings is
  a report nobody opens.
- **`contextvars` do not cross a thread boundary.** Work handed to a thread pool
  sees no recorder at all, so its probes come back `SILENT` rather than
  `ORPHANED` — the more dangerous of the two mistakes. `asyncio` is fine.
  There is a test asserting this so it cannot drift silently.
- **Reachability is relative to the corpus you ran.** The tool proves reachability
  by witnessing it; it can only ever prove *un*reachability with respect to what
  you fed it. `ORPHANED` survives this caveat — the line ran, so the corpus was
  not the problem — and `SILENT` does not.
- **A registry is a claim, and claims go stale.** Nothing here notices a probe you
  deleted from the code but left in the registry; it reports as `SILENT` forever.
  Strict mode catches the opposite direction only.

MIT licensed.
