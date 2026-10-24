"""Real Media/QB read boundaries, closed contracts and safe observations."""

import json
import logging
from typing import Any

import pytest
import qbittorrentapi

from app.capabilities import media
from app.core.config import settings
from app.harness.normalizer import ResultNormalizer, validate_input, SchemaContractError
from app.schemas.rss import RssRule

READS = ("library_status", "list_rss_feeds", "list_rss_rules")
PRIVATE = "synthetic-media-private-diagnostic"


class Client:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.feeds: Any = {
            "feed": {"uid": "feed-7", "url": "https://example.invalid/rss"}
        }
        self.rules: Any = {
            "rule": RssRule(
                affectedFeeds=["https://example.invalid/rss"],
                assignedCategory="anime",
                enabled=True,
                episodeFilter="",
                ignoreDays=0,
                mustContain="anime",
                mustNotContain="",
                previouslyMatchedEpisodes=[],
                priority=0,
                savePath="anime",
                smartFilter=False,
                useRegex=False,
            ).model_dump(mode="json")
        }
        self.failure: Exception | None = None
        self.login_failure: Exception | None = None

    def auth_log_in(self) -> None:
        self.calls.append("login")
        if self.login_failure:
            raise self.login_failure

    def rss_items(self) -> Any:
        self.calls.append("items")
        if self.failure:
            raise self.failure
        return self.feeds

    def rss_rules(self) -> Any:
        self.calls.append("rules")
        if self.failure:
            raise self.failure
        return self.rules

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"Unexpected SDK operation: {name}")


@pytest.fixture
def client(monkeypatch):
    import qbittorrentapi

    value = Client()
    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", True)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", "7")
    monkeypatch.setattr(settings, "QB_HOST", "https://qb.synthetic.invalid")
    monkeypatch.setattr(settings, "QB_USERNAME", "synthetic-user")
    monkeypatch.setattr(settings, "QB_PASSWORD", "synthetic-password")
    monkeypatch.setattr(media, "QBService", None)
    monkeypatch.setattr(qbittorrentapi, "Client", lambda **kwargs: value)
    return value


@pytest.mark.parametrize("action", READS)
def test_media_read_contracts_are_closed_and_structured(action):
    descriptor = next(a for a in media.MediaCapability().actions() if a.name == action)
    with pytest.raises(SchemaContractError):
        validate_input({"host": "https://untrusted.invalid"}, descriptor)
    result = ResultNormalizer().normalize(
        {"success": True},
        descriptor=descriptor,
        run_id="r",
        decision_id="d",
        invocation_id="i",
        trace_id="t",
    )
    assert result.error_code == "invalid_output"
    assert descriptor.requires_auth is (action != "library_status")
    assert descriptor.is_side_effect is False


@pytest.mark.asyncio
@pytest.mark.parametrize("action", READS[1:])
@pytest.mark.parametrize("principal", [None, 0, -1, True, 7.0, "7"])
async def test_media_direct_read_requires_a_strict_principal(action, principal, client):
    result = await media.MediaCapability().execute(action, user_id=principal)
    assert result["success"] is False and result["error_type"] == "unauthorized"
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("action", READS[1:])
@pytest.mark.parametrize("allowlist", ["", "7,0", "7,,8", "７", "7,-1", "7,nope"])
async def test_media_read_allowlist_is_fail_closed(
    action, allowlist, client, monkeypatch
):
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", allowlist)
    result = await media.MediaCapability().execute(action, user_id=7)
    assert result["success"] is False and result["error_type"] == "forbidden"
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("action", READS[1:])
async def test_media_read_urls_hide_embedded_credentials(action, client):
    url = f"https://name:{PRIVATE}@example.invalid/rss?passkey={PRIVATE}&category=anime"
    client.feeds["feed"]["url"] = url
    client.rules["rule"]["affectedFeeds"] = [url]
    result = await media.MediaCapability().execute(action, user_id=7)
    assert result["success"] is True
    encoded = json.dumps(result, allow_nan=False)
    assert PRIVATE not in encoded and "name:" not in encoded
    assert "category=anime" in encoded
    assert client.calls == ["login", "items" if action == "list_rss_feeds" else "rules"]
    # Read projection must not alter qB resources.
    assert client.feeds["feed"]["url"] == url
    assert client.rules["rule"]["affectedFeeds"] == [url]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", READS[1:])
@pytest.mark.parametrize("fault", [ValueError, RuntimeError])
async def test_media_read_capability_faults_do_not_leak(
    action, fault, client, monkeypatch, caplog
):
    def fail():
        raise fault(PRIVATE)

    monkeypatch.setattr(media, "_new_qb", fail)
    media.logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR):
            result = await media.MediaCapability().execute(action, user_id=7)
    finally:
        media.logger.removeHandler(caplog.handler)
    assert result["success"] is False
    assert result["error_type"] == (
        "invalid_args" if fault is ValueError else "internal"
    )
    assert PRIVATE not in json.dumps(result)
    assert caplog.records and all(record.exc_info is None for record in caplog.records)
    assert PRIVATE not in repr([record.__dict__ for record in caplog.records])


@pytest.mark.asyncio
@pytest.mark.parametrize("action", READS[1:])
async def test_media_real_service_rejects_malformed_provider_payload(action, client):
    client.feeds = {"broken": {"url": "https://example.invalid"}}
    client.rules = {"broken": {"enabled": "invalid"}}
    result = await media.MediaCapability().execute(action, user_id=7)
    assert result["success"] is False and result["error_type"] == "qb_operation_failed"
    assert PRIVATE not in json.dumps(result)


@pytest.mark.asyncio
async def test_library_status_is_public_configuration_without_a_connection(client):
    result = await media.MediaCapability().execute("library_status")
    assert result == {"success": True, "configured": True, "provider": "qbittorrent"}
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("action", READS[1:])
@pytest.mark.parametrize("payload", [None, [], "synthetic malformed response", 7])
async def test_nonmapping_provider_response_is_not_an_empty_success(
    action, payload, client
):
    client.feeds = client.rules = payload
    result = await media.MediaCapability().execute(action, user_id=7)
    assert result["success"] is False and result["error_type"] == "qb_operation_failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("action", READS[1:])
@pytest.mark.parametrize("phase", ["login", "read"])
@pytest.mark.parametrize(
    "fault,code,retryable",
    [
        (qbittorrentapi.LoginFailed, "qb_authentication_failed", False),
        (qbittorrentapi.HTTP4XXError, "qb_request_rejected", False),
        (qbittorrentapi.HTTP5XXError, "qb_server_error", False),
        (qbittorrentapi.APIConnectionError, "qb_connection_error", True),
    ],
)
async def test_media_sdk_error_categories_survive_read_initialization(
    action, phase, fault, code, retryable, client
):
    if phase == "login":
        client.login_failure = fault(PRIVATE)
    else:
        client.failure = fault(PRIVATE)
    result = await media.MediaCapability().execute(action, user_id=7)
    assert result["success"] is False and result["error_type"] == code
    assert result["retryable"] is retryable
    assert PRIVATE not in json.dumps(result)
