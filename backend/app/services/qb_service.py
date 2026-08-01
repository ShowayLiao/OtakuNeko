from __future__ import annotations

from typing import Any, Optional

import qbittorrentapi

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.rss import RssItemsResponse, RssRule, RssRulesResponse


logger = get_logger(__name__)


class QBServiceError(RuntimeError):
    """Safe, stable qBittorrent error for API and Harness boundaries."""

    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        status_code: int = 502,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable


class QBService:
    """qBittorrent RSS adapter with safe errors and bounded compensation."""

    def __init__(self, client: Any | None = None) -> None:
        self.client = client
        if self.client is None:
            self._initialize_client()

    def _initialize_client(self) -> None:
        try:
            self.client = qbittorrentapi.Client(
                host=settings.QB_HOST,
                username=settings.QB_USERNAME,
                password=settings.QB_PASSWORD,
            )
            self.client.auth_log_in()
        except Exception as error:
            self._raise_safe(error, "qB client initialization")

    def get_client(self) -> Any:
        if self.client is None:
            self._initialize_client()
        return self.client

    def get_rss_items(self) -> RssItemsResponse:
        try:
            result = self.get_client().rss_items()
            return RssItemsResponse(items=result if isinstance(result, dict) else {})
        except Exception as error:
            self._raise_safe(error, "rss list")
        raise AssertionError("unreachable")

    def add_rss_feed(self, url: str, name: Optional[str] = None) -> dict[str, Any]:
        try:
            self.get_client().rss_add_feed(url=url, item_path=name)
            logger.info("qB RSS add completed")
            return {"status": "succeeded", "message": "RSS feed added."}
        except Exception as error:
            self._raise_safe(error, "rss add")
        raise AssertionError("unreachable")

    def upsert_rss_feed(self, url: str, name: Optional[str]) -> dict[str, Any]:
        client = self.get_client()
        try:
            current_feeds = client.rss_items(include_feed_data=True)
            existing = (
                current_feeds.get(name)
                if isinstance(current_feeds, dict)
                else None
            )
            existing_url = self._field(existing, "url")
            old_resource_id = self._resource_id(existing, name or "rss-feed")

            if existing is not None and existing_url == url:
                return {
                    "status": "succeeded",
                    "message": "RSS feed is already up to date.",
                }

            if existing is not None:
                try:
                    client.rss_remove_item(item_path=name)
                except Exception as error:
                    self._raise_safe(error, "rss upsert remove")

            try:
                client.rss_add_feed(url=url, item_path=name)
            except Exception as error:
                return self._compensate_after_add_failure(
                    client,
                    name=name,
                    old_url=existing_url,
                    old_resource_id=old_resource_id,
                    error=error,
                )

            try:
                verified = client.rss_items(include_feed_data=True)
            except Exception as error:
                return self._attention_result(
                    error_code="qb_upsert_verify_failed",
                    message="The RSS update needs manual verification.",
                    old_resource_id=old_resource_id,
                    retryable=self._classify(error).retryable,
                )
            verified_feed = (
                verified.get(name) if isinstance(verified, dict) else None
            )
            if self._field(verified_feed, "url") != url:
                return self._attention_result(
                    error_code="qb_upsert_verify_failed",
                    message="The RSS update needs manual verification.",
                    old_resource_id=old_resource_id,
                    retryable=False,
                )
            return {"status": "succeeded", "message": "RSS feed upserted."}
        except QBServiceError:
            raise
        except Exception as error:
            self._raise_safe(error, "rss upsert")
        raise AssertionError("unreachable")

    def remove_rss_item(self, item_path: str) -> dict[str, Any]:
        try:
            self.get_client().rss_remove_item(item_path=item_path)
            return {"status": "succeeded", "message": "RSS item removed."}
        except Exception as error:
            self._raise_safe(error, "rss remove")
        raise AssertionError("unreachable")

    def set_rss_rule(self, rule_name: str, rule: RssRule) -> dict[str, Any]:
        try:
            rule_params = rule.model_dump(exclude_unset=True, by_alias=True)
            self.get_client().rss_set_rule(
                rule_name=rule_name,
                rule_def=rule_params,
            )
            return {"status": "succeeded", "message": "RSS rule set."}
        except Exception as error:
            self._raise_safe(error, "rss set rule")
        raise AssertionError("unreachable")

    def remove_rss_rule(self, rule_name: str) -> dict[str, Any]:
        try:
            self.get_client().rss_remove_rule(rule_name=rule_name)
            return {"status": "succeeded", "message": "RSS rule removed."}
        except Exception as error:
            self._raise_safe(error, "rss remove rule")
        raise AssertionError("unreachable")

    def get_rss_rules(self) -> RssRulesResponse:
        try:
            result = self.get_client().rss_rules()
            return RssRulesResponse(rules=result if isinstance(result, dict) else {})
        except Exception as error:
            self._raise_safe(error, "rss rules list")
        raise AssertionError("unreachable")

    def _compensate_after_add_failure(
        self,
        client: Any,
        *,
        name: Optional[str],
        old_url: str,
        old_resource_id: str,
        error: Exception,
    ) -> dict[str, Any]:
        classified = self._classify(error)
        compensation_status = "not_attempted"
        if old_url:
            try:
                client.rss_add_feed(url=old_url, item_path=name)
                compensation_status = "succeeded"
            except Exception:
                compensation_status = "failed"
        return {
            "status": "attention_required",
            "error_code": (
                "qb_connection_error"
                if classified.retryable
                else "qb_upsert_add_failed"
            ),
            "message": "The RSS update needs manual verification.",
            "retryable": classified.retryable,
            "old_resource_id": old_resource_id,
            "compensation_status": compensation_status,
        }

    @staticmethod
    def _field(value: Any, field_name: str) -> str:
        if isinstance(value, dict):
            field = value.get(field_name)
        else:
            field = getattr(value, field_name, None)
        return field if isinstance(field, str) else ""

    @classmethod
    def _resource_id(cls, value: Any, fallback: str) -> str:
        return cls._field(value, "uid") or fallback

    @classmethod
    def _classify(cls, error: Exception) -> QBServiceError:
        if isinstance(error, getattr(qbittorrentapi, "LoginFailed")):
            return QBServiceError(
                "qb_authentication_failed",
                "qBittorrent authentication failed.",
                status_code=401,
            )
        if isinstance(error, getattr(qbittorrentapi, "APIConnectionError")):
            return QBServiceError(
                "qb_connection_error",
                "qBittorrent is temporarily unavailable.",
                status_code=503,
                retryable=True,
            )
        if isinstance(error, getattr(qbittorrentapi, "HTTP4XXError")):
            return QBServiceError(
                "qb_request_rejected",
                "qBittorrent rejected the request.",
            )
        if isinstance(error, getattr(qbittorrentapi, "HTTP5XXError")):
            return QBServiceError(
                "qb_server_error",
                "qBittorrent returned a server error.",
            )
        return QBServiceError(
            "qb_operation_failed",
            "qBittorrent operation failed.",
        )

    @classmethod
    def _raise_safe(cls, error: Exception, operation: str) -> None:
        safe_error = cls._classify(error)
        logger.error("qB operation failed: %s", operation)
        raise safe_error from error

    @staticmethod
    def _attention_result(
        *,
        error_code: str,
        message: str,
        old_resource_id: str,
        retryable: bool,
    ) -> dict[str, Any]:
        return {
            "status": "attention_required",
            "error_code": error_code,
            "message": message,
            "retryable": retryable,
            "old_resource_id": old_resource_id,
            "compensation_status": "not_attempted",
        }
