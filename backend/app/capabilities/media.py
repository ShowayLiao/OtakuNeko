"""Provider-neutral media capability backed by the qBittorrent service."""

from __future__ import annotations

import asyncio
from typing import Any

from app.capabilities.base import BaseCapability
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.core.logging import get_logger
from app.schemas.rss import RssRule


logger = get_logger(__name__)


class _QBServiceErrorPlaceholder(Exception):
    pass


QBService: Any = None
QBServiceError: type[Exception] = _QBServiceErrorPlaceholder


def _new_qb() -> Any:
    global QBService, QBServiceError
    if QBService is None:
        from app.services.qb_service import QBService as Service
        from app.services.qb_service import QBServiceError as ServiceError

        QBService = Service
        QBServiceError = ServiceError
    return QBService()


def _settings() -> Any:
    try:
        from app.core.config import settings

        return settings
    except Exception:
        return None


def _qb_access_allowed(user_id: int | None) -> bool:
    """Mirror the server-owned qB allowlist without exposing provider config."""
    config = _settings()
    if config is None or not config.ENABLE_QB_PROXY or not isinstance(user_id, int) or user_id <= 0:
        return False
    raw = config.QB_ALLOWED_USER_IDS.strip()
    if not raw:
        return False
    try:
        tokens = [token.strip() for token in raw.split(",")]
        if any(not token.isascii() or not token.isdecimal() for token in tokens):
            return False
        allowed = {int(token) for token in tokens}
    except ValueError:
        return False
    return bool(allowed) and user_id in allowed


def _provider_configured() -> bool:
    config = _settings()
    return bool(config and config.ENABLE_QB_PROXY and config.QB_HOST and config.QB_USERNAME)


