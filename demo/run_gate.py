"""Run the gate over the demo helpdesk and print what it finds.

    python -m demo.run_gate

Exit code is 1 when a declared path cannot be reached the way production runs.
"""

from __future__ import annotations

import sys

from reachable import Registry, Unreachable, entered, watch

from . import helpdesk

# The branches this team says matter. Declaring them is the commitment: every
# name here is a claim that some real customer can reach this line.
REGISTRY = Registry(
    {
        "drop.closed": "helpdesk.py:18",
        "ack.unassigned.v1": "helpdesk.py:37",
        "ack.assigned.v1": "helpdesk.py:39",
        "greet.v1": "helpdesk.py:43",
        "fallback.v1": "helpdesk.py:46",
        "ack.unassigned.v2": "helpdesk.py:53",
        "greet.v2": "helpdesk.py:57",
        "fallback.v2": "helpdesk.py:60",
    }
)

# What the fleet actually looks like. The rewrite is on for nobody but the
# staging tenant, which is the fact that turns "behind a flag" into "dead".
FLEET = [
    ("acme", {"flow_v2": False}, True),
    ("globex", {"flow_v2": False}, True),
    ("initech", {"flow_v2": False}, True),
    ("staging", {"flow_v2": True}, False),
]

TRAFFIC = [
    ({"status": "open", "assignee": None}, "hi"),
    ({"status": "open", "assignee": None}, "my invoice is wrong"),
    ({"status": "assigned", "assignee": None}, "anyone there?"),
    ({"status": "assigned", "assignee": "dana"}, "thanks!"),
    ({"status": "closed", "assignee": "dana"}, "one more thing"),
]


def main() -> int:
    with watch(REGISTRY) as session:
        # How production runs: everything through the front door.
        for name, config, is_production in FLEET:
            with session.config(name, production=is_production):
                for ticket, text in TRAFFIC:
                    with entered("webhook"):
                        helpdesk.handle_inbound(dict(ticket), text, config)

        # How the suite exercises it: unit tests that call the flow directly.
        # These are the calls that make coverage look finished.
        with session.config("acme", production=True):
            helpdesk.flow_v1({"status": "assigned", "assignee": None}, "anyone there?", {})
            helpdesk.flow_v1({"status": "assigned", "assignee": "dana"}, "thanks!", {})

    report = session.report()
    print(report.describe())

    try:
        report.assert_live(silent_is="fail")
    except Unreachable as exc:
        print(f"\nFAIL\n{exc}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
