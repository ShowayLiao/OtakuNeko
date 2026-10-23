"""Provider-neutral media capability backed by the qBittorrent service."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
from typing import Any

from app.capabilities.base import BaseCapability
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.core.logging import get_logger
from app.schemas.rss import RssRule
from app.capabilities.media_read_contracts import (
    READ_ACTIONS,
    INPUT_SCHEMA,
    ReadOutputError,
    output_schema,
    safe_read_output,
)


from app.capabilities.media_write_contracts import (
    WRITE_ACTIONS,
    WRITE_OUTPUT_SCHEMA,
    write_input_schema,
)

logger = get_logger(__name__)


class _QBServiceErrorPlaceholder(Exception):
    pass


QBService: Any = None
QBServiceError: Any = _QBServiceErrorPlaceholder


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
    if (
        config is None
        or not config.ENABLE_QB_PROXY
        or type(user_id) is not int
        or user_id <= 0
    ):
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
    return bool(allowed) and all(value > 0 for value in allowed) and user_id in allowed


def _provider_configured() -> bool:
    config = _settings()
    return bool(
        config and config.ENABLE_QB_PROXY and config.QB_HOST and config.QB_USERNAME
    )


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
        "status",
        "message",
        "error_code",
        "retryable",
        "old_resource_id",
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
        write_common: dict[str, Any] = {
            "requires_auth": True,
            "is_side_effect": True,
            "idempotency_mode": "required",
            "risk_level": "high",
        }
        actions = [
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
        return [
            replace(
                action,
                input_schema=deepcopy(INPUT_SCHEMA),
                output_schema=output_schema(action.name),
            )
            if action.name in READ_ACTIONS
            else replace(
                action,
                input_schema=write_input_schema(action.input_schema),
                output_schema=deepcopy(WRITE_OUTPUT_SCHEMA),
            )
            if action.name in WRITE_ACTIONS
            else action
            for action in actions
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
        if action in READ_ACTIONS:
            return await self._execute_read(action, handler, kwargs)
        try:
            return await handler(**kwargs)
        except ValueError:
            return CapabilityResult.fail(
                "Invalid media arguments", error_type="invalid_args"
            ).to_dict()
        except QBServiceError as exc:
            from app.services.qb_service import normalize_qb_read_error

            safe = normalize_qb_read_error(exc)
            return CapabilityResult.fail(
                safe.message, error_type=safe.error_code, retryable=False
            ).to_dict()
        except Exception:
            logger.error("media_capability_failed", extra={"action": action})
            return CapabilityResult.fail(
                "Media operation failed", error_type="internal"
            ).to_dict()

    async def _execute_read(
        self, action: str, handler: Any, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            result = await handler(**kwargs)
            return safe_read_output(action, result) if result.get("success") else result
        except QBServiceError as exc:
            from app.services.qb_service import normalize_qb_read_error

            error = normalize_qb_read_error(exc)
            return CapabilityResult.fail(
                error.message, error_type=error.error_code, retryable=error.retryable
            ).to_dict()
        except Exception as exc:
            logger.error(
                "media_read_failed",
                extra={"action": action, "error_type": type(exc).__name__},
            )
            code = (
                "invalid_output"
                if isinstance(exc, ReadOutputError)
                else ("invalid_args" if isinstance(exc, ValueError) else "internal")
            )
            return CapabilityResult.fail("Media read failed", error_type=code).to_dict()

    @staticmethod
    def _require_read_qb(kwargs: dict[str, Any]) -> dict[str, Any] | None:
        user_id = kwargs.get("user_id")
        if type(user_id) is not int or user_id <= 0:
            return CapabilityResult.fail(
                "Authentication is required", error_type="unauthorized"
            ).to_dict()
        config = _settings()
        if not (
            config and config.ENABLE_QB_PROXY and config.QB_HOST and config.QB_USERNAME
        ):
            return CapabilityResult.fail(
                "RSS management is not configured", error_type="not_configured"
            ).to_dict()
        tokens = [token.strip() for token in config.QB_ALLOWED_USER_IDS.split(",")]
        valid = all(
            token.isascii() and token.isdecimal() and int(token) > 0 for token in tokens
        )
        if not valid or user_id not in {int(token) for token in tokens}:
            return CapabilityResult.fail(
                "qBittorrent access is not authorized", error_type="forbidden"
            ).to_dict()
        return None

    async def _library_status(self, **kwargs: Any) -> dict[str, Any]:
        configured = _provider_configured()
        return CapabilityResult.ok(
            configured=configured,
            provider="qbittorrent" if configured else None,
        ).to_dict()

    async def _list_rss_feeds(self, **kwargs: Any) -> dict[str, Any]:
        access = self._require_read_qb(kwargs)
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
        access = self._require_read_qb(kwargs)
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
        if type(user_id) is not int or user_id <= 0:
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
        operation_result = _safe_operation_result(result)
        if operation_result.get("status") != "succeeded":
            return CapabilityResult.fail(
                "The operation state requires manual verification",
                error_type="attention_required",
                retryable=False,
            ).to_dict()
        return CapabilityResult.ok(
            operation=operation_result,
            idempotency_key=kwargs.get("idempotency_key"),
        ).to_dict()
