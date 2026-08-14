"""The demo is a claim about a real bug shape. Assert it, so it stays true."""

from __future__ import annotations

from demo.helpdesk import flow_v1, handle_inbound
from demo.run_gate import FLEET, REGISTRY, TRAFFIC, main
from reachable import Verdict, entered, watch


def _report():
    with watch(REGISTRY) as s:
        for name, config, is_production in FLEET:
            with s.config(name, production=is_production):
                for ticket, text in TRAFFIC:
                    with entered("webhook"):
                        handle_inbound(dict(ticket), text, config)
        with s.config("acme", production=True):
            flow_v1({"status": "assigned", "assignee": None}, "anyone there?", {})
            flow_v1({"status": "assigned", "assignee": "dana"}, "thanks!", {})
    return s.report()


def _verdict(report, probe):
    return next(f for f in report.findings if f.probe == probe).verdict


def test_the_acknowledgement_runs_in_the_suite_and_cannot_run_in_production():
    """The early return in handle_inbound orphans it. Unit tests calling flow_v1
    directly are the only reason it executes at all — which is also the reason
    coverage reports it as covered."""
    report = _report()
    finding = next(f for f in report.findings if f.probe == "ack.unassigned.v1")
    assert finding.verdict is Verdict.ORPHANED
    assert finding.executions == 1


def test_the_rewrite_is_reachable_only_for_a_tenant_nobody_is():
    """The whole v2 flow serves zero real users, while being the first thing
    anyone opens when they go looking for the bug."""
    report = _report()
    for name in ("greet.v2", "fallback.v2"):
        finding = next(f for f in report.findings if f.probe == name)
        assert finding.verdict is Verdict.PREVIEW_ONLY
        assert finding.preview_in == frozenset({"staging"})
        assert finding.dead_in == frozenset({"acme", "globex", "initech"})


def test_fixing_it_in_the_rewrite_would_have_fixed_nothing():
    """The sharpest finding in the demo, and the trap that makes this a class of
    bug rather than a bug: the same early return orphans the acknowledgement in
    *both* implementations. Porting the fix into v2 produces a green suite, a
    convincing commit, and no change whatsoever for a customer — the branch is
    not even preview-only, it is unreachable in the flow nobody runs.
    """
    assert _verdict(_report(), "ack.unassigned.v2") is Verdict.SILENT


def test_the_paths_that_are_genuinely_fine_are_reported_as_fine():
    """A gate that flags everything gets turned off in a month."""
    report = _report()
    for name in ("drop.closed", "greet.v1", "fallback.v1"):
        assert _verdict(report, name) is Verdict.LIVE


def test_the_assigned_branch_is_orphaned_too():
    """Same early return, quieter consequence: the bot stays silent either way,
    so nobody noticed this one was dead."""
    assert _verdict(_report(), "ack.assigned.v1") is Verdict.ORPHANED


def test_the_gate_exits_nonzero():
    assert main() == 1
