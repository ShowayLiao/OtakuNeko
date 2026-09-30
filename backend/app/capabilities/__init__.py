"""Capability layer package.

Capabilities encapsulate what the system can do — anime search, scheduling,
recommendations, etc. — with a stable interface so agents depend on
capabilities rather than directly on tools or services.
"""

from app.capabilities.base import BaseCapability
from app.capabilities.anime import AnimeCapability
from app.capabilities.recommendation import RecommendationCapability
from app.capabilities.schedule import ScheduleCapability
from app.capabilities.media import MediaCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.factory import build_capability_registry
from app.capabilities.types import ActionDescriptor, CapabilityResult

__all__ = [
    "BaseCapability",
    "AnimeCapability",
    "RecommendationCapability",
    "ScheduleCapability",
    "MediaCapability",
    "CapabilityRegistry",
    "ActionDescriptor",
    "CapabilityResult",
    "build_capability_registry",
]
