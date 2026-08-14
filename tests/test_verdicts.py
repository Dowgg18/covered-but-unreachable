"""The five verdicts, and the boundaries between them."""

from __future__ import annotations

import pytest

from reachable import (
    ConflictingConfig,
    NoActiveConfig,
    Registry,
    UndeclaredProbe,
    Verdict,
    entered,
    probe,
    watch,
)

REG = Registry({"p": "x.py:1"})


def _verdict(session):
    return session.report().findings[0].verdict


def test_live_when_every_production_config_reaches_it():
    with watch(REG) as s:
        for name in ("a", "b"):
            with s.config(name, production=True), entered("webhook"):
                probe("p")
    assert _verdict(s) is Verdict.LIVE


def test_partial_names_the_configs_that_cannot_reach_it():
    with watch(REG) as s:
        with s.config("a", production=True), entered("webhook"):
            probe("p")
        with s.config("b", production=True), entered("webhook"):
            pass
    finding = s.report().findings[0]
    assert finding.verdict is Verdict.PARTIAL
    assert finding.dead_in == frozenset({"b"})
    assert finding.live_in == frozenset({"a"})


def test_preview_only_when_the_flag_is_on_for_nobody_real():
    """The shape of a rewrite that shipped behind a flag and was never enabled."""
    with watch(REG) as s:
        with s.config("staging", production=False), entered("webhook"):
            probe("p")
        with s.config("acme", production=True), entered("webhook"):
            pass
    finding = s.report().findings[0]
    assert finding.verdict is Verdict.PREVIEW_ONLY
    assert finding.preview_in == frozenset({"staging"})
    assert finding.dead_in == frozenset({"acme"})


def test_orphaned_when_it_only_ever_ran_from_a_direct_call():
    """The headline. The line executes in the suite and cannot execute in
    production, which is exactly what coverage cannot tell you."""
    with watch(REG) as s, s.config("acme", production=True):
        probe("p")
        probe("p")
    finding = s.report().findings[0]
    assert finding.verdict is Verdict.ORPHANED
    assert finding.executions == 2


def test_one_entrypoint_hit_is_enough_to_stop_being_orphaned():
    """Orphaned means *never* through the door, not mostly-not."""
    with watch(REG) as s, s.config("acme", production=True):
        probe("p")
        with entered("webhook"):
            probe("p")
    assert _verdict(s) is Verdict.LIVE


def test_silent_when_it_never_ran_at_all():
    with watch(REG) as s, s.config("acme", production=True), entered("webhook"):
        pass
    finding = s.report().findings[0]
    assert finding.verdict is Verdict.SILENT
    assert finding.executions == 0


# -- the registry is a commitment ------------------------------------------


def test_an_undeclared_probe_raises_by_default():
    """A probe that registers itself on first fire can never be reported as
    never-fired, which would quietly delete the SILENT verdict."""
    with (
        pytest.raises(UndeclaredProbe, match="not declared"),
        watch(REG) as s,
        s.config("a", production=True),
    ):
        probe("typo.in.the.name")


def test_strict_false_lets_you_probe_more_than_you_grade():
    with watch(REG, strict=False) as s, s.config("a", production=True), entered("w"):
        probe("not.graded")
        probe("p")
    assert _verdict(s) is Verdict.LIVE


def test_an_empty_registry_is_refused():
    with pytest.raises(ValueError, match="nothing to report"):
        Registry({})


def test_a_probe_outside_any_config_is_a_harness_bug():
    with pytest.raises(NoActiveConfig, match="belongs to a configuration"), watch(REG):
        probe("p")


def test_a_config_cannot_be_production_in_one_place_and_not_another():
    with pytest.raises(ConflictingConfig, match="production=True"), watch(REG) as s:
        with s.config("a", production=True):
            pass
        with s.config("a", production=False):
            pass
