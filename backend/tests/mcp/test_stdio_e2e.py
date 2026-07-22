"""End-to-end stdio transport tests for MCP-002.

Tests use a subprocess to invoke the MCP entry point, send JSON-RPC
requests over stdin, and verify responses on stdout.

NOTE: These tests exercise a *real* subprocess on every run. They are
kept minimal to avoid flakiness on Windows async pipe semantics.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import pytest

from app.mcp_server import MAX_REQUEST_SIZE


def _build_initialize() -> bytes:
    return (
        json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
            },
        })
        + "\n"
    ).encode()


@pytest.mark.asyncio
async def test_initialize_and_tools_list():
    """Subprocess responds to initialize and tools/list correctly."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.mcp_server.entry",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        # initialize
        proc.stdin.write(_build_initialize())
        await proc.stdin.drain()

        line = await asyncio.wait_for(proc.stdout.readline(), timeout=15)
        resp = json.loads(line.decode())
        assert resp["result"]["protocolVersion"] == "2024-11-05"

        # tools/list
        proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            .encode()
            + b"\n"
        )
        await proc.stdin.drain()

        line = await asyncio.wait_for(proc.stdout.readline(), timeout=15)
        resp = json.loads(line.decode())
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}

        # Anime (all 5)
        for expected in (
            "anime_search",
            "anime_get_detail",
            "anime_get_staff",
            "anime_get_cast",
            "anime_get_reviews",
        ):
            assert expected in names, f"Missing tool {expected}"

        # Schedule read-only
        assert "schedule_list_schedules" in names
        # Media read-only
        assert "media_library_status" in names
        # Recommendation not exposed
        assert "recommendation_generate_profile" not in names

    finally:
        await _cleanup_proc(proc)


@pytest.mark.asyncio
async def test_tools_call_anime_search():
    """Subprocess returns a well-formed result for a real capability call."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.mcp_server.entry",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        proc.stdin.write(_build_initialize())
        await proc.stdin.drain()
        await asyncio.wait_for(proc.stdout.readline(), timeout=15)

        # tools/call anime_search
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "anime_search",
                "arguments": {"keyword": "Frieren"},
            },
        }) + "\n"
        proc.stdin.write(payload.encode())
        await proc.stdin.drain()

        line = await asyncio.wait_for(proc.stdout.readline(), timeout=15)
        resp = json.loads(line.decode())
        content = json.loads(resp["result"]["content"][0]["text"])
        assert resp["id"] == 3
        assert isinstance(content["success"], bool)
        assert resp["result"]["isError"] is (content["success"] is False)
        if content["success"]:
            assert "results" in content
        else:
            assert "error_type" in content

    finally:
        await _cleanup_proc(proc)


@pytest.mark.asyncio
async def test_unknown_method_returns_error():
    """Unknown JSON-RPC methods return -32601."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.mcp_server.entry",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        proc.stdin.write(_build_initialize())
        await proc.stdin.drain()
        await asyncio.wait_for(proc.stdout.readline(), timeout=15)

        payload = json.dumps({
            "jsonrpc": "2.0", "id": 5, "method": "bogus/method",
        }) + "\n"
        proc.stdin.write(payload.encode())
        await proc.stdin.drain()

        line = await asyncio.wait_for(proc.stdout.readline(), timeout=15)
        resp = json.loads(line.decode())
        assert resp["error"]["code"] == -32601

    finally:
        await _cleanup_proc(proc)