def _safe_model(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _safe_model(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {key: _safe_model(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_model(item) for item in value]
    return value


def _safe_rss_rules(value: Any) -> dict[str, Any]:
    payload = _safe_model(value)
    rules = payload.get("rules", {}) if isinstance(payload, dict) else {}
    safe: dict[str, Any] = {}
    for name, rule in rules.items():
        if isinstance(rule, dict):
            safe[name] = {
                key: item for key, item in rule.items() if key != "torrentParams"
            }
    return safe


def _safe_operation_result(result: Any) -> dict[str, Any]:
    payload = _safe_model(result)
    if not isinstance(payload, dict):
        return {"status": "succeeded", "message": "Operation completed."}
    allowed = {
        "status", "message", "error_code", "retryable", "old_resource_id",
        "compensation_status",
    }
    return {key: value for key, value in payload.items() if key in allowed}


class MediaCapability(BaseCapability):
    """Media library boundary with explicit qBittorrent authorization."""

    @property
    def name(self) -> str:
        return "media"

    @property
    def description(self) -> str:
        return "Media library lookup, RSS feed management, and download rules"

    def actions(self) -> list[ActionDescriptor]:
        write_common = {
            "requires_auth": True,
            "is_side_effect": True,
            "idempotency_mode": "required",
            "risk_level": "high",
        }
        return [
            ActionDescriptor(
                name="library_status",
                public_name="library_status",
                description="Check media library connection status",
                input_schema={"type": "object", "properties": {}},
            ),
            ActionDescriptor(
                name="list_rss_feeds",
                public_name="list_rss_feeds",
                description="List configured RSS feeds",
                input_schema={"type": "object", "properties": {}},
                requires_auth=True,
            ),
            ActionDescriptor(
                name="list_rss_rules",
                public_name="list_rss_rules",
                description="List configured RSS automation rules without provider secrets",
                input_schema={"type": "object", "properties": {}},
                requires_auth=True,
            ),
            ActionDescriptor(
                name="add_rss_feed",
                public_name="add_rss_feed",
                description="Add an RSS subscription feed",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "name": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["url"],
                },
                max_payload_bytes=16 * 1024,
                **write_common,
            ),
            ActionDescriptor(
                name="upsert_rss_feed",
                public_name="upsert_rss_feed",
                description="Create or update an RSS subscription feed",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "name": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["url"],
                },
                max_payload_bytes=16 * 1024,
                **write_common,
            ),
            ActionDescriptor(
                name="remove_rss_feed",
                public_name="remove_rss_feed",
                description="Remove an RSS feed by provider item path",
                input_schema={
                    "type": "object",
                    "properties": {
                        "item_path": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["item_path"],
                },
                max_payload_bytes=16 * 1024,
                **write_common,
            ),
            ActionDescriptor(
                name="set_rss_rule",
                public_name="set_rss_rule",
                description="Create or replace an RSS automation rule",
                input_schema={
                    "type": "object",
                    "properties": {
                        "rule_name": {"type": "string"},
                        "rule": {"type": "object"},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["rule_name", "rule"],
                },
                max_payload_bytes=256 * 1024,
                **write_common,
            ),
            ActionDescriptor(
                name="remove_rss_rule",
                public_name="remove_rss_rule",
                description="Remove an RSS automation rule",
                input_schema={
                    "type": "object",
                    "properties": {
                        "rule_name": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["rule_name"],
                },
                max_payload_bytes=16 * 1024,
                **write_common,
            ),
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        handlers: dict[str, Any] = {
            "library_status": self._library_status,
            "list_rss_feeds": self._list_rss_feeds,
            "list_rss_rules": self._list_rss_rules,
            "add_rss_feed": self._add_rss_feed,
            "upsert_rss_feed": self._upsert_rss_feed,
            "remove_rss_feed": self._remove_rss_feed,
            "set_rss_rule": self._set_rss_rule,
            "remove_rss_rule": self._remove_rss_rule,
        }
        handler = handlers.get(action)
        if handler is None:
            return CapabilityResult.fail(
                f"Unknown action: {action}", error_type="invalid_action"
            ).to_dict()
        try:
            return await handler(**kwargs)
        except ValueError as exc:
            return CapabilityResult.fail(str(exc), error_type="invalid_args").to_dict()
        except QBServiceError as exc:
            return CapabilityResult.fail(
                exc.message, error_type=exc.error_code, retryable=exc.retryable
            ).to_dict()
        except Exception:
            logger.exception("media_capability_failed", extra={"action": action})
            return CapabilityResult.fail(
                "Media operation failed", error_type="internal"
            ).to_dict()

    async def _library_status(self, **kwargs: Any) -> dict[str, Any]:
        configured = _provider_configured()
        return CapabilityResult.ok(
            configured=configured,
            provider="qbittorrent" if configured else None,
        ).to_dict()

    async def _list_rss_feeds(self, **kwargs: Any) -> dict[str, Any]:
        user_id = kwargs.get("user_id")
        if not isinstance(user_id, int):
            return CapabilityResult.ok(feeds={}, configured=False).to_dict()
        access = self._require_qb(kwargs)
        if access is not None:
            return access
        result = await asyncio.to_thread(lambda: _new_qb().get_rss_items())
        payload = _safe_model(result)
        if not isinstance(payload, dict) and hasattr(result, "items"):
            payload = {"items": _safe_model(result.items)}
        return CapabilityResult.ok(
            feeds=payload.get("items", {}), configured=True
        ).to_dict()

    async def _list_rss_rules(self, **kwargs: Any) -> dict[str, Any]:
        access = self._require_qb(kwargs)
        if access is not None:
            return access
        return CapabilityResult.ok(
            rules=_safe_rss_rules(
                await asyncio.to_thread(lambda: _new_qb().get_rss_rules())
            )
        ).to_dict()

    async def _add_rss_feed(self, **kwargs: Any) -> dict[str, Any]:
        access = self._require_qb(kwargs, preserve_unconfigured=True)
        if access is not None:
            return access
        return await self._run_write(
            lambda: _new_qb().add_rss_feed(kwargs["url"], kwargs.get("name")),
            kwargs,
        )

    async def _upsert_rss_feed(self, **kwargs: Any) -> dict[str, Any]:
        access = self._require_qb(kwargs)
        if access is not None:
            return access
        return await self._run_write(
            lambda: _new_qb().upsert_rss_feed(kwargs["url"], kwargs.get("name")),
            kwargs,
        )

    async def _remove_rss_feed(self, **kwargs: Any) -> dict[str, Any]:
        access = self._require_qb(kwargs)
        if access is not None:
            return access
        return await self._run_write(
            lambda: _new_qb().remove_rss_item(kwargs["item_path"]), kwargs
        )

    async def _set_rss_rule(self, **kwargs: Any) -> dict[str, Any]:
        access = self._require_qb(kwargs)
        if access is not None:
            return access
        return await self._run_write(
            lambda: _new_qb().set_rss_rule(
                kwargs["rule_name"], RssRule(**kwargs["rule"])
            ),
            kwargs,
        )

    async def _remove_rss_rule(self, **kwargs: Any) -> dict[str, Any]:
        access = self._require_qb(kwargs)
        if access is not None:
            return access
        return await self._run_write(
            lambda: _new_qb().remove_rss_rule(kwargs["rule_name"]), kwargs
        )

    @staticmethod
    def _require_qb(
        kwargs: dict[str, Any], *, preserve_unconfigured: bool = False
    ) -> dict[str, Any] | None:
        user_id = kwargs.get("user_id")
        if not isinstance(user_id, int):
            if preserve_unconfigured and not _provider_configured():
                return CapabilityResult.fail(
                    "RSS management is not yet configured", error_type="not_configured"
                ).to_dict()
            return CapabilityResult.fail(
                "Authentication is required", error_type="unauthorized"
            ).to_dict()
        if not _provider_configured():
            return CapabilityResult.fail(
                "RSS management is not configured", error_type="not_configured"
            ).to_dict()
        if not _qb_access_allowed(user_id):
            return CapabilityResult.fail(
                "qBittorrent access is not authorized", error_type="forbidden"
            ).to_dict()
        return None

    @staticmethod
    async def _run_write(operation: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
        result = await asyncio.to_thread(operation)
        return CapabilityResult.ok(
            operation=_safe_operation_result(result),
            idempotency_key=kwargs.get("idempotency_key"),
        ).to_dict()
