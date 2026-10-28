"""HTTP error contracts for the existing approval-resume ingress."""

from collections.abc import Callable
import json

import httpx
import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import create_access_token
from app.harness.persistence.run_store import RunStore
from app.models.user import User


@pytest.fixture
async def resume_headers(db_session: AsyncSession) -> dict[str, str]:
    db_session.add(User(id=401, username="resume-owner"))
    db_session.add(User(id=402, username="resume-other"))
    await db_session.commit()
    return {"Authorization": "Bearer " + create_access_token({"sub": "401"})}


@pytest.mark.parametrize(
    ("query", "expected_status", "expected_detail"),
    [
        ({"thread_id": "resume"}, 400, "run_id is required"),
        (
            {"thread_id": "resume", "run_id": "absent", "decision": "unknown"},
            400,
            "decision must be 'approve' or 'reject'",
        ),
        (
            {"thread_id": "resume", "run_id": "absent"},
            404,
            "Run not found",
        ),
    ],
)
async def test_resume_error_body(
    api_client: httpx.AsyncClient,
    resume_headers: dict[str, str],
    query: dict[str, str],
    expected_status: int,
    expected_detail: str,
    record_property: Callable[[str, object], None],
) -> None:
    response = await api_client.post(
        "/api/v1/chat/resume", params=query, headers=resume_headers
    )
    assert response.status_code == expected_status
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": expected_detail}
    record_property(
        "safe_http_failure",
        json.dumps({"status": response.status_code, "body": response.json()}),
    )


async def test_resume_required_thread_schema(
    api_client: httpx.AsyncClient, resume_headers: dict[str, str]
) -> None:
    response = await api_client.post("/api/v1/chat/resume", headers=resume_headers)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(
        item["loc"] == ["query", "thread_id"] and item["type"] == "missing"
        for item in detail
    )


@pytest.mark.parametrize(
    "status", ["queued", "succeeded", "failed", "cancelled", "abandoned"]
)
async def test_resume_terminal_or_not_started_is_conflict_without_mutation(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    resume_headers: dict[str, str],
    status: str,
    record_property: Callable[[str, object], None],
) -> None:
    store = RunStore(db_session)
    await store.create(
        run_id="resume-state",
        user_id=401,
        thread_id="user:401:thread:resume",
        status=status,
    )
    response = await api_client.post(
        "/api/v1/chat/resume",
        params={"thread_id": "resume", "run_id": "resume-state"},
        headers=resume_headers,
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Run is not resumable"}
    saved = await store.get("resume-state", user_id=401)
    assert saved is not None and saved.status == status
    record_property(
        "safe_http_failure", json.dumps({"status": 409, "body": response.json()})
    )


@pytest.mark.parametrize("foreign", [False, True])
async def test_resume_wrong_thread_or_owner_matches_missing_resource(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    resume_headers: dict[str, str],
    foreign: bool,
) -> None:
    await RunStore(db_session).create(
        run_id="hidden-resume",
        user_id=402 if foreign else 401,
        thread_id="user:402:thread:resume" if foreign else "user:401:thread:another",
        status="paused",
    )
    hidden = await api_client.post(
        "/api/v1/chat/resume",
        params={"thread_id": "resume", "run_id": "hidden-resume"},
        headers=resume_headers,
    )
    missing = await api_client.post(
        "/api/v1/chat/resume",
        params={"thread_id": "resume", "run_id": "absent"},
        headers=resume_headers,
    )
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json() == missing.json() == {"detail": "Run not found"}


@pytest.mark.parametrize("kind", ["expired", "unknown-subject"])
async def test_required_identity_rejects_expired_or_unknown_subject(
    api_client: httpx.AsyncClient,
    resume_headers: dict[str, str],
    kind: str,
    record_property: Callable[[str, object], None],
) -> None:
    from datetime import timedelta

    token = (
        create_access_token({"sub": "401"}, expires_delta=timedelta(seconds=-60))
        if kind == "expired"
        else create_access_token({"sub": "999999"})
    )
    response = await api_client.get(
        "/api/v1/runs/absent", headers={"Authorization": "Bearer " + token}
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "无法验证凭据"}
    assert response.headers.get("www-authenticate") == "Bearer"
    record_property(
        "safe_http_failure", json.dumps({"status": 401, "body": response.json()})
    )


async def test_trace_invalid_cursor_is_safe_bad_request(
    api_client: httpx.AsyncClient,
    resume_headers: dict[str, str],
    record_property: Callable[[str, object], None],
) -> None:
    response = await api_client.get(
        "/api/v1/trace/", params={"cursor": "invalid"}, headers=resume_headers
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid trace cursor"}
    record_property(
        "safe_http_failure", json.dumps({"status": 400, "body": response.json()})
    )