@pytest.mark.asyncio
async def test_unknown_tool_returns_failure():
    """Calling an unregistered tool returns an invalid-params error."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.mcp_server.entry",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        proc.stdin.write(_build_initialize())
        await proc.stdin.drain()
        await asyncio.wait_for(proc.stdout.readline(), timeout=15)

        payload = json.dumps({
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "nonexistent", "arguments": {}},
        }) + "\n"
        proc.stdin.write(payload.encode())
        await proc.stdin.drain()

        line = await asyncio.wait_for(proc.stdout.readline(), timeout=15)
        resp = json.loads(line.decode())
        assert resp["error"]["code"] == -32602

    finally:
        await _cleanup_proc(proc)


@pytest.mark.asyncio
async def test_malformed_json_returns_parse_error_and_server_continues():
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.mcp_server.entry",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        proc.stdin.write(b"{not-json}\n")
        await proc.stdin.drain()
        response = json.loads(
            (await asyncio.wait_for(proc.stdout.readline(), timeout=15)).decode()
        )
        assert response["id"] is None
        assert response["error"]["code"] == -32700

        proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": 8, "method": "tools/list"})
            .encode()
            + b"\n"
        )
        await proc.stdin.drain()
        response = json.loads(
            (await asyncio.wait_for(proc.stdout.readline(), timeout=15)).decode()
        )
        assert response["id"] == 8
    finally:
        await _cleanup_proc(proc)


@pytest.mark.asyncio
async def test_nonstandard_json_constant_returns_parse_error():
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.mcp_server.entry",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        proc.stdin.write(
            b'{"jsonrpc":"2.0","id":12,"method":"tools/list",'
            b'"params":{"value":NaN}}\n'
        )
        await proc.stdin.drain()
        response = json.loads(
            (await asyncio.wait_for(proc.stdout.readline(), timeout=15)).decode()
        )
        assert response["id"] is None
        assert response["error"]["code"] == -32700
    finally:
        await _cleanup_proc(proc)


@pytest.mark.asyncio
async def test_initialized_notification_emits_no_protocol_frame():
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.mcp_server.entry",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        proc.stdin.write(
            json.dumps({
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }).encode()
            + b"\n"
        )
        proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": 9, "method": "tools/list"})
            .encode()
            + b"\n"
        )
        await proc.stdin.drain()

        response = json.loads(
            (await asyncio.wait_for(proc.stdout.readline(), timeout=15)).decode()
        )
        assert response["id"] == 9
    finally:
        await _cleanup_proc(proc)


@pytest.mark.asyncio
async def test_authenticated_media_call_uses_trusted_environment():
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.mcp_server.entry",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={
            **os.environ,
            "DEBUG": "false",
            "OTAKUNEKO_MCP_USER_ID": "42",
        },
    )

    try:
        proc.stdin.write(_build_initialize())
        await proc.stdin.drain()
        await asyncio.wait_for(proc.stdout.readline(), timeout=15)
        proc.stdin.write(
            json.dumps({
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {"name": "media_list_rss_feeds", "arguments": {}},
            }).encode()
            + b"\n"
        )
        await proc.stdin.drain()

        response = json.loads(
            (await asyncio.wait_for(proc.stdout.readline(), timeout=15)).decode()
        )
        content = json.loads(response["result"]["content"][0]["text"])
        assert content["success"] is True
        assert response["result"]["isError"] is False
    finally:
        await _cleanup_proc(proc)


@pytest.mark.asyncio
async def test_oversized_request_returns_error_and_server_continues():
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.mcp_server.entry",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        proc.stdin.write(b"x" * (MAX_REQUEST_SIZE + 1) + b"\n")
        await proc.stdin.drain()
        response = json.loads(
            (await asyncio.wait_for(proc.stdout.readline(), timeout=15)).decode()
        )
        assert response["error"]["code"] == -32600

        proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": 11, "method": "tools/list"})
            .encode()
            + b"\n"
        )
        await proc.stdin.drain()
        response = json.loads(
            (await asyncio.wait_for(proc.stdout.readline(), timeout=15)).decode()
        )
        assert response["id"] == 11
    finally:
        await _cleanup_proc(proc)


@pytest.mark.asyncio
async def test_clean_eof_exits_zero():
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.mcp_server.entry",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    proc.stdin.close()
    await asyncio.wait_for(proc.wait(), timeout=15)
    assert proc.returncode == 0


async def _cleanup_proc(proc: asyncio.subprocess.Process) -> None:
    """Close stdin and verify graceful stdio shutdown before forcing exit."""
    try:
        if proc.returncode is None:
            proc.stdin.close()
    except Exception:
        pass
    try:
        if proc.returncode is None:
            await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=3)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
