"""The registry of paths you claim matter, and the session that watches them."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ._probe import _recorder
from ._report import Finding, Observation, Report, Verdict

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


class UndeclaredProbe(LookupError):
    """A probe fired that the registry does not know about."""


class NoActiveConfig(RuntimeError):
    """A probe fired while a session was watching but no configuration was set."""


class ConflictingConfig(ValueError):
    """The same configuration name was used as production and as non-production."""


@dataclass(frozen=True, slots=True)
class Probe:
    name: str
    where: str


class Registry:
    """The paths you claim matter.

    Declaration is what makes `SILENT` observable at all: a probe that registers
    itself on first fire can never be reported as never-fired. So the registry is
    the list of branches you are willing to be held to.
    """

    def __init__(self, probes: Mapping[str, str]) -> None:
        if not probes:
            raise ValueError("a registry with no probes has nothing to report on")
        self._probes = {name: Probe(name, where) for name, where in probes.items()}

    def __contains__(self, name: object) -> bool:
        return name in self._probes

    def __len__(self) -> int:
        return len(self._probes)

    @property
    def probes(self) -> tuple[Probe, ...]:
        return tuple(self._probes.values())


class Session:
    """Collects observations while the production code runs."""

    def __init__(self, registry: Registry, *, strict: bool = True) -> None:
        self._registry = registry
        self._strict = strict
        self._observations: set[Observation] = set()
        self._counts: dict[str, int] = {}
        self._configs: dict[str, bool] = {}
        self._current: str | None = None

    # -- recording ---------------------------------------------------------

    def record(self, probe: str, entrypoint: str | None) -> None:
        if probe not in self._registry:
            if self._strict:
                raise UndeclaredProbe(
                    f"probe {probe!r} fired but is not declared in the registry. "
                    "An undeclared probe cannot be reported as dead, because the "
                    "report only knows about declarations — add it, or pass "
                    "strict=False if you are deliberately probing more than you grade."
                )
            return
        if self._current is None:
            raise NoActiveConfig(
                f"probe {probe!r} fired outside session.config(...). Every observation "
                "belongs to a configuration; if you only have one, name it."
            )
        self._counts[probe] = self._counts.get(probe, 0) + 1
        self._observations.add(Observation(probe, self._current, entrypoint))

    @contextmanager
    def config(self, name: str, *, production: bool) -> Iterator[None]:
        """Run the block under a named configuration.

        `production` has no default. Whether real users are served under this
        configuration is the fact that separates "shipped behind a flag" from
        "dead", and it is not something the library can infer.
        """
        known = self._configs.get(name)
        if known is not None and known != production:
            raise ConflictingConfig(
                f"config {name!r} was already used with production={known}"
            )
        self._configs[name] = production
        previous, self._current = self._current, name
        try:
            yield
        finally:
            self._current = previous

    # -- grading -----------------------------------------------------------

    def report(self) -> Report:
        prod = frozenset(n for n, is_prod in self._configs.items() if is_prod)
        every = frozenset(self._configs)
        findings = tuple(
            self._grade(p, prod) for p in self._registry.probes
        )
        return Report(findings=findings, configs=every, production_configs=prod)

    def _grade(self, p: Probe, prod: frozenset[str]) -> Finding:
        mine = [o for o in self._observations if o.probe == p.name]
        executions = self._counts.get(p.name, 0)
        if not mine:
            return Finding(p.name, p.where, Verdict.SILENT, executions)

        entered = [o for o in mine if o.entrypoint is not None]
        if not entered:
            return Finding(p.name, p.where, Verdict.ORPHANED, executions)

        reached_from = frozenset(o.entrypoint for o in entered if o.entrypoint)
        live_in = frozenset(o.config for o in entered) & prod
        preview_in = frozenset(o.config for o in entered) - prod
        dead_in = prod - live_in

        if not live_in:
            return Finding(
                p.name, p.where, Verdict.PREVIEW_ONLY, executions,
                reached_from=reached_from, preview_in=preview_in, dead_in=dead_in,
            )
        verdict = Verdict.LIVE if not dead_in else Verdict.PARTIAL
        return Finding(
            p.name, p.where, verdict, executions,
            reached_from=reached_from, live_in=live_in,
            dead_in=dead_in, preview_in=preview_in,
        )


@contextmanager
def watch(registry: Registry, *, strict: bool = True) -> Iterator[Session]:
    """Install a session for the duration of the block.

    Restores the previous recorder in a `finally`; a harness that leaks one turns
    every later test into a silent contributor to somebody else's report.
    """
    session = Session(registry, strict=strict)
    token = _recorder.set(session)
    try:
        yield session
    finally:
        _recorder.reset(token)
