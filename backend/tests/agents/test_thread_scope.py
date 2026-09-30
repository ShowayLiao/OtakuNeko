import pytest

from app.agents.thread_scope import (
    AnonymousThread,
    make_anonymous_thread,
    make_user_thread,
    public_thread_id,
)


def test_user_threads_are_namespaced_by_user_without_changing_public_id():
    first = make_user_thread(7, "watching")
    second = make_user_thread(8, "watching")

    assert first.public_id == "watching"
    assert second.public_id == "watching"
    assert first.internal_id != second.internal_id
    assert first.internal_id == "user:7:thread:watching"
    assert second.internal_id == "user:8:thread:watching"


def test_user_thread_ids_are_rejected_when_empty_or_oversized():
    with pytest.raises(ValueError):
        make_user_thread(7, "")

    with pytest.raises(ValueError):
        make_user_thread(7, "x" * 129)


def test_public_thread_id_never_exposes_another_user_namespace():
    scope = make_user_thread(7, "watching")

    assert public_thread_id(7, scope.internal_id) == "watching"
    assert public_thread_id(8, scope.internal_id) is None


def test_anonymous_threads_are_ephemeral_and_unique():
    first = make_anonymous_thread()
    second = make_anonymous_thread()

    assert isinstance(first, AnonymousThread)
    assert first.public_id is None
    assert first.internal_id.startswith("anon:")
    assert first.internal_id != second.internal_id
