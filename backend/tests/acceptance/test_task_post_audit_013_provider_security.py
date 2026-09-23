from datetime import datetime, timezone
import inspect

from fastapi import params
from fastapi import HTTPException
import pytest

from app.api.deps import get_current_user
from app.api.v1 import agent
from app.agents.provider_endpoint import ProviderEndpointError
from app.schemas.user import UserRead


def _user(user_id: int = 7) -> UserRead:
    return UserRead(
        id=user_id,
        username=f"user-{user_id}",
        created_at=datetime.now(timezone.utc),
    )


def test_models_check_requires_business_authentication_dependency():
    user_parameter = inspect.signature(agent.check_connection).parameters["user"]
    assert isinstance(user_parameter.default, params.Depends)
    assert user_parameter.default.dependency is get_current_user


def test_models_check_rate_limit_is_scoped_to_authenticated_owner(monkeypatch):
    monkeypatch.setattr(agent, "_MODEL_CHECK_ATTEMPTS", {}, raising=False)
    monkeypatch.setattr(agent.settings, "MODEL_CHECK_RATE_LIMIT", 1, raising=False)
    monkeypatch.setattr(agent.settings, "MODEL_CHECK_RATE_WINDOW_SECONDS", 60, raising=False)

    assert agent._consume_model_check_rate_limit(_user(7)) is True
    assert agent._consume_model_check_rate_limit(_user(7)) is False
    assert agent._consume_model_check_rate_limit(_user(8)) is True


@pytest.mark.asyncio
async def test_models_check_maps_endpoint_rejection_without_leaking_address(monkeypatch):
    monkeypatch.setattr(agent, "_MODEL_CHECK_ATTEMPTS", {}, raising=False)
    monkeypatch.setattr(
        agent,
        "_resolve_provider_base_url",
        lambda _: (_ for _ in ()).throw(
            ProviderEndpointError(
                "provider endpoint resolved address is not public",
                category="ssrf",
            )
        ),
    )

    try:
        await agent.check_connection(
            provider="openai-compatible",
            user=_user(),
        )
    except HTTPException as exc:
        assert exc.status_code == 422
        assert exc.detail == "Provider endpoint is not allowed"
        assert "169.254.169.254" not in str(exc.detail)
    else:
        raise AssertionError("endpoint rejection must fail closed")
