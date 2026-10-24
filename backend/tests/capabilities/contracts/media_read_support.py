"""Trusted Runtime composition and SDK transport doubles for media read tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
from typing import Any
from uuid import uuid4

import pytest
from unittest.mock import create_autospec

from app.capabilities.factory import build_capability_registry
from app.core.config import settings
from app.harness.budget import CancellationToken, RunBudget
from app.harness.contracts import AgentDecision, ExecutionContext
from app.harness.execution import build_runtime
from app.harness.model_gateway import ModelGateway
from app.models import User
from app.schemas.user import UserRead

READ_ACTIONS = frozenset({"library_status", "list_rss_feeds", "list_rss_rules"})
MEDIA_PRIVATE = "media-read-contract-provider-private-sentinel"


def _default_rule(feed_url: str) -> dict[str, Any]:
    return {
        "addPaused": False,
        "affectedFeeds": [feed_url],
        "assignedCategory": "anime",
        "enabled": True,
        "episodeFilter": "S01E[0-9]+",
        "ignoreDays": 0,
        "lastMatch": "2026-01-01T00:00:00Z",
        "mustContain": "Synthetic Anime",
        "mustNotContain": "spoiler",
        "previouslyMatchedEpisodes": ["S01E01"],
        "priority": 1,
        "savePath": "anime",
        "smartFilter": False,
        "torrentContentLayout": None,
        "torrentParams": {
            "category": "anime",
            "content_layout": None,
            "download_limit": 0,
            "download_path": "anime",
            "inactive_seeding_time_limit": 0,
            "operating_mode": "auto",
            "ratio_limit": -1,
            "save_path": "anime",
            "seeding_time_limit": -1,
            "share_limit_action": "default",
            "skip_checking": False,
            "ssl_certificate": "",
            "ssl_dh_params": "",
            "ssl_private_key": MEDIA_PRIVATE,
            "tags": ["synthetic"],
            "upload_limit": 0,
            "use_auto_tmm": True,
            "stop_condition": None,
        },
        "useRegex": False,
    }


class SyntheticQBClient:
    """Only the real QBService's login and two read calls are implemented."""

    _WRITE_METHODS = frozenset(
        {
            "rss_add_feed",
            "rss_remove_item",
            "rss_set_rule",
            "rss_remove_rule",
        }
    )

    def __init__(self) -> None:
        feed_url = "https://feeds.synthetic.invalid/rss.xml?category=anime"
        self.feeds: dict[str, Any] = {
            "global-feed": {"uid": "media-feed-1", "url": feed_url}
        }
        self.rules: dict[str, Any] = {"global-rule": _default_rule(feed_url)}
        self.failures: dict[str, Exception] = {}
        self.calls: list[str] = []
        self.write_calls = 0
        self._lock = threading.Lock()
        self._blocked_method: str | None = None
        self._late_results: dict[str, Any] = {}
        self.entered = {name: threading.Event() for name in ("rss_items", "rss_rules")}
        self.release = {name: threading.Event() for name in ("rss_items", "rss_rules")}
        self.finished = {name: threading.Event() for name in ("rss_items", "rss_rules")}

    def auth_log_in(self) -> None:
        with self._lock:
            self.calls.append("auth_log_in")

    def rss_items(self) -> Any:
        return self._read("rss_items")

    def rss_rules(self) -> Any:
        return self._read("rss_rules")

    def _read(self, method: str) -> Any:
        with self._lock:
            self.calls.append(method)
            is_blocked = self._blocked_method == method
            failure = self.failures.get(method)
            payload = deepcopy(self.feeds if method == "rss_items" else self.rules)

        if is_blocked:
            self.entered[method].set()
            try:
                if not self.release[method].wait(timeout=10):
                    raise AssertionError("Timed media SDK fixture was not released")
                payload = deepcopy(self._late_results[method])
            finally:
                self.finished[method].set()
        if failure is not None:
            raise failure
        return payload

    def block_read(self, method: str, late_result: Any) -> None:
        self._blocked_method = method
        self._late_results[method] = deepcopy(late_result)
        self.entered[method].clear()
        self.release[method].clear()
        self.finished[method].clear()

    def unblock_read(self) -> None:
        self._blocked_method = None

    def __getattr__(self, name: str) -> Any:
        if name in self._WRITE_METHODS:

            def forbidden_write(*args: Any, **kwargs: Any) -> None:
                with self._lock:
                    self.write_calls += 1
                raise AssertionError("A media read called a qBittorrent write")

            return forbidden_write
        raise AssertionError(f"Unexpected qBittorrent SDK operation: {name}")


class SyntheticQBClientFactory:
    """Replaces only the provider SDK constructor; QBService stays real."""

    def __init__(self, client: SyntheticQBClient) -> None:
        self.client = client
        self.constructor_calls = 0
        self.constructor_fields: list[frozenset[str]] = []

    def __call__(self, **kwargs: Any) -> SyntheticQBClient:
        self.constructor_calls += 1
        self.constructor_fields.append(frozenset(kwargs))
        return self.client


def configure_qb_settings(
    monkeypatch: Any,
    *,
    allowed_user_ids: str = "1,2",
    enabled: bool = True,
    host: str = "https://qbittorrent.synthetic.invalid",
    username: str = "media-contract-user",
) -> None:
    """Use ordinary Settings values with synthetic provider configuration."""
    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", enabled)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", allowed_user_ids)
    monkeypatch.setattr(settings, "QB_HOST", host)
    monkeypatch.setattr(settings, "QB_USERNAME", username)
    monkeypatch.setattr(settings, "QB_PASSWORD", "media-contract-password")


