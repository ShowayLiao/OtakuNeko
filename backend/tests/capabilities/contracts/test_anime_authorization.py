"""Anime authorization, input admission, and real Dispatcher certification."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.capabilities import anime
from app.harness.authority import RUNTIME_OWNED_FIELDS
from app.harness.normalizer import validate_input, SchemaContractError
from tests.capabilities.contracts.anime_support import anime_parameters, make_execution
from tests.capabilities.contracts.plugin import record
from tests.capabilities.contracts.test_contracts import assert_subset


@pytest.mark.parametrize("key", anime_parameters("anime_authorization"))
async def test_anime_authorization(key, db_session, monkeypatch, request):
    execution = await make_execution(key, db_session, monkeypatch, authenticated=False)
    result = await execution.dispatch()
    if execution.descriptor.requires_auth:
        assert result.status == "denied" and result.error_code == "unauthorized"
        assert not execution.env.calls
    else:
        assert result.status == "succeeded"
        assert_subset(execution.example.expected, result.output)
        assert execution.env.calls

    execution = await make_execution(key, db_session, monkeypatch)
    for field in sorted(RUNTIME_OWNED_FIELDS):
        for location in ("root", "nested"):
            arguments = deepcopy(execution.example.arguments)
            arguments.update(
                {field: "forged-authority"}
                if location == "root"
                else {"untrusted": [{field: "forged-authority"}]}
            )
            with pytest.raises(ValidationError):
                await execution.dispatch(arguments)
            denied = await execution.dispatch(arguments, forged=True)
            assert (
                denied.status == "denied" and denied.error_code == "identity_spoofing"
            )
            assert not execution.env.calls

    if execution.descriptor.requires_auth:
        for principal in (None, 0, -1):
            denied = await execution.dispatch(
                context=execution.context.model_copy(update={"principal_id": principal})
            )
            assert denied.status == "denied" and denied.error_code == "unauthorized"
            assert not execution.env.calls
        for binding in (None, "", "   "):
            unbound = await make_execution(
                key, db_session, monkeypatch, linked_name=binding
            )
            refused = await unbound.dispatch()
            assert refused.status == "denied" and refused.error_code == "not_configured"
            assert not unbound.env.calls
        execution = await make_execution(key, db_session, monkeypatch)
        spoofed_user = await execution.dispatch(
            {"user": {"bangumi_name": "other-account"}, "username": "other-account"}
        )
        assert spoofed_user.status == "succeeded"
        assert spoofed_user.output["user"]["username"] == "contract-bangumi"
    record(request, key, "anime_authorization")


@pytest.mark.parametrize("key", anime_parameters("anime_dispatcher"))
async def test_anime_dispatcher(key, db_session, monkeypatch, request):
    execution = await make_execution(key, db_session, monkeypatch)
    denied = await execution.dispatch(
        context=execution.context.model_copy(
            update={"capability_allowlist": frozenset({"unrelated.action"})}
        )
    )
    assert denied.status == "denied" and denied.error_code == "policy_denied"
    wrong_version = await execution.dispatch(version="v999")
    assert (
        wrong_version.status == "denied"
        and wrong_version.error_code == "not_configured"
    )
    assert not execution.env.calls and not execution.dispatcher.events
    for name, schema in execution.descriptor.input_schema.get("properties", {}).items():
        if schema.get("type") not in {"array", "integer", "string"}:
            continue
        invalid = deepcopy(execution.example.arguments)
        invalid[name] = {"wrong": "type"}
        result = await execution.dispatch(invalid)
        assert result.status == "denied" and result.error_code == "invalid_request"
        assert not execution.env.calls and not execution.dispatcher.events
    if key[0] == "get_anime_info_batch":
        for ids in ([], list(range(1, 7)), [0], [-1], [True], ["1"]):
            result = await execution.dispatch({"subject_ids": ids})
            assert result.status == "denied" and result.error_code == "invalid_request"
            assert not execution.env.calls
        result = await execution.dispatch({"subject_ids": [501], "unexpected": True})
        assert result.status == "denied" and result.error_code == "invalid_request"
    result = await execution.dispatch()
    assert result.status == "succeeded" and result.error_code is None
    assert_subset(execution.example.expected, result.output)
    assert execution.env.calls
    events = execution.dispatcher.events
    assert [event.event_type for event in events] == [
        "invocation_start",
        "invocation_end",
    ]
    assert events[0].invocation_id == events[1].invocation_id == result.invocation_id
    assert events[1].payload["status"] == "succeeded"
    assert (
        result.run_id == execution.context.run_id
        and result.trace_id == execution.context.trace_id
    )
    record(request, key, "anime_dispatcher")


@pytest.mark.parametrize("key", anime_parameters("output-schema-probe", required=False))
def test_anime_declares_success_payload_fields(key):
    from app.capabilities.factory import build_capability_registry

    owner = build_capability_registry().find_action(key[0])
    assert owner is not None
    descriptor = owner[1]
    assert descriptor.output_schema.get("required"), f"Open output contract: {key}"


async def test_anime_raw_error_and_log_do_not_disclose_diagnostic(monkeypatch):
    diagnostic = "synthetic-private-upstream-diagnostic"
    logs = []

    async def fail(*args, **kwargs):
        raise RuntimeError(diagnostic)

    monkeypatch.setattr(anime, "fetch_subject_by_id", fail)
    monkeypatch.setattr(
        anime.logger, "error", lambda *args, **kwargs: logs.append((args, kwargs))
    )
    result = await anime.AnimeCapability().execute("get_detail", subject_id=1)
    assert result["success"] is False and result["error_type"] == "internal"
    assert diagnostic not in str(result)
    assert logs and diagnostic not in str(logs)


@pytest.mark.parametrize("values", [[], list(range(1, 7))])
def test_declared_batch_length_is_enforced_before_dispatch(values):
    descriptor = next(
        d for d in anime.AnimeCapability().actions() if d.name == "get_detail_batch"
    )
    with pytest.raises(SchemaContractError):
        validate_input({"subject_ids": values}, descriptor)


def test_anime_certification_dimensions_are_mandatory():
    from tests.capabilities.contracts.catalog import (
        census,
        cases,
        expected_observations,
    )

    expected = expected_observations(census(), cases())
    key = ("get_bangumi_calendar", "v1")
    assert (*key, "anime_authorization") in expected
    assert (*key, "anime_error") in expected
