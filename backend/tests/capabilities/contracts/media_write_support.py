"""Trusted Runtime composition and SDK transport doubles for media writes."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
from typing import Any
from unittest.mock import create_autospec
from uuid import uuid4

import pytest

from app.capabilities.factory import build_capability_registry
from app.capabilities.media_write_contracts import WRITE_ACTIONS
from app.core.config import settings
from app.harness.budget import CancellationToken
from app.harness.contracts import AgentDecision, ExecutionContext
from app.harness.execution import build_runtime
from app.harness.model_gateway import ModelGateway
from app.harness.policy import Approval
from app.models import User
from app.schemas.user import UserRead

SCENARIOS = (
    "media_write_error",
    "media_write_timeout",
    "media_write_isolation",
    "media_write_serialization",
    "media_write_authorization",
    "media_write_dispatcher",
    "media_write_approval",
    "media_write_idempotency",
    "media_write_recovery",
)

MEDIA_PRIVATE = "media-write-private-provider-sentinel"
FEED_URL = "https://feeds.synthetic.invalid/contract.xml?category=anime"


def default_rule(feed_url: str = FEED_URL) -> dict[str, Any]:
    """Use every real RssRule/TorrentParams field, including a secret sentinel."""
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


def media_write_parameters(scenario: str) -> list[Any]:
    """Freeze the five registered, high-risk media write actions per scenario."""
    registry = build_capability_registry()
    descriptors: dict[tuple[str, str], Any] = {}
    for descriptor in registry.list_actions():
        public_name = descriptor.public_name or descriptor.name
        owner = registry.find_action(public_name)
        if owner is None or owner[0].name != "media" or not owner[1].is_side_effect:
            continue
        descriptors[(public_name, owner[1].version)] = owner[1]

    expected = {(name, "v1") for name in WRITE_ACTIONS}
    assert set(descriptors) == expected
    assert len(expected) == 5
    assert all(descriptors[key].requires_auth for key in expected)
    assert all(descriptors[key].is_side_effect for key in expected)
    assert all(descriptors[key].approval_required for key in expected)
    assert all(descriptors[key].idempotency_mode == "required" for key in expected)
    assert all(descriptors[key].risk_level == "high" for key in expected)
    assert all(descriptors[key].output_schema for key in expected)

    assert scenario in SCENARIOS
    return [
        pytest.param(
            key,
            id=f"{key[0]}@{key[1]}-{scenario}",
            marks=pytest.mark.capability_contract(*key, scenario),
        )
        for key in sorted(expected)
    ]


def arguments_for(action: str) -> dict[str, Any]:
    """Synthetic public input for each frozen media write contract."""
    if action == "add_rss_feed":
        return {"url": FEED_URL, "name": "contract-add"}
    if action == "upsert_rss_feed":
        return {
            "url": "https://feeds.synthetic.invalid/replaced.xml",
            "name": "contract-upsert",
        }
    if action == "remove_rss_feed":
        return {"item_path": "contract-remove-feed"}
    if action == "set_rss_rule":
        return {"rule_name": "contract-set-rule", "rule": default_rule()}
    if action == "remove_rss_rule":
        return {"rule_name": "contract-remove-rule"}
    raise ValueError(f"Unexpected Media write action: {action}")


_WRITE_METHODS = frozenset(
    {"rss_add_feed", "rss_remove_item", "rss_set_rule", "rss_remove_rule"}
)


class SyntheticQBClient:
    """Small mutable qB endpoint with call auditing and controllable writes."""

    def __init__(self) -> None:
        self.feeds: dict[str, Any] = {
            "contract-upsert": {
                "uid": "media-upsert-feed",
                "url": "https://feeds.synthetic.invalid/old.xml",
            },
            "contract-remove-feed": {
                "uid": "media-remove-feed",
                "url": "https://feeds.synthetic.invalid/remove.xml",
            },
        }
        self.rules: dict[str, Any] = {
            "contract-remove-rule": default_rule(),
        }
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.failures: dict[str, Exception] = {}
        self._lock = threading.Lock()
        self._blocked_method: str | None = None
        self._completed_block_method: str | None = None
        self.after_block_read = threading.Event()
        self.entered = {name: threading.Event() for name in _WRITE_METHODS}
        self.release = {name: threading.Event() for name in _WRITE_METHODS}
        self.finished = {name: threading.Event() for name in _WRITE_METHODS}

    @property
    def write_calls(self) -> int:
        return sum(method in _WRITE_METHODS for method, _ in self.calls)

    def calls_for(self, method: str) -> list[dict[str, Any]]:
        with self._lock:
            return [deepcopy(args) for name, args in self.calls if name == method]

    def auth_log_in(self) -> None:
        self._read_or_auth_call("auth_log_in", {})

    def rss_items(self, **kwargs: Any) -> dict[str, Any]:
        self._read_or_auth_call("rss_items", kwargs)
        with self._lock:
            result = deepcopy(self.feeds)
            completed_write = self._completed_block_method
        if completed_write == "rss_add_feed":
            self.after_block_read.set()
        return result

    def rss_rules(self, **kwargs: Any) -> dict[str, Any]:
        self._read_or_auth_call("rss_rules", kwargs)
        with self._lock:
            return deepcopy(self.rules)

    def rss_add_feed(self, *, url: str, item_path: str | None = None) -> None:
        args = {"url": url, "item_path": item_path}

        def update() -> None:
            name = item_path or url
            self.feeds[name] = {"uid": f"feed-{name}", "url": url}

        self._write("rss_add_feed", args, update)

    def rss_remove_item(self, *, item_path: str) -> None:
        self._write(
            "rss_remove_item",
            {"item_path": item_path},
            lambda: self.feeds.pop(item_path, None),
        )

    def rss_set_rule(self, *, rule_name: str, rule_def: dict[str, Any]) -> None:
        self._write(
            "rss_set_rule",
            {"rule_name": rule_name, "rule_def": rule_def},
            lambda: self.rules.__setitem__(rule_name, deepcopy(rule_def)),
        )

    def rss_remove_rule(self, *, rule_name: str) -> None:
        self._write(
            "rss_remove_rule",
            {"rule_name": rule_name},
            lambda: self.rules.pop(rule_name, None),
        )

    def _read_or_auth_call(self, method: str, arguments: dict[str, Any]) -> None:
        with self._lock:
            self.calls.append((method, deepcopy(arguments)))
            failure = self.failures.get(method)
        if failure is not None:
            raise failure

    def _write(self, method: str, arguments: dict[str, Any], mutate: Any) -> None:
        with self._lock:
            self.calls.append((method, deepcopy(arguments)))
            failure = self.failures.get(method)
            if failure is not None:
                raise failure
            mutate()
            should_block = self._blocked_method == method
            if should_block:
                # Mark entry under the same lock used by cleanup to disable a
                # pending block, closing the start-versus-release race.
                self.entered[method].set()
        if should_block:
            try:
                if not self.release[method].wait(timeout=10):
                    raise AssertionError("Timed media SDK fixture was not released")
            finally:
                with self._lock:
                    self._completed_block_method = method
                self.finished[method].set()

    def block_write(self, method: str) -> None:
        assert method in _WRITE_METHODS
        with self._lock:
            self._blocked_method = method
            self._completed_block_method = None
            self.after_block_read.clear()
            self.entered[method].clear()
            self.release[method].clear()
            self.finished[method].clear()

    def unblock_write(self) -> None:
        with self._lock:
            self._blocked_method = None

    def release_and_join_writes(self, *, verify_upsert: bool = False) -> None:
        """Always release blocked SDK calls and join their worker threads."""
        with self._lock:
            self._blocked_method = None
            for release in self.release.values():
                release.set()
            entered_methods = [
                method for method in _WRITE_METHODS if self.entered[method].is_set()
            ]
        for method in entered_methods:
            assert self.finished[method].wait(timeout=10), (
                f"Timed media SDK worker did not finish: {method}"
            )
            if verify_upsert and method == "rss_add_feed":
                assert self.after_block_read.wait(timeout=10), (
                    "Timed upsert worker did not finish its verification read"
                )

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"Unexpected qBittorrent SDK operation: {name}")


class SyntheticQBClientFactory:
    """Replace only the provider SDK constructor; QBService remains real."""

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
    allowed_user_ids: str,
    enabled: bool = True,
) -> None:
    """Use synthetic qB configuration without reading real credentials."""
    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", enabled)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", allowed_user_ids)
    monkeypatch.setattr(settings, "QB_HOST", "https://qbittorrent.synthetic.invalid")
    monkeypatch.setattr(settings, "QB_USERNAME", "media-write-contract-user")
    monkeypatch.setattr(settings, "QB_PASSWORD", "media-write-contract-password")


def install_synthetic_qb_sdk(
    monkeypatch: Any,
    *,
    allowed_user_ids: str,
    enabled: bool = True,
) -> tuple[SyntheticQBClient, SyntheticQBClientFactory]:
    import qbittorrentapi

    client = SyntheticQBClient()
    factory = SyntheticQBClientFactory(client)
    configure_qb_settings(
        monkeypatch, allowed_user_ids=allowed_user_ids, enabled=enabled
    )
    monkeypatch.setattr(qbittorrentapi, "Client", factory)
    return client, factory


@dataclass
class MediaWriteExecution:
    key: tuple[str, str]
    db: Any
    user: UserRead
    other_user: UserRead
    registry: Any
    capability: Any
    descriptor: Any
    model_gateway: Any
    dispatcher: Any
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
            "run_id": "media-write-run-" + uuid4().hex,
            "trace_id": "media-write-trace-" + uuid4().hex,
            "capability_allowlist": frozenset({name}),
        }
        if principal_id is None or type(principal_id) is int:
            return ExecutionContext(**values)
        return ExecutionContext.model_construct(**values)

    def make_dispatcher(
        self,
        *,
        action: str | None = None,
        db: Any | None = None,
        user: UserRead | None = None,
        authenticated: bool = True,
        durable: bool = True,
        allow_side_effects: bool = True,
        approval: Approval | None = None,
        use_default_approval: bool = True,
    ) -> Any:
        target_action = action or self.key[0]
        session = db or self.db
        principal = (user or self.user) if authenticated else None
        if use_default_approval:
            action_approval = (
                Approval(
                    approval_id=uuid4().hex,
                    principal_id=principal.id,
                    action=target_action,
                )
                if principal is not None
                else None
            )
        else:
            action_approval = approval
        runtime = build_runtime(
            session=session,
            user=principal,
            registry=self.registry,
            model_gateway=self.model_gateway,
            trace_store=None,
            durable=durable,
            allow_side_effects=allow_side_effects,
            approval=action_approval,
        )
        assert runtime.dispatcher is not None
        return runtime.dispatcher

    async def dispatch(
        self,
        arguments: dict[str, Any] | None = None,
        *,
        action: str | None = None,
        context: ExecutionContext | None = None,
        dispatcher: Any | None = None,
        version: str | None = None,
        idempotency_key: str | None = None,
        include_key: bool = True,
        cancellation: CancellationToken | None = None,
    ):
        target_action = action or self.key[0]
        owner = self.registry.find_action(target_action)
        assert owner is not None and owner[0].name == "media"
        current = context or self.context_for(action=target_action)
        public_arguments = deepcopy(
            arguments if arguments is not None else arguments_for(target_action)
        )
        if include_key:
            public_arguments["idempotency_key"] = idempotency_key or uuid4().hex
        else:
            public_arguments.pop("idempotency_key", None)
        decision = AgentDecision(
            decision_id=uuid4().hex,
            run_id=current.run_id,
            action="invoke",
            capability=target_action,
            capability_version=version or owner[1].version,
            arguments=public_arguments,
        )
        return await (dispatcher or self.dispatcher).dispatch(
            decision,
            current,
            cancellation=cancellation,
        )


async def make_write_execution(
    key: tuple[str, str], db: Any, monkeypatch: Any
) -> MediaWriteExecution:
    """Compose the production Registry, Runtime, Dispatcher, and SQL store."""
    suffix = uuid4().hex[:12]
    owner_model = User(username=f"media-write-owner-{suffix}")
    other_model = User(username=f"media-write-other-{suffix}")
    db.add_all([owner_model, other_model])
    await db.flush()
    assert owner_model.id is not None and other_model.id is not None
    await db.commit()

    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    owner = UserRead(
        id=owner_model.id,
        username=owner_model.username,
        bangumi_name=owner_model.bangumi_name,
        created_at=created_at,
    )
    other = UserRead(
        id=other_model.id,
        username=other_model.username,
        bangumi_name=other_model.bangumi_name,
        created_at=created_at,
    )

    client, client_factory = install_synthetic_qb_sdk(
        monkeypatch,
        allowed_user_ids=f"{owner.id},{other.id}",
    )
    registry = build_capability_registry()
    owner_action = registry.find_action(key[0])
    assert owner_action is not None and owner_action[0].name == "media"
    capability, descriptor = owner_action
    assert descriptor.version == key[1] and descriptor.is_side_effect

    gateway = create_autospec(ModelGateway, instance=True)
    for method in ("infer", "stream_infer", "synthesize", "synthesize_result"):
        getattr(gateway, method).side_effect = AssertionError(
            "Media write handler contracts must not call a model"
        )

    execution = MediaWriteExecution(
        key=key,
        db=db,
        user=owner,
        other_user=other,
        registry=registry,
        capability=capability,
        descriptor=descriptor,
        model_gateway=gateway,
        dispatcher=None,
        client=client,
        client_factory=client_factory,
    )
    execution.dispatcher = execution.make_dispatcher()
    return execution


def sdk_method(action: str) -> str:
    methods = {
        "add_rss_feed": "rss_add_feed",
        "upsert_rss_feed": "rss_add_feed",
        "remove_rss_feed": "rss_remove_item",
        "set_rss_rule": "rss_set_rule",
        "remove_rss_rule": "rss_remove_rule",
    }
    try:
        return methods[action]
    except KeyError as error:
        raise ValueError(f"No qBittorrent write method for {action}") from error


def assert_no_model_calls(execution: MediaWriteExecution) -> None:
    for method in ("infer", "stream_infer", "synthesize", "synthesize_result"):
        assert getattr(execution.model_gateway, method).call_count == 0
