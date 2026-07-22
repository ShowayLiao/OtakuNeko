"""Tests for the MCP stdio entry-point registry composition."""

from app.mcp_server.entry import build_registry


def test_entry_exposes_only_unauthenticated_legacy_capability():
    registry = build_registry()

    assert registry.list_names() == ["anime"]
