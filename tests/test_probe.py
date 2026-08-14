"""The two production-facing calls."""

from __future__ import annotations

import threading

import pytest

from reachable import Registry, Verdict, entered, probe, watch
from reachable._probe import _entrypoint, _recorder

REG = Registry({"a": "x.py:1", "b": "x.py:2"})


def test_probe_is_inert_when_nobody_is_watching():
    """It ships in production code, so the no-session path must do nothing."""
    assert _recorder.get() is None
    probe("anything at all")  # must not raise, must not need a registry


def test_watch_restores_the_previous_recorder():
    """A harness that leaks a recorder turns every later test into a silent
    contributor to somebody else's report."""
    with watch(REG):
        assert _recorder.get() is not None
    assert _recorder.get() is None


def test_watch_restores_even_when_the_block_raises():
    with pytest.raises(RuntimeError, match="boom"), watch(REG):
        raise RuntimeError("boom")
    assert _recorder.get() is None


def test_nested_entrypoints_keep_the_outermost():
    """How production got here is the outer door. Recording the inner one would
    let a probe look reachable because a test entered halfway down."""
    with watch(REG) as s, s.config("c", production=True), entered("webhook"), entered("flow"):
        probe("a")
    live = s.report().live[0]
    assert live.reached_from == frozenset({"webhook"})


def test_entrypoint_is_cleared_after_the_block():
    with watch(REG) as s, s.config("c", production=True):
        with entered("webhook"):
            pass
        probe("a")
    assert _entrypoint.get() is None
    assert s.report().orphaned[0].probe == "a"


def test_a_probe_in_a_worker_thread_is_invisible_entirely():
    """Documented limit, asserted so it cannot drift: contextvars do not cross a
    thread boundary, so a probe running in a pool sees no recorder at all. It
    does not read as orphaned — it reads as never executed, which is the more
    dangerous mistake, because SILENT is the verdict people are told to weigh
    against a thin corpus.
    """
    with watch(REG) as s, s.config("c", production=True), entered("webhook"):
        t = threading.Thread(target=lambda: probe("a"))
        t.start()
        t.join()
    finding = next(f for f in s.report().findings if f.probe == "a")
    assert finding.verdict is Verdict.SILENT
    assert finding.executions == 0
