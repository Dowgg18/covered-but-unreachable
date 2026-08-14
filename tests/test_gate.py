"""What the gate refuses to let you configure away."""

from __future__ import annotations

import pytest

from reachable import Registry, Unreachable, Verdict, entered, probe, watch

REG = Registry({"p": "x.py:1", "q": "x.py:2"})


def _orphan_session():
    with watch(REG) as s, s.config("acme", production=True):
        probe("p")
        with entered("webhook"):
            probe("q")
    return s


def test_orphaned_fails_the_gate():
    with pytest.raises(Unreachable, match="ORPHANED"):
        _orphan_session().report().assert_live(silent_is="ignore")


def test_orphaned_cannot_be_allowlisted():
    """There is no thin-corpus story for an orphan: the code demonstrably ran.
    A flag to silence it would be a flag to silence the library."""
    report = _orphan_session().report()
    with pytest.raises(Unreachable, match="ORPHANED"):
        report.assert_live(
            silent_is="ignore",
            allow_preview={"p"},
            allow_partial={"p"},
        )


def test_silent_is_has_no_default():
    """A never-executed path is genuinely ambiguous, and only the author knows
    whether their corpus is broad enough to make silence damning."""
    with watch(REG) as s, s.config("acme", production=True), entered("webhook"):
        probe("p")
        probe("q")
    with pytest.raises(TypeError):
        s.report().assert_live()  # type: ignore[call-arg]


def test_silent_is_rejects_anything_it_does_not_understand():
    with watch(REG) as s, s.config("acme", production=True), entered("webhook"):
        probe("p")
        probe("q")
    with pytest.raises(ValueError, match="must be 'fail' or 'ignore'"):
        s.report().assert_live(silent_is="maybe")


def test_silent_can_be_failed_or_ignored():
    with watch(REG) as s, s.config("acme", production=True), entered("webhook"):
        probe("p")
    report = s.report()
    report.assert_live(silent_is="ignore")
    with pytest.raises(Unreachable, match="SILENT"):
        report.assert_live(silent_is="fail")


def test_preview_is_allowlisted_by_name_not_by_switch():
    """Naming the probe makes the exemption rot visibly once the flag ships."""
    with watch(REG) as s:
        with s.config("staging", production=False), entered("webhook"):
            probe("p")
            probe("q")
        with s.config("acme", production=True), entered("webhook"):
            probe("q")
    report = s.report()
    with pytest.raises(Unreachable, match="PREVIEW-ONLY"):
        report.assert_live(silent_is="ignore")
    report.assert_live(silent_is="ignore", allow_preview={"p"})


def test_partial_is_allowlisted_by_name():
    with watch(REG) as s:
        with s.config("acme", production=True), entered("webhook"):
            probe("p")
            probe("q")
        with s.config("globex", production=True), entered("webhook"):
            probe("q")
    report = s.report()
    with pytest.raises(Unreachable, match="PARTIAL"):
        report.assert_live(silent_is="ignore")
    report.assert_live(silent_is="ignore", allow_partial={"p"})


def test_a_clean_run_passes():
    with watch(REG) as s, s.config("acme", production=True), entered("webhook"):
        probe("p")
        probe("q")
    s.report().assert_live(silent_is="fail")


def test_the_report_has_no_truth_value():
    """'silent' and 'orphaned' are not the same kind of evidence, and a bool
    would be read as 'is my code fine'."""
    report = _orphan_session().report()
    with pytest.raises(TypeError, match="no truth value"):
        bool(report)


def test_describe_leads_with_the_worst_verdict():
    text = _orphan_session().report().describe()
    assert text.index("ORPHANED") < text.index("LIVE")


def test_describe_explains_an_orphan_without_the_reader_knowing_the_library():
    text = _orphan_session().report().describe()
    assert "never from an entrypoint" in text
    assert "nothing production runs does" in text


def test_verdict_values_are_stable():
    """They appear in CI output people grep for."""
    assert [v.value for v in Verdict] == [
        "live",
        "partial",
        "preview-only",
        "orphaned",
        "silent",
    ]
