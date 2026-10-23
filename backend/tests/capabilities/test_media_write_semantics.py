"""Media write safety regressions; provider replaced only at SDK boundary."""

import pytest

from app.capabilities.media import MediaCapability
from app.services.qb_service import QBService


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_media_scope_hides_url_and_reserves_legacy_keys(db_session, legacy):
    from app.harness.capability_adapter import CapabilityAdapter, _payload_hash
    from app.harness.contracts import ExecutionContext
    from app.harness.persistence.idempotency import SqlIdempotencyStore
    from app.harness.policy import Approval, PolicyEngine
    from app.models.agent_run import AgentRun
    from sqlmodel import select

    calls = []

    class Capability(MediaCapability):
        async def execute(self, action, **kwargs):
            calls.append(action)
            return {
                "success": True,
                "operation": {"status": "succeeded", "message": "safe"},
                "idempotency_key": kwargs["idempotency_key"],
            }

    args = {
        "url": "https://user:PRIVATE_PASSWORD@example.invalid/rss?passkey=PRIVATE_PASSKEY",
        "idempotency_key": "legacy-url-key",
    }
    store = SqlIdempotencyStore(db_session)
    if legacy:
        await store.execute_once(
            "7:media:rss:feed:" + args["url"],
            args["idempotency_key"],
            _payload_hash(args),
            lambda: {"status": "succeeded", "result": {"success": True}},
        )
    adapter = CapabilityAdapter(
        Capability(),
        policy_engine=PolicyEngine(allow_side_effects=True),
        approval=Approval("a"),
        idempotency_store=store,
        trusted_args={"db": db_session},
    )
    result = await adapter.execute(
        ExecutionContext(principal_id=7, run_id="run", trace_id="trace"),
        "add_rss_feed",
        args,
    )
    if legacy:
        assert result["error_type"] == "attention_required"
        assert calls == []
    else:
        assert result["success"] is True
        records = (await db_session.execute(select(AgentRun))).scalars().all()
        assert records
        assert all(
            "PRIVATE_PASSWORD" not in row.thread_id
            and "PRIVATE_PASSKEY" not in row.thread_id
            for row in records
        )


def test_approval_projection_does_not_expose_url_credentials():
    from app.harness.runtime import _safe_approval_arguments

    value = _safe_approval_arguments(
        {
            "url": "https://user:PRIVATE_PASSWORD@example.invalid/rss?passkey=PRIVATE_PASSKEY"
        }
    )
    assert "PRIVATE_PASSWORD" not in str(value)
    assert "PRIVATE_PASSKEY" not in str(value)


@pytest.mark.parametrize("allowlist", ["7,0", "7,,8", "7,-1", "7,nope"])
def test_write_allowlist_rejects_invalid_configuration(monkeypatch, allowlist):
    from app.capabilities.media import _qb_access_allowed
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", True)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", allowlist)
    assert _qb_access_allowed(7) is False


@pytest.mark.asyncio
async def test_write_validation_error_never_exposes_provider_text(monkeypatch, caplog):
    import app.capabilities.media as media

    def fail():
        raise ValueError("PRIVATE_PROVIDER_DIAGNOSTIC")

    monkeypatch.setattr(media, "_new_qb", fail)
    monkeypatch.setattr(MediaCapability, "_require_qb", lambda *args, **kwargs: None)
    result = await MediaCapability().execute(
        "add_rss_feed", user_id=7, url="https://synthetic.invalid/rss"
    )
    assert "PRIVATE_PROVIDER_DIAGNOSTIC" not in str(result)
    assert "PRIVATE_PROVIDER_DIAGNOSTIC" not in caplog.text


def test_unknown_upsert_add_does_not_attempt_compensation():
    from tests.services.test_qb_service import FakeQBClient

    client = FakeQBClient()
    client.add_failures = [RuntimeError("unknown response")]
    result = QBService(client=client).upsert_rss_feed("https://new.invalid/rss", "feed")
    assert result["status"] == "attention_required"
    assert result["compensation_status"] == "not_attempted"
    assert sum(name == "rss_add_feed" for name, _ in client.calls) == 1


