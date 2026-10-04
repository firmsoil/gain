"""In-tree AI Attribution Harvester & Telemetry Synthesis (SE 3.0)."""

from gain.attribution.detector import AIAttributionDetector
from gain.attribution.models import (
    AttributionReport,
    AttributionSignal,
    AttributionSignalType,
)

__all__ = [
    "AIAttributionDetector",
    "AttributionReport",
    "AttributionSignal",
    "AttributionSignalType",
]