def make_media_sdk(
    monkeypatch: Any,
) -> tuple[SyntheticQBClient, SyntheticQBClientFactory]:
    import qbittorrentapi

    client = SyntheticQBClient()
    factory = SyntheticQBClientFactory(client)
    configure_qb_settings(monkeypatch)
    monkeypatch.setattr(qbittorrentapi, "Client", factory)
    return client, factory


def media_read_parameters(scenario: str) -> list[Any]:
    """Freeze the three registered, non-side-effect media reads per scenario."""
    registry = build_capability_registry()
    descriptors = {}
    for descriptor in registry.list_actions():
        public_name = descriptor.public_name or descriptor.name
        owner = registry.find_action(public_name)
        if owner is None or owner[0].name != "media" or owner[1].is_side_effect:
            continue
        key = (public_name, owner[1].version)
        descriptors[key] = owner[1]

    expected = {(name, "v1") for name in READ_ACTIONS}
    assert set(descriptors) == expected
    assert all(not descriptors[key].is_side_effect for key in expected)
    assert descriptors[("library_status", "v1")].requires_auth is False
    assert all(
        descriptors[(name, "v1")].requires_auth
        for name in ("list_rss_feeds", "list_rss_rules")
    )
    return [
        pytest.param(
            key,
            id=f"{key[0]}@{key[1]}-{scenario}",
            marks=pytest.mark.capability_contract(*key, scenario),
        )
        for key in sorted(expected)
    ]


@dataclass
class MediaReadExecution:
    key: tuple[str, str]
    descriptor: Any
    capability: Any
    registry: Any
    runtime: Any
    dispatcher: Any
    user: UserRead
    other_user: UserRead
    gateway: Any
    client: SyntheticQBClient
    client_factory: SyntheticQBClientFactory

    def context_for(
        self,
        principal_id: Any = ...,
        *,
        action: str | None = None,
    ) -> ExecutionContext:
        if principal_id is ...:
            principal_id = self.user.id
        name = action or self.key[0]
        values = {
            "principal_id": principal_id,
            "run_id": "media-read-run-" + uuid4().hex,
            "trace_id": "media-read-trace-" + uuid4().hex,
            "capability_allowlist": frozenset({name}),
        }
        if principal_id is None or type(principal_id) is int:
            return ExecutionContext(**values)
        # Model-construct only hostile trusted-context types that normal request
        # validation would reject/coerce before they reach this Dispatcher test.
        return ExecutionContext.model_construct(**values)

    async def dispatch(
        self,
        action: str | None = None,
        arguments: dict[str, Any] | None = None,
        *,
        context: ExecutionContext | None = None,
        version: str | None = None,
        budget: RunBudget | None = None,
        cancellation: CancellationToken | None = None,
        forged_decision: bool = False,
    ):
        name = action or self.key[0]
        current = context or self.context_for(action=name)
        decision_id = uuid4().hex
        decision_version = version or self.key[1]
        decision_arguments = deepcopy(arguments or {})
        if forged_decision:
            decision = AgentDecision.model_construct(
                decision_id=decision_id,
                run_id=current.run_id,
                action="invoke",
                capability=name,
                capability_version=decision_version,
                arguments=decision_arguments,
            )
        else:
            decision = AgentDecision(
                decision_id=decision_id,
                run_id=current.run_id,
                action="invoke",
                capability=name,
                capability_version=decision_version,
                arguments=decision_arguments,
            )
        return await self.dispatcher.dispatch(
            decision,
            current,
            budget=budget,
            cancellation=cancellation,
        )


async def make_media_read_execution(
    key: tuple[str, str],
    db: Any,
    client: SyntheticQBClient,
    client_factory: SyntheticQBClientFactory,
) -> MediaReadExecution:
    """Compose the production Registry, Runtime, Dispatcher, and Adapter."""
    registry = build_capability_registry()
    owner = registry.find_action(key[0])
    assert owner is not None and owner[0].name == "media"
    capability, descriptor = owner
    assert descriptor.version == key[1] and not descriptor.is_side_effect

    suffix = uuid4().hex[:16]
    owner_model = User(username=f"media-read-owner-{suffix}")
    other_model = User(username=f"media-read-other-{suffix}")
    db.add_all([owner_model, other_model])
    await db.flush()
    assert owner_model.id is not None and other_model.id is not None
    await db.commit()
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    owner_user = UserRead(
        id=owner_model.id,
        username=owner_model.username,
        bangumi_name=owner_model.bangumi_name,
        created_at=created_at,
    )
    other_user = UserRead(
        id=other_model.id,
        username=other_model.username,
        bangumi_name=other_model.bangumi_name,
        created_at=created_at,
    )

    gateway = create_autospec(ModelGateway, instance=True)
    for method in ("infer", "stream_infer", "synthesize", "synthesize_result"):
        getattr(gateway, method).side_effect = AssertionError(
            "Media handler contracts must not call a model"
        )
    runtime = build_runtime(
        session=db,
        user=owner_user,
        registry=registry,
        model_gateway=gateway,
        trace_store=None,
        durable=False,
    )
    assert runtime.dispatcher is not None
    return MediaReadExecution(
        key,
        descriptor,
        capability,
        registry,
        runtime,
        runtime.dispatcher,
        owner_user,
        other_user,
        gateway,
        client,
        client_factory,
    )


def sdk_method(action: str) -> str:
    if action == "list_rss_feeds":
        return "rss_items"
    if action == "list_rss_rules":
        return "rss_rules"
    raise ValueError(f"No qBittorrent read method for {action}")


def assert_no_model_calls(execution: MediaReadExecution) -> None:
    for method in ("infer", "stream_infer", "synthesize", "synthesize_result"):
        assert getattr(execution.gateway, method).call_count == 0
