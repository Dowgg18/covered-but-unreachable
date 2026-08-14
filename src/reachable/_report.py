"""Verdicts, and the one that has no knob."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Verdict(Enum):
    """What a session observed about one declared path."""

    LIVE = "live"
    """Reached from an entrypoint under every production configuration."""

    PARTIAL = "partial"
    """Reached under at least one production configuration, but not all of them."""

    PREVIEW_ONLY = "preview-only"
    """Reached from an entrypoint, but only under configurations nobody is served.

    A feature behind an off flag looks exactly like this, and so does a feature
    behind a flag everyone forgot to turn on.
    """

    ORPHANED = "orphaned"
    """Executed, but never from an entrypoint.

    The path runs in your suite and cannot run in production. There is no thin-
    corpus explanation for this one: the code demonstrably executes, so the
    corpus reaches it — just never through a door production uses.
    """

    SILENT = "silent"
    """Never executed at all.

    Weaker evidence than the others. It can mean the path is dead, and it can
    equally mean nothing in the corpus happened to steer that way.
    """


@dataclass(frozen=True, slots=True)
class Observation:
    probe: str
    config: str
    entrypoint: str | None


@dataclass(frozen=True, slots=True)
class Finding:
    probe: str
    where: str
    verdict: Verdict
    executions: int
    reached_from: frozenset[str] = frozenset()
    """Entrypoint names that reached this path."""
    live_in: frozenset[str] = frozenset()
    """Production configurations that reached it through an entrypoint."""
    dead_in: frozenset[str] = frozenset()
    """Production configurations that did not."""
    preview_in: frozenset[str] = frozenset()
    """Non-production configurations that reached it."""

    def describe(self) -> str:
        head = f"{self.verdict.value.upper():<12} {self.where}  {self.probe}"
        return f"{head}\n{_detail(self)}"


def _detail(f: Finding) -> str:
    pad = " " * 4
    if f.verdict is Verdict.ORPHANED:
        return (
            f"{pad}executed {f.executions}x, never from an entrypoint\n"
            f"{pad}something in the suite calls it directly; nothing production runs does"
        )
    if f.verdict is Verdict.SILENT:
        return f"{pad}never executed under any configuration in this run"
    if f.verdict is Verdict.PREVIEW_ONLY:
        return (
            f"{pad}reached only under non-production config: {_names(f.preview_in)}\n"
            f"{pad}dead for everyone actually being served: {_names(f.dead_in)}"
        )
    if f.verdict is Verdict.PARTIAL:
        return (
            f"{pad}live in {_names(f.live_in)}\n"
            f"{pad}dead in {_names(f.dead_in)}"
        )
    return f"{pad}live in {_names(f.live_in)} via {_names(f.reached_from)}"


def _names(names: frozenset[str]) -> str:
    return ", ".join(sorted(names)) if names else "(none)"


class Unreachable(AssertionError):
    """Raised by `Report.assert_live` when a declared path cannot be reached."""


@dataclass(frozen=True, slots=True)
class Report:
    findings: tuple[Finding, ...]
    configs: frozenset[str] = field(default_factory=frozenset)
    production_configs: frozenset[str] = field(default_factory=frozenset)

    def of(self, verdict: Verdict) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.verdict is verdict)

    @property
    def orphaned(self) -> tuple[Finding, ...]:
        return self.of(Verdict.ORPHANED)

    @property
    def silent(self) -> tuple[Finding, ...]:
        return self.of(Verdict.SILENT)

    @property
    def preview_only(self) -> tuple[Finding, ...]:
        return self.of(Verdict.PREVIEW_ONLY)

    @property
    def partial(self) -> tuple[Finding, ...]:
        return self.of(Verdict.PARTIAL)

    @property
    def live(self) -> tuple[Finding, ...]:
        return self.of(Verdict.LIVE)

    def __bool__(self) -> bool:
        raise TypeError(
            "Report has no truth value on purpose. 'silent' and 'orphaned' are not "
            "the same kind of evidence and must not collapse into one boolean — "
            "use assert_live(silent_is=...) and say what a never-executed path means "
            "to you."
        )

    def describe(self) -> str:
        order = (
            Verdict.ORPHANED,
            Verdict.PREVIEW_ONLY,
            Verdict.PARTIAL,
            Verdict.SILENT,
            Verdict.LIVE,
        )
        lines = [
            f"reachable: {len(self.findings)} declared path(s) across "
            f"{len(self.production_configs)} production and "
            f"{len(self.configs) - len(self.production_configs)} non-production config(s)"
        ]
        for verdict in order:
            for finding in self.of(verdict):
                lines.append(finding.describe())
        return "\n".join(lines)

    def assert_live(
        self,
        *,
        silent_is: Verdict | str,
        allow_preview: frozenset[str] | set[str] = frozenset(),
        allow_partial: frozenset[str] | set[str] = frozenset(),
    ) -> None:
        """Fail if a declared path cannot be reached the way production runs.

        `silent_is` has no default. A path that never executed is genuinely
        ambiguous — dead code, or a corpus that never steered that way — and only
        you know which your suite is good enough to distinguish. Pass `"fail"` if
        your corpus is broad enough that silence is damning, `"ignore"` if it is
        not.

        `ORPHANED` has no knob and never will. The path executed, so the corpus
        reaches it; it simply cannot be reached through a door production uses.
        That is the bug this library exists to find, and a flag to silence it is
        a flag to silence the library.

        The allowlists take probe names rather than being global switches, so a
        feature parked behind an off flag has to be named — and the name rots
        visibly once the flag ships.
        """
        silent_mode = silent_is.value if isinstance(silent_is, Verdict) else str(silent_is)
        if silent_mode not in ("fail", "ignore"):
            raise ValueError(f"silent_is must be 'fail' or 'ignore', got {silent_is!r}")

        bad: list[Finding] = list(self.orphaned)
        bad += [f for f in self.preview_only if f.probe not in allow_preview]
        bad += [f for f in self.partial if f.probe not in allow_partial]
        if silent_mode == "fail":
            bad += list(self.silent)

        if not bad:
            return
        body = "\n".join(f.describe() for f in bad)
        raise Unreachable(
            f"{len(bad)} declared path(s) cannot be reached the way production runs.\n{body}"
        )
