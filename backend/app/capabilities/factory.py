"""Shared production factory for the canonical capability registry."""

from app.capabilities.anime import AnimeCapability
from app.capabilities.collections import CollectionCapability
from app.capabilities.media import MediaCapability
from app.capabilities.recommendation import RecommendationCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.schedule import ScheduleCapability
from app.capabilities.stats import StatsCapability
from app.capabilities.system import SystemCapability
from app.capabilities.subjects import SubjectCapability


def build_capability_registry() -> CapabilityRegistry:
    """Register the complete production capability inventory once."""
    registry = CapabilityRegistry()
    registry.register(AnimeCapability())
    registry.register(CollectionCapability())
    registry.register(RecommendationCapability())
    registry.register(ScheduleCapability())
    registry.register(SubjectCapability())
    registry.register(StatsCapability())
    registry.register(MediaCapability())
    registry.register(SystemCapability())
    return registry