def test_unknown_upsert_remove_does_not_proceed_or_retry():
    import qbittorrentapi
    from tests.services.test_qb_service import FakeQBClient

    client = FakeQBClient()
    client.remove_failures = [
        qbittorrentapi.APIConnectionError("unknown remove response")
    ]
    result = QBService(client=client).upsert_rss_feed("https://new.invalid/rss", "feed")
    assert result["status"] == "attention_required"
    assert result["retryable"] is False
    assert [name for name, _ in client.calls] == ["rss_items", "rss_remove_item"]


@pytest.mark.asyncio
async def test_media_cross_action_key_cannot_replay_other_action():
    from app.harness.capability_adapter import CapabilityAdapter
    from app.harness.contracts import ExecutionContext
    from app.harness.persistence.idempotency import InMemoryIdempotencyStore
    from app.harness.policy import Approval, PolicyEngine

    class Capability(MediaCapability):
        async def execute(self, action, **kwargs):
            return {
                "success": True,
                "operation": {"status": "succeeded", "message": "safe"},
                "idempotency_key": kwargs["idempotency_key"],
            }

    adapter = CapabilityAdapter(
        Capability(),
        policy_engine=PolicyEngine(allow_side_effects=True),
        approval=Approval("a"),
        idempotency_store=InMemoryIdempotencyStore(),
    )
    context = ExecutionContext(principal_id=7, run_id="run", trace_id="trace")
    arguments = {
        "url": "https://synthetic.invalid/rss",
        "name": "feed",
        "idempotency_key": "same",
    }
    first = await adapter.execute(context, "add_rss_feed", arguments)
    second = await adapter.execute(context, "upsert_rss_feed", arguments)
    assert first["success"] is True
    assert second["success"] is False
    assert second["error_type"] == "idempotency_conflict"


@pytest.mark.asyncio
async def test_operation_attention_is_not_capability_success(monkeypatch):
    import app.capabilities.media as media

    class Client:
        def auth_log_in(self):
            pass

        def rss_items(self, **kwargs):
            return {"feed": {"uid": "id", "url": "https://old.invalid/rss"}}

        def rss_remove_item(self, **kwargs):
            pass

        def rss_add_feed(self, **kwargs):
            raise RuntimeError("PRIVATE_PROVIDER_DIAGNOSTIC")

    import qbittorrentapi
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", True)
    monkeypatch.setattr(settings, "QB_HOST", "https://qb.invalid")
    monkeypatch.setattr(settings, "QB_USERNAME", "synthetic")
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", "7")
    monkeypatch.setattr(qbittorrentapi, "Client", lambda **kwargs: Client())
    monkeypatch.setattr(media, "QBService", None)
    result = await MediaCapability().execute(
        "upsert_rss_feed",
        user_id=7,
        name="feed",
        url="https://new.invalid/rss",
        idempotency_key="attention-key",
    )
    assert result["success"] is False
    assert result["error_type"] == "attention_required"
    assert result.get("retryable", False) is False


@pytest.mark.parametrize(
    "action",
    [
        "add_rss_feed",
        "upsert_rss_feed",
        "remove_rss_feed",
        "set_rss_rule",
        "remove_rss_rule",
    ],
)
def test_write_contracts_are_structured_and_closed(action):
    descriptor = next(d for d in MediaCapability().actions() if d.name == action)
    assert descriptor.input_schema.get("additionalProperties") is False
    assert descriptor.output_schema.get("required")
    assert descriptor.approval_required and descriptor.idempotency_mode == "required"


def test_post_write_connection_failure_is_unknown_not_retryable():
    import qbittorrentapi

    class Client:
        writes = 0

        def rss_add_feed(self, **kwargs):
            self.writes += 1
            raise qbittorrentapi.APIConnectionError("PRIVATE_PROVIDER_DIAGNOSTIC")

    client = Client()
    result = QBService(client=client).add_rss_feed("https://synthetic.invalid/rss")
    assert client.writes == 1
    assert result["status"] == "attention_required"
    assert result["retryable"] is False
