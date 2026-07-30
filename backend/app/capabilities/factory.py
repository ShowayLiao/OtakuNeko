"""Shared production factory for the canonical capability registry."""

from app.capabilities.anime import AnimeCapability
from app.capabilities.media import MediaCapability
from app.capabilities.recommendation import RecommendationCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.schedule import ScheduleCapability
from app.capabilities.system import SystemCapability


def build_capability_registry() -> CapabilityRegistry:
    """Register the complete production capability inventory once."""
    registry = CapabilityRegistry()
    registry.register(AnimeCapability())
    registry.register(RecommendationCapability())
    registry.register(ScheduleCapability())
    registry.register(MediaCapability())
    registry.register(SystemCapability())
    return registry
