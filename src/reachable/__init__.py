"""Coverage says the line ran. It does not say production can get there.

    from reachable import Registry, watch, probe, entered

    registry = Registry({"wait_notice": "flows.py:2264"})

    with watch(registry) as session:
        with session.config("tenant-a", production=True):
            with entered("webhook"):
                handle(payload)

    session.report().assert_live(silent_is="fail")
"""

from ._probe import entered, probe
from ._report import Finding, Observation, Report, Unreachable, Verdict
from ._session import (
    ConflictingConfig,
    NoActiveConfig,
    Probe,
    Registry,
    Session,
    UndeclaredProbe,
    watch,
)

__all__ = [
    "ConflictingConfig",
    "Finding",
    "NoActiveConfig",
    "Observation",
    "Probe",
    "Registry",
    "Report",
    "Session",
    "UndeclaredProbe",
    "Unreachable",
    "Verdict",
    "entered",
    "probe",
    "watch",
]
__version__ = "0.1.0"
