"""Capability layer package.

Capabilities encapsulate what the system can do — anime search, scheduling,
recommendations, etc. — with a stable interface so agents depend on
capabilities rather than directly on tools or services.
"""

from app.capabilities.base import BaseCapability
from app.capabilities.anime import AnimeCapability
from app.capabilities.registry import CapabilityRegistry

__all__ = ["BaseCapability", "AnimeCapability", "CapabilityRegistry"]
