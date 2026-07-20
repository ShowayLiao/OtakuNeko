"""Media capability — provider-neutral interface for media library operations.

This is a boundary capability for future integrations (qBittorrent, Plex,
etc.).  Initially only media status and metadata actions are wired; provider-
specific actions (RSS, downloads) are placeholders that return a clear
``not_configured`` error.
"""

from __future__ import annotations

from typing import Any

from app.capabilities.base import BaseCapability
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.core.logging import get_logger

logger = get_logger(__name__)


class MediaCapability(BaseCapability):
    """Provider-neutral media library boundary.

    Unsupported actions return ``not_configured`` so agents can detect
    capabilities that exist in the interface but lack a runtime backend.
    """

    @property
    def name(self) -> str:
        return "media"

    @property
    def description(self) -> str:
        return "Media library lookup, RSS feed management, and download rules"

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name="library_status",
                description="Check media library connection status",
                input_schema={"type": "object", "properties": {}},
            ),
            ActionDescriptor(
                name="list_rss_feeds",
                description="List configured RSS feeds",
                input_schema={"type": "object", "properties": {}},
                requires_auth=True,
            ),
            ActionDescriptor(
                name="add_rss_feed",
                description="Add or update an RSS subscription feed",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "RSS feed URL"},
                        "name": {"type": "string", "description": "Feed display name"},
                    },
                    "required": ["url"],
                },
                requires_auth=True,
                is_side_effect=True,
            ),
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        handlers: dict[str, Any] = {
            "library_status": self._library_status,
            "list_rss_feeds": self._list_rss_feeds,
            "add_rss_feed": self._add_rss_feed,
        }
        handler = handlers.get(action)
        if handler is None:
            return CapabilityResult.fail(
                f"Unknown action: {action}", error_type="invalid_action"
            ).to_dict()
        try:
            return await handler(**kwargs)
        except Exception as exc:
            logger.error(
                "media_capability_failed",
                extra={"action": action, "error": str(exc)},
            )
            return CapabilityResult.fail(str(exc), error_type="internal").to_dict()

    async def _library_status(self, **kwargs: Any) -> dict[str, Any]:
        try:
            from app.core.config import settings

            configured = bool(settings.QB_HOST and settings.QB_USERNAME)
        except Exception:
            # A capability import must not make unrelated registry/MCP use
            # fail because an optional provider's settings are malformed.
            configured = False
        return CapabilityResult.ok(
            configured=configured,
            provider="qbittorrent" if configured else None,
        ).to_dict()

    async def _list_rss_feeds(self, **kwargs: Any) -> dict[str, Any]:
        return CapabilityResult.ok(
            feeds=[],
            configured=False,
            message="RSS management is not yet configured",
        ).to_dict()

    async def _add_rss_feed(self, **kwargs: Any) -> dict[str, Any]:
        return CapabilityResult.fail(
            "RSS management is not yet configured", error_type="not_configured"
        ).to_dict()
