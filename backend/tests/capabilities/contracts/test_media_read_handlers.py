"""Real Runtime/Dispatcher observations for Media's frozen read actions."""

from __future__ import annotations

import asyncio
import json
import logging
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

import pytest

from app.capabilities.types import ActionDescriptor
from app.harness.budget import CancellationToken, RunBudget
from tests.capabilities.contracts.media_read_support import (
    MEDIA_PRIVATE,
    assert_no_model_calls,
    configure_qb_settings,
    make_media_sdk,
    make_media_read_execution,
    media_read_parameters,
    sdk_method,
)
from tests.capabilities.contracts.plugin import record


@pytest.fixture
def media_sdk(monkeypatch: Any) -> tuple[Any, Any]:
    return make_media_sdk(monkeypatch)


def _wire(result: Any) -> str:
    return json.dumps(result.model_dump(mode="json"), allow_nan=False)


def _assert_safe_common_read(result: Any, action: str) -> None:
    assert result.status == "succeeded"
    assert result.capability == action
    assert result.capability_version == "v1"
    assert result.error_code is None
    assert result.output["success"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("key", media_read_parameters("media_read_error"))
async def test_media_read_error_observation(
    key, db_session, media_sdk, monkeypatch, caplog, request
):
    import qbittorrentapi

    client, factory = media_sdk
    execution = await make_media_read_execution(key, db_session, client, factory)
    action = key[0]

    if action == "library_status":
        # Configuration status is local. Even a configured provider transport
        # failure cannot cause it to construct or probe the SDK client.
        client.failures["rss_items"] = qbittorrentapi.APIConnectionError(MEDIA_PRIVATE)
        result = await execution.dispatch(
            context=execution.context_for(None, action=action)
        )
        _assert_safe_common_read(result, action)
        assert result.output["configured"] is True
        assert result.output["provider"] == "qbittorrent"
        assert factory.constructor_calls == 0
        assert client.calls == []
    else:
        method = sdk_method(action)
        client.failures[method] = qbittorrentapi.APIConnectionError(MEDIA_PRIVATE)
        with caplog.at_level(logging.ERROR):
            result = await execution.dispatch()

        assert result.status == "failed"
        assert result.error_code == "qb_connection_error"
        # The registered reads declare no retry class, so Dispatcher suppresses
        # retryability even when QBService classifies the provider error as transient.
        assert result.retryable is False
        assert "Capability execution failed" in result.output["message"]
        assert MEDIA_PRIVATE not in _wire(result)
        assert MEDIA_PRIVATE not in caplog.text
        assert all(item.exc_info is None for item in caplog.records)
        assert factory.constructor_calls == 1
        assert factory.constructor_fields == [
            frozenset({"host", "username", "password"})
        ]
        assert client.calls == ["auth_log_in", method]

    assert client.write_calls == 0
    assert_no_model_calls(execution)
    record(request, key, "media_read_error")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", media_read_parameters("media_read_timeout"))
async def test_media_read_timeout_observation(
    key, db_session, media_sdk, monkeypatch, request
):
    client, factory = media_sdk
    execution = await make_media_read_execution(key, db_session, client, factory)
    action = key[0]

    if action == "library_status":
        started = monotonic()
        result = await asyncio.wait_for(
            execution.dispatch(context=execution.context_for(None, action=action)),
            timeout=2.0,
        )
        assert monotonic() - started < 2.0
        _assert_safe_common_read(result, action)
        assert result.output["configured"] is True
        assert result.output["provider"] == "qbittorrent"

        denied = await execution.dispatch(
            context=execution.context_for(None, action=action),
            budget=RunBudget(max_tool_calls=0),
        )
        assert denied.status == "denied" and denied.error_code == "budget_exceeded"

        cancellation = CancellationToken()
        cancellation.cancel()
        cancelled = await execution.dispatch(
            context=execution.context_for(None, action=action),
            cancellation=cancellation,
        )
        assert cancelled.status == "cancelled" and cancelled.error_code == "cancelled"
        assert factory.constructor_calls == 0
        assert client.calls == []
    else:
        method = sdk_method(action)
        late_result = (
            {
                "late-global-feed": {
                    "uid": "late-feed",
                    "url": "https://late.invalid/rss",
                }
            }
            if action == "list_rss_feeds"
            else {"late-global-rule": {"enabled": True, "mustContain": "late-only"}}
        )
        client.block_read(method, late_result)
        controls = execution.dispatcher._run_with_controls

        async def armed_controls(operation, _timeout_seconds, cancellation):
            task = asyncio.ensure_future(operation)
            try:
                entered = await asyncio.wait_for(
                    asyncio.to_thread(client.entered[method].wait, 5.0), timeout=6.0
                )
                assert entered, "SDK read did not enter its blocking transport"
                # Start the injected deadline only after the synchronous SDK
                # call is active; Runtime/Dispatcher setup time is outside it.
                return await controls(task, 0.05, cancellation)
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        monkeypatch.setattr(execution.dispatcher, "_run_with_controls", armed_controls)
        original_timeout = execution.descriptor.timeout_seconds
        try:
            timed_out = await execution.dispatch()
            frozen_result = _wire(timed_out)
            assert timed_out.status == "timeout"
            assert timed_out.error_code == "timeout"
            assert client.entered[method].is_set()
            assert not client.finished[method].is_set()
            assert execution.descriptor.timeout_seconds == original_timeout

            # A cancelled asyncio wrapper cannot stop the synchronous SDK
            # thread. Release and join it before another principal reads.
            client.release[method].set()
            assert await asyncio.to_thread(client.finished[method].wait, 5.0)
            client.unblock_read()
            monkeypatch.setattr(execution.dispatcher, "_run_with_controls", controls)

            next_action = (
                "list_rss_rules" if action == "list_rss_feeds" else "list_rss_feeds"
            )
            next_context = execution.context_for(
                execution.other_user.id, action=next_action
            )
            healthy = await execution.dispatch(next_action, context=next_context)
            _assert_safe_common_read(healthy, next_action)
            if next_action == "list_rss_feeds":
                assert "global-feed" in healthy.output["feeds"]
                assert "late-global-feed" not in healthy.output["feeds"]
            else:
                assert "global-rule" in healthy.output["rules"]
                assert "late-global-rule" not in healthy.output["rules"]
            assert timed_out.invocation_id != healthy.invocation_id
            assert timed_out.run_id != healthy.run_id
            assert timed_out.trace_id != healthy.trace_id
            assert _wire(timed_out) == frozen_result
            invocation_events = [
                event
                for event in execution.dispatcher.events
                if event.invocation_id == timed_out.invocation_id
            ]
            assert [event.event_type for event in invocation_events] == [
                "invocation_start",
                "invocation_end",
            ]
            assert invocation_events[-1].payload["status"] == "timeout"
            assert client.write_calls == 0
        finally:
            client.release[method].set()
            if client.entered[method].is_set():
                await asyncio.to_thread(client.finished[method].wait, 5.0)

        # Exercise active cancellation independently from the timeout above.
        # The watcher only cancels after the real synchronous SDK read enters.
        client.block_read(method, late_result)
        active_cancellation = CancellationToken()

        async def cancel_after_sdk_entry():
            entered = await asyncio.wait_for(
                asyncio.to_thread(client.entered[method].wait, 5.0), timeout=6.0
            )
            assert entered, "SDK read did not enter before active cancellation"
            active_cancellation.cancel()

        cancellation_task = asyncio.create_task(cancel_after_sdk_entry())
        try:
            cancelled = await execution.dispatch(
                context=execution.context_for(execution.user.id, action=action),
                cancellation=active_cancellation,
            )
            await cancellation_task
            frozen_cancelled = _wire(cancelled)
            assert cancelled.status == "cancelled"
            assert cancelled.error_code == "cancelled"
            assert client.entered[method].is_set()
            assert not client.finished[method].is_set()
            cancelled_events = [
                event
                for event in execution.dispatcher.events
                if event.invocation_id == cancelled.invocation_id
            ]
            assert [event.event_type for event in cancelled_events] == [
                "invocation_start",
                "invocation_end",
            ]
            assert cancelled_events[-1].payload["status"] == "cancelled"

            # Cancellation stops the invocation, not the underlying SDK thread.
            # Join that thread before a different principal starts another read.
            client.release[method].set()
            assert await asyncio.to_thread(client.finished[method].wait, 5.0)
            client.unblock_read()
            assert _wire(cancelled) == frozen_cancelled

            next_action = (
                "list_rss_rules" if action == "list_rss_feeds" else "list_rss_feeds"
            )
            healthy = await execution.dispatch(
                next_action,
                context=execution.context_for(
                    execution.other_user.id, action=next_action
                ),
            )
            _assert_safe_common_read(healthy, next_action)
            if next_action == "list_rss_feeds":
                assert "global-feed" in healthy.output["feeds"]
                assert "late-global-feed" not in healthy.output["feeds"]
            else:
                assert "global-rule" in healthy.output["rules"]
                assert "late-global-rule" not in healthy.output["rules"]
            assert cancelled.invocation_id != healthy.invocation_id
            assert cancelled.run_id != healthy.run_id
            assert cancelled.trace_id != healthy.trace_id
            assert _wire(cancelled) == frozen_cancelled
            cancelled_events_after_join = [
                event
                for event in execution.dispatcher.events
                if event.invocation_id == cancelled.invocation_id
            ]
            assert [event.event_type for event in cancelled_events_after_join] == [
                "invocation_start",
                "invocation_end",
            ]
            assert client.write_calls == 0
        finally:
            active_cancellation.cancel()
            client.release[method].set()
            if client.entered[method].is_set():
                finished = await asyncio.to_thread(client.finished[method].wait, 5.0)
                assert finished, "Blocked SDK read failed to finish after release"
            client.unblock_read()
            if not cancellation_task.done():
                cancellation_task.cancel()
            await asyncio.gather(cancellation_task, return_exceptions=True)

    assert_no_model_calls(execution)
    record(request, key, "media_read_timeout")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", media_read_parameters("media_read_isolation"))
async def test_media_read_isolation_observation(
    key, db_session, media_sdk, monkeypatch, request
):
    client, factory = media_sdk
    execution = await make_media_read_execution(key, db_session, client, factory)
    action = key[0]

    if action == "library_status":
        client.failures["rss_items"] = RuntimeError(MEDIA_PRIVATE)
        failed = await execution.dispatch(
            "list_rss_feeds",
            context=execution.context_for(execution.user.id, action="list_rss_feeds"),
        )
        assert failed.status == "failed"
        assert failed.error_code == "qb_operation_failed"
        assert MEDIA_PRIVATE not in _wire(failed)
        client.failures.clear()
        constructors_before_status = factory.constructor_calls

        status = await execution.dispatch(
            context=execution.context_for(None, action="library_status")
        )
        _assert_safe_common_read(status, "library_status")
        assert status.output["configured"] is True
        assert factory.constructor_calls == constructors_before_status
        assert failed.run_id != status.run_id
        assert failed.trace_id != status.trace_id
    else:
        method = sdk_method(action)
        client.failures[method] = RuntimeError(MEDIA_PRIVATE)
        failed = await execution.dispatch(
            context=execution.context_for(execution.user.id, action=action)
        )
        assert failed.status == "failed"
        assert failed.error_code == "qb_operation_failed"
        assert failed.retryable is False
        assert MEDIA_PRIVATE not in _wire(failed)
        client.failures.clear()

        next_action = (
            "list_rss_rules" if action == "list_rss_feeds" else "list_rss_feeds"
        )
        healthy = await execution.dispatch(
            next_action,
            context=execution.context_for(execution.other_user.id, action=next_action),
        )
        _assert_safe_common_read(healthy, next_action)
        assert failed.run_id != healthy.run_id
        assert failed.trace_id != healthy.trace_id
        if next_action == "list_rss_feeds":
            assert healthy.output["feeds"]["global-feed"]["uid"] == "media-feed-1"
        else:
            assert (
                healthy.output["rules"]["global-rule"]["mustContain"]
                == "Synthetic Anime"
            )
        assert len(factory.constructor_fields) == 2

    assert client.write_calls == 0
    assert_no_model_calls(execution)
    record(request, key, "media_read_isolation")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", media_read_parameters("media_read_serialization"))
async def test_media_read_serialization_observation(
    key, db_session, media_sdk, monkeypatch, request
):
    client, factory = media_sdk
    execution = await make_media_read_execution(key, db_session, client, factory)
    action = key[0]

    if action == "library_status":
        result = await execution.dispatch(
            context=execution.context_for(None, action=action)
        )
        _assert_safe_common_read(result, action)
        assert result.output["configured"] is True
        assert result.output["provider"] == "qbittorrent"
        assert factory.constructor_calls == 0
        assert MEDIA_PRIVATE not in _wire(result)
    else:
        from tests.capabilities.contracts.media_read_support import _default_rule

        secret_url = (
            f"https://media-user:{MEDIA_PRIVATE}@example.invalid/rss.xml"
            f"?passkey={MEDIA_PRIVATE}&category=anime&access_token={MEDIA_PRIVATE}"
        )
        original_feeds = {"global-feed": {"uid": "media-feed-1", "url": secret_url}}
        original_rule = _default_rule(secret_url)
        original_rules = {"global-rule": original_rule}

        if action == "list_rss_feeds":
            client.feeds = original_feeds
            result = await execution.dispatch()
            _assert_safe_common_read(result, action)
            feed = result.output["feeds"]["global-feed"]
            assert set(feed) == {"uid", "url"}
            assert feed["uid"] == "media-feed-1"
            sanitized_url = feed["url"]
            assert "category=anime" in sanitized_url
            assert urlsplit(sanitized_url).username is None
            assert urlsplit(sanitized_url).password is None

            large_url = "https://example.invalid/" + ("x" * 6000)
            large_feeds = {"large-feed": {"uid": "large-feed", "url": large_url}}
        else:
            client.rules = original_rules
            result = await execution.dispatch()
            _assert_safe_common_read(result, action)
            rule = result.output["rules"]["global-rule"]
            assert set(rule) == set(original_rule) - {"torrentParams"}
            assert rule["enabled"] is True
            assert rule["mustContain"] == "Synthetic Anime"
            assert "torrentParams" not in rule
            sanitized_url = rule["affectedFeeds"][0]
            assert "category=anime" in sanitized_url
            assert urlsplit(sanitized_url).username is None
            assert urlsplit(sanitized_url).password is None

            large_rule = _default_rule("https://example.invalid/" + ("x" * 6000))
            large_rules = {"large-rule": large_rule}

        assert MEDIA_PRIVATE not in _wire(result)
        if action == "list_rss_feeds":
            assert client.feeds["global-feed"]["url"] == secret_url
            observed_url = result.output["feeds"]["global-feed"]["url"]
        else:
            assert (
                client.rules["global-rule"]["torrentParams"]
                == original_rule["torrentParams"]
            )
            observed_url = result.output["rules"]["global-rule"]["affectedFeeds"][0]
        assert MEDIA_PRIVATE not in observed_url
        assert "media-user:" not in _wire(result)
        assert "category=anime" in _wire(result)
        assert "ssl_private_key" not in _wire(result)
        assert "torrentParams" not in _wire(result)

        if action == "list_rss_feeds":
            client.feeds = large_feeds
        else:
            client.rules = large_rules
        bounded = await execution.dispatch()
        assert bounded.status == "succeeded"
        assert bounded.provenance.get("bounded") is True
        assert bounded.artifacts
        assert all(item["kind"] == "bounded_output" for item in bounded.artifacts)
        json.dumps(bounded.output, allow_nan=False)
        assert MEDIA_PRIVATE not in _wire(bounded)

    assert client.write_calls == 0
    assert_no_model_calls(execution)
    record(request, key, "media_read_serialization")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", media_read_parameters("media_read_authorization"))
async def test_media_read_authorization_observation(
    key, db_session, media_sdk, monkeypatch, request
):
    client, factory = media_sdk
    execution = await make_media_read_execution(key, db_session, client, factory)
    action = key[0]

    if action == "library_status":
        assert execution.descriptor.requires_auth is False
        result = await execution.dispatch(
            context=execution.context_for(None, action=action)
        )
        _assert_safe_common_read(result, action)
        assert result.output["configured"] is True
        assert result.output["provider"] == "qbittorrent"
        assert factory.constructor_calls == 0
        assert client.calls == []
    else:
        configure_qb_settings(monkeypatch, allowed_user_ids="1")
        invalid_principals = (None, 0, -1, True)
        for principal_id in invalid_principals:
            result = await execution.dispatch(
                context=execution.context_for(principal_id, action=action)
            )
            assert result.status == "denied"
            assert result.error_code == "unauthorized"
            assert factory.constructor_calls == 0
            assert client.calls == []

        config_cases: tuple[dict[str, Any], ...] = (
            {"enabled": False, "host": "https://qbittorrent.synthetic.invalid"},
            {"enabled": True, "host": ""},
            {"enabled": True, "username": ""},
        )
        for config in config_cases:
            configure_qb_settings(
                monkeypatch,
                allowed_user_ids=str(execution.user.id),
                **config,
            )
            denied = await execution.dispatch(
                context=execution.context_for(execution.user.id, action=action)
            )
            assert denied.status == "denied" and denied.error_code == "not_configured"
            assert factory.constructor_calls == 0
            assert client.calls == []

        malformed_allowlists = (
            "",
            f"{execution.user.id},,{execution.other_user.id}",
            "not-an-id",
            f"{execution.user.id},-1",
            f"{execution.user.id},0",
        )
        for allowlist in malformed_allowlists:
            configure_qb_settings(monkeypatch, allowed_user_ids=allowlist)
            denied = await execution.dispatch(
                context=execution.context_for(execution.user.id, action=action)
            )
            assert denied.status == "failed" and denied.error_code == "forbidden"
            assert factory.constructor_calls == 0
            assert client.calls == []

        configure_qb_settings(monkeypatch, allowed_user_ids=str(execution.user.id))
        non_owner = await execution.dispatch(
            context=execution.context_for(execution.other_user.id, action=action)
        )
        assert non_owner.status == "failed" and non_owner.error_code == "forbidden"
        assert factory.constructor_calls == 0
        assert client.calls == []

        # Reads need neither approval nor an idempotency key. The trusted
        # Dispatcher context supplies the allowlisted principal to QBService.
        configure_qb_settings(
            monkeypatch,
            allowed_user_ids=f"{execution.user.id},{execution.other_user.id}",
        )
        allowed = await execution.dispatch(
            context=execution.context_for(execution.user.id, action=action)
        )
        _assert_safe_common_read(allowed, action)
        assert factory.constructor_calls == 1
        assert client.calls == ["auth_log_in", sdk_method(action)]

    assert client.write_calls == 0
    assert_no_model_calls(execution)
    record(request, key, "media_read_authorization")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", media_read_parameters("media_read_dispatcher"))
async def test_media_read_dispatcher_observation(
    key, db_session, media_sdk, monkeypatch, request
):
    client, factory = media_sdk
    execution = await make_media_read_execution(key, db_session, client, factory)
    action = key[0]
    assert isinstance(execution.descriptor, ActionDescriptor)
    assert execution.descriptor.is_side_effect is False
    assert execution.descriptor.input_schema["additionalProperties"] is False

    # Runtime-owned identity/dependencies and provider credentials never enter
    # model arguments. Remaining unknown keys fail the registered empty schema.
    forged_values = {
        "user_id": execution.user.id,
        "principal_id": execution.user.id,
        "tenant_id": "media-contract-tenant",
        "db": "synthetic-database-handle",
        "host": "https://attacker.invalid",
        "client": "synthetic-provider-client",
        "credential": MEDIA_PRIVATE,
        "credentials": MEDIA_PRIVATE,
        "password": MEDIA_PRIVATE,
    }
    context = execution.context_for(
        None if action == "library_status" else execution.user.id,
        action=action,
    )
    for name, value in forged_values.items():
        denied = await execution.dispatch(
            arguments={name: value}, context=context, forged_decision=True
        )
        assert denied.status == "denied"
        assert denied.error_code in {"identity_spoofing", "invalid_request"}
        assert MEDIA_PRIVATE not in _wire(denied)
        assert factory.constructor_calls == 0
        assert client.calls == []

    wrong_version = await execution.dispatch(
        context=context,
        version="v999",
    )
    assert wrong_version.status == "denied"
    assert wrong_version.error_code == "not_configured"
    assert factory.constructor_calls == 0
    assert client.calls == []
    assert client.write_calls == 0
    assert_no_model_calls(execution)
    record(request, key, "media_read_dispatcher")
