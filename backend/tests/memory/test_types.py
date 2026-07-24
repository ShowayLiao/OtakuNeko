"""Tests for MEMORY-002 typed memory records."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.memory.types import MemoryKind, MemoryRecord


class TestMemoryKind:
    def test_values(self):
        assert MemoryKind.EPISODIC.value == "episodic"
        assert MemoryKind.SEMANTIC.value == "semantic"
        assert MemoryKind.PROFILE.value == "profile"

    def test_invalid_kind_raises(self):
        from app.memory.types import _validate_kind

        with pytest.raises(ValueError, match="invalid MemoryKind"):
            _validate_kind("bogus")


class TestMemoryRecord:
    def test_defaults(self):
        rec = MemoryRecord(user_id=1, thread_id="th-1", content="fact")
        assert rec.kind == MemoryKind.EPISODIC
        assert rec.importance == 0.5
        assert rec.source == "conversation"
        assert rec.user_id == 1
        assert rec.id is None

    def test_non_positive_user_id_is_rejected(self):
        with pytest.raises(ValueError, match="user_id"):
            MemoryRecord(user_id=0, thread_id="th-1", content="fact")

    def test_episodic_record_requires_thread(self):
        with pytest.raises(ValueError, match="thread_id"):
            MemoryRecord(user_id=1, content="fact")

    def test_importance_range_valid(self):
        rec = MemoryRecord(
            user_id=1, thread_id="th-1", content="fact", importance=0.0
        )
        assert rec.importance == 0.0
        rec = MemoryRecord(
            user_id=1, thread_id="th-1", content="fact", importance=1.0
        )
        assert rec.importance == 1.0

    def test_importance_below_zero_raises(self):
        with pytest.raises(ValueError):
            MemoryRecord(
                user_id=1, thread_id="th-1", content="fact", importance=-0.1
            )

    def test_importance_above_one_raises(self):
        with pytest.raises(ValueError):
            MemoryRecord(
                user_id=1, thread_id="th-1", content="fact", importance=1.1
            )

    def test_kind_as_string_is_validated(self):
        rec = MemoryRecord(user_id=1, content="fact", kind="semantic")
        assert rec.kind == MemoryKind.SEMANTIC

    def test_invalid_kind_string_raises(self):
        with pytest.raises(ValueError, match="invalid MemoryKind"):
            MemoryRecord(user_id=1, content="fact", kind="unknown")

    def test_to_dict_is_json_compatible(self):
        import json

        rec = MemoryRecord(
            id=1,
            user_id=42,
            thread_id="th-1",
            kind=MemoryKind.SEMANTIC,
            content="Likes sci-fi",
            importance=0.8,
            source="extraction",
            metadata={"model": "gpt-4"},
        )
        d = rec.to_dict()
        assert json.dumps(d)
        assert d["user_id"] == 42
        assert d["kind"] == "semantic"
        assert d["importance"] == 0.8

    def test_record_from_dict_roundtrip(self):
        rec = MemoryRecord(
            id=5,
            user_id=1,
            thread_id="th-2",
            kind=MemoryKind.EPISODIC,
            content="Watched episode 7",
            importance=0.3,
        )
        d = rec.to_dict()
        restored = MemoryRecord(
            id=d["id"],
            user_id=d["user_id"],
            thread_id=d["thread_id"],
            kind=d["kind"],
            content=d["content"],
            importance=d["importance"],
            created_at=datetime.fromisoformat(d["created_at"]),
            metadata=d["metadata"],
        )
        assert restored.id == 5
        assert restored.kind == MemoryKind.EPISODIC

    def test_no_model_api_or_repository_import(self):
        """Ensure no API/agent/repository imports leak via types."""
        import inspect
        import app.memory.types as types_mod

        source = inspect.getsource(types_mod)
        # Should NOT import any API/agent/repository modules
        assert "fastapi" not in source.lower()
        assert "agents/" not in source
