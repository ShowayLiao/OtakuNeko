from __future__ import annotations

import qbittorrentapi
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.harness.persistence.idempotency import SqlIdempotencyStore
from app.schemas.rss import RssRule
from app.services.qb_service import QBService, QBServiceError


class FakeQBClient:
    def __init__(self, *, url: str = "https://old.example/feed") -> None:
        self.url = url
        self.calls: list[tuple[str, dict]] = []
        self.add_failures: list[Exception] = []
        self.remove_failures: list[Exception] = []
        self.verify_failures: list[Exception] = []

    def rss_items(self, *, include_feed_data: bool = False):
        self.calls.append(("rss_items", {"include_feed_data": include_feed_data}))
        if self.verify_failures:
            raise self.verify_failures.pop(0)
        return {
            "feed": {
                "uid": "resource-123",
                "url": self.url,
            }
        }

    def rss_remove_item(self, *, item_path: str) -> None:
        self.calls.append(("rss_remove_item", {"item_path": item_path}))
        if self.remove_failures:
            raise self.remove_failures.pop(0)
        self.url = ""

    def rss_add_feed(self, *, url: str, item_path: str) -> None:
        self.calls.append(
            ("rss_add_feed", {"url": url, "item_path": item_path})
        )
        if self.add_failures:
            raise self.add_failures.pop(0)
        self.url = url

    def rss_set_rule(self, *, rule_name: str, rule_def: dict) -> None:
        self.calls.append(
            ("rss_set_rule", {"rule_name": rule_name, "rule_def": rule_def})
        )

    def rss_remove_rule(self, *, rule_name: str) -> None:
        self.calls.append(("rss_remove_rule", {"rule_name": rule_name}))

    def rss_rules(self):
        self.calls.append(("rss_rules", {}))
        return {}


def _service(client: FakeQBClient) -> QBService:
    return QBService(client=client)


def test_upsert_same_url_is_a_noop() -> None:
    client = FakeQBClient()

    result = _service(client).upsert_rss_feed(
        url="https://old.example/feed", name="feed"
    )

    assert result["status"] == "succeeded"
    assert [name for name, _ in client.calls] == ["rss_items"]


def test_upsert_verifies_new_resource_after_remove_and_add() -> None:
    client = FakeQBClient()

    result = _service(client).upsert_rss_feed(
        url="https://new.example/feed", name="feed"
    )

    assert result["status"] == "succeeded"
    assert [name for name, _ in client.calls] == [
        "rss_items",
        "rss_remove_item",
        "rss_add_feed",
        "rss_items",
    ]


def test_upsert_add_failure_attempts_one_compensation_and_records_attention() -> None:
    client = FakeQBClient()
    client.add_failures = [RuntimeError("downstream add leaked secret")]

    result = _service(client).upsert_rss_feed(
        url="https://new.example/feed", name="feed"
    )

    assert result == {
        "status": "attention_required",
        "error_code": "qb_upsert_add_failed",
        "message": "The RSS update needs manual verification.",
        "retryable": False,
        "old_resource_id": "resource-123",
        "compensation_status": "succeeded",
    }
    assert [name for name, _ in client.calls] == [
        "rss_items",
        "rss_remove_item",
        "rss_add_feed",
        "rss_add_feed",
    ]


def test_upsert_compensation_failure_is_queryable_and_not_retried() -> None:
    client = FakeQBClient()
    client.add_failures = [
        RuntimeError("new add failed"),
        RuntimeError("old add failed"),
    ]

    result = _service(client).upsert_rss_feed(
        url="https://new.example/feed", name="feed"
    )

    assert result["status"] == "attention_required"
    assert result["compensation_status"] == "failed"
    assert result["old_resource_id"] == "resource-123"
    assert len([name for name, _ in client.calls if name == "rss_add_feed"]) == 2


def test_only_connection_errors_are_retryable() -> None:
    class ConnectionFailure(qbittorrentapi.APIConnectionError):
        pass

    client = FakeQBClient()
    client.add_failures = [ConnectionFailure("connection detail")]

    with pytest.raises(QBServiceError) as error:
        _service(client).add_rss_feed(
            url="https://secret.example/feed", name="feed"
        )

    assert error.value.error_code == "qb_connection_error"
    assert error.value.retryable is True
    assert "connection detail" not in error.value.message


def test_unknown_qb_error_is_safe_and_not_retryable(caplog) -> None:
    client = FakeQBClient()
    client.add_failures = [RuntimeError("raw provider payload")]

    with pytest.raises(QBServiceError) as error:
        _service(client).add_rss_feed(
            url="https://secret.example/feed", name="feed"
        )

    assert error.value.error_code == "qb_operation_failed"
    assert error.value.retryable is False
    assert "raw provider payload" not in error.value.message
    assert "https://secret.example/feed" not in caplog.text
    assert "raw provider payload" not in caplog.text


def test_rule_payload_and_url_are_not_logged(caplog) -> None:
    client = FakeQBClient()
    rule = RssRule(
        affectedFeeds=["https://secret.example/feed"],
        assignedCategory="anime",
        enabled=True,
        episodeFilter="*",
        ignoreDays=0,
        mustContain="secret title",
        mustNotContain="",
        previouslyMatchedEpisodes=[],
        priority=0,
        savePath="/secret/path",
        smartFilter=False,
        useRegex=False,
    )

    _service(client).set_rss_rule("secret-rule", rule)

    assert "https://secret.example/feed" not in caplog.text
    assert "secret title" not in caplog.text
    assert "secret-rule" not in caplog.text


@pytest.mark.asyncio
async def test_sql_idempotency_replays_after_database_restart(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'idempotency.db').as_posix()}"
    first_engine = create_async_engine(database_url)
    async with first_engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    first_factory = async_sessionmaker(first_engine, expire_on_commit=False)
    calls = 0

    async with first_factory() as session:
        async def first_operation() -> dict[str, str]:
            nonlocal calls
            calls += 1
            return {"status": "succeeded", "message": "stored"}

        first = await SqlIdempotencyStore(session).execute_once(
            "principal:7|operation:rss.add|resource:one",
            "restart-key",
            "payload-a",
            first_operation,
        )
    await first_engine.dispose()

    second_engine = create_async_engine(database_url)
    second_factory = async_sessionmaker(second_engine, expire_on_commit=False)
    async with second_factory() as session:
        async def replay_operation() -> dict[str, str]:
            nonlocal calls
            calls += 1
            return {"status": "succeeded", "message": "must not run"}

        replay = await SqlIdempotencyStore(session).execute_once(
            "principal:7|operation:rss.add|resource:one",
            "restart-key",
            "payload-a",
            replay_operation,
        )
    await second_engine.dispose()

    assert first.status == "executed"
    assert replay.status == "replayed"
    assert replay.result["message"] == "stored"
    assert calls == 1


@pytest.mark.asyncio
async def test_sql_idempotency_persists_attention_without_retrying(db_session) -> None:
    calls = 0

    async def failed_operation() -> dict[str, str]:
        nonlocal calls
        calls += 1
        raise RuntimeError("unknown downstream state")

    store = SqlIdempotencyStore(db_session)
    first = await store.execute_once("scope", "key", "hash", failed_operation)
    replay = await store.execute_once("scope", "key", "hash", failed_operation)

    assert first.status == "executed"
    assert first.result["status"] == "attention_required"
    assert replay.status == "replayed"
    assert replay.result["error_code"] == "operation_state_unknown"
    assert calls == 1
