"""A helpdesk that quietly stopped replying to people.

Every branch here is defensible on its own, which is the point. Nothing in this
file looks like a bug in review.
"""

from __future__ import annotations

from reachable import probe

# Two implementations of the same conversation, because someone started a
# rewrite. Which one runs is a per-tenant flag.


def handle_inbound(ticket: dict, text: str, config: dict) -> str | None:
    """The webhook. Every customer message in the product enters through here."""
    if ticket["status"] == "closed":
        probe("drop.closed")
        return None

    # An agent owns this ticket, so the bot must not talk over them. Defensible,
    # obvious, and the reason a third of this file is dead.
    if ticket["status"] == "assigned":
        return None

    if config.get("flow_v2"):
        return flow_v2(ticket, text, config)
    return flow_v1(ticket, text, config)


def flow_v1(ticket: dict, text: str, config: dict) -> str | None:
    """The flow every paying tenant is actually served by."""
    if ticket["status"] == "assigned":
        # Nobody has picked it up yet: say something rather than leave the
        # customer staring at their own last message.
        if ticket["assignee"] is None:
            probe("ack.unassigned.v1")
            return config.get("ack_text", "Thanks — someone will pick this up shortly.")
        probe("ack.assigned.v1")
        return None

    if _is_greeting(text):
        probe("greet.v1")
        return "Hi! What can we help with?"

    probe("fallback.v1")
    return "Got it, looking into this."


def flow_v2(ticket: dict, text: str, config: dict) -> str | None:
    """The rewrite. Behind a flag since the spring."""
    if ticket["status"] == "assigned" and ticket["assignee"] is None:
        probe("ack.unassigned.v2")
        return config.get("ack_text", "Thanks — someone will pick this up shortly.")

    if _is_greeting(text):
        probe("greet.v2")
        return "Hi there! What can we help with?"

    probe("fallback.v2")
    return "Got it, looking into this."


def _is_greeting(text: str) -> bool:
    return text.strip().lower() in {"hi", "hello", "hey"}
