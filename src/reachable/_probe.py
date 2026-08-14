"""The two calls production code ever sees.

`probe` marks a branch you believe in. `entered` marks the door production
actually comes through. Everything else in this package is bookkeeping on top of
those two facts.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterator


class Recorder(Protocol):
    def record(self, probe: str, entrypoint: str | None) -> None: ...


# None whenever nothing is watching, which is the production case. `probe` then
# costs one ContextVar lookup and an identity check. That budget is deliberate:
# a probe you strip for performance is a probe that stops telling you the truth,
# and the branches worth probing are the rare ones anyway.
_recorder: ContextVar[Recorder | None] = ContextVar("reachable_recorder", default=None)
_entrypoint: ContextVar[str | None] = ContextVar("reachable_entrypoint", default=None)


def probe(name: str) -> None:
    """Record that this branch just executed.

    A no-op unless a session is watching, so it is safe to leave in shipped code.
    """
    recorder = _recorder.get()
    if recorder is None:
        return
    recorder.record(name, _entrypoint.get())


@contextmanager
def entered(name: str) -> Iterator[None]:
    """Mark a boundary that production enters through.

    Nested calls keep the outermost name. If a webhook handler calls a flow that
    also declares an entrypoint, the honest answer to "how did production get
    here" is still the webhook — and recording the inner one would let a probe
    look reachable because a test entered halfway down.
    """
    if _entrypoint.get() is not None:
        yield
        return
    token = _entrypoint.set(name)
    try:
        yield
    finally:
        _entrypoint.reset(token)
