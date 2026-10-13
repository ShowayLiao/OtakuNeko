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
import textwrap
import pytest

from app.mcp_server import MAX_REQUEST_SIZE


_OFFLINE_BOOTSTRAP = textwrap.dedent(
    """
    import os
    import runpy
    import httpx

    async def handler(request):
        expected_params = {"limit": "10", "offset": "0"}
        expected_body = {
            "keyword": "Frieren",
            "sort": "rank",
            "filter": {"type": [2]},
        }
        if (
            request.method != "POST"
            or request.url.scheme != "https"
            or request.url.host != "api.bgm.tv"
            or request.url.path != "/v0/search/subjects"
            or dict(request.url.params) != expected_params
            or not request.content
        ):
            return httpx.Response(400, json={"detail": "unexpected fake request"})
        if request.content:
            import json
            if json.loads(request.content) != expected_body:
                return httpx.Response(400, json={"detail": "unexpected fake body"})
        if os.environ.get("MCP_TEST_UPSTREAM_MODE") == "error":
            marker_path = os.environ.get("MCP_TEST_MARKER")
            if marker_path:
                with open(marker_path, "w", encoding="utf-8") as marker:
                    marker.write("fake upstream failure marker")
            raise httpx.ReadTimeout("fake upstream failure marker", request=request)
        return httpx.Response(
            200,
            json={
                "total": 1,
                "data": [
                    {
                        "id": 12345,
                        "name": "Sousou no Frieren",
                        "name_cn": "葬送的芙莉莲",
                        "summary": "A fixed offline fixture.",
                        "rating": {"score": 9.1, "rank": 1},
                        "type": 2,
                        "air_date": "2023-09-29",
                        "images": {"large": "https://example.invalid/frieren.jpg"},
                        "tags": [{"name": "Fantasy"}],
                    }
                ],
            },
        )

    class OfflineAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    httpx.AsyncClient = OfflineAsyncClient
    runpy.run_module("app.mcp_server.entry", run_name="__main__")
    """
)


async def _offline_process(
    mode: str = "success", marker_path: str | None = None
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _OFFLINE_BOOTSTRAP,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={
            **os.environ,
            "MCP_TEST_UPSTREAM_MODE": mode,
            "MCP_TEST_MARKER": marker_path or "",
        },
    )


def _require_stdio(
    proc: asyncio.subprocess.Process,
) -> tuple[asyncio.StreamWriter, asyncio.StreamReader]:
    """Return the subprocess stdio streams after validating their presence."""
    stdin = proc.stdin
    stdout = proc.stdout
    assert stdin is not None
    assert stdout is not None
    return stdin, stdout


def _build_initialize() -> bytes:
    return (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                },
            }
        )
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
        stdin, stdout = _require_stdio(proc)
        # initialize
        stdin.write(_build_initialize())
        await stdin.drain()

        line = await asyncio.wait_for(stdout.readline(), timeout=15)
        resp = json.loads(line.decode())
        assert resp["result"]["protocolVersion"] == "2024-11-05"

        # tools/list
        stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).encode()
            + b"\n"
        )
        await stdin.drain()

        line = await asyncio.wait_for(stdout.readline(), timeout=15)
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
async def test_offline_tools_call_anime_search():
    """Subprocess exercises the real MCP and capability path without network I/O."""
    proc = await _offline_process()

    try:
        stdin, stdout = _require_stdio(proc)
        stdin.write(_build_initialize())
        await stdin.drain()
        await asyncio.wait_for(stdout.readline(), timeout=15)

        # tools/call anime_search
        payload = (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "anime_search",
                        "arguments": {"keyword": "Frieren"},
                    },
                }
            )
            + "\n"
        )
        stdin.write(payload.encode())
        await stdin.drain()

        line = await asyncio.wait_for(stdout.readline(), timeout=15)
        resp = json.loads(line.decode())
        content = json.loads(resp["result"]["content"][0]["text"])
        assert resp["id"] == 3
        assert resp["result"]["isError"] is False
        assert content["success"] is True
        assert content["data"]["total"] == 1
        result = content["data"]["results"][0]
        assert result["id"] == 12345
        assert result["name"] == "Sousou no Frieren"
        assert result["name_cn"] == "葬送的芙莉莲"
        assert result["summary"] == "A fixed offline fixture...."
        assert result["score"] == 9.1
        assert result["rank"] == 1
        assert result["type"] == 2
        assert result["air_date"] == "2023-09-29"
        assert result["images"]["large"].endswith("frieren.jpg")
        assert result["tags"] == ["Fantasy"]

    finally:
        await _cleanup_proc(proc)


@pytest.mark.asyncio
async def test_offline_tools_call_anime_search_upstream_failure(tmp_path):
    """A real upstream failure remains an MCP internal error."""
    marker_path = str(tmp_path / "marker")
    proc = await _offline_process("error", marker_path)

    try:
        stdin, stdout = _require_stdio(proc)
        stdin.write(_build_initialize())
        await stdin.drain()
        await asyncio.wait_for(stdout.readline(), timeout=15)
        stdin.write(
            (
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "tools/call",
                        "params": {
                            "name": "anime_search",
                            "arguments": {"keyword": "Frieren"},
                        },
                    }
                )
                + "\n"
            ).encode()
        )
        await stdin.drain()

        response = json.loads(
            (await asyncio.wait_for(stdout.readline(), timeout=15)).decode()
        )
        content = json.loads(response["result"]["content"][0]["text"])
        assert response["result"]["isError"] is True
        assert content["success"] is False
        assert content["error_type"] == "internal"
        with open(marker_path, encoding="utf-8") as marker:
            assert marker.read() == "fake upstream failure marker"
    finally:
        await _cleanup_proc(proc)


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_BANGUMI_TESTS") != "1",
    reason="set RUN_LIVE_BANGUMI_TESTS=1 to enable the live Bangumi check",
)
async def test_live_tools_call_anime_search():
    """Opt-in integration check against the public Bangumi endpoint."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.mcp_server.entry",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdin, stdout = _require_stdio(proc)
        stdin.write(_build_initialize())
        await stdin.drain()
        await asyncio.wait_for(stdout.readline(), timeout=60)
        stdin.write(
            (
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 13,
                        "method": "tools/call",
                        "params": {
                            "name": "anime_search",
                            "arguments": {"keyword": "Frieren"},
                        },
                    }
                )
                + "\n"
            ).encode()
        )
        await stdin.drain()
        response = json.loads(
            (await asyncio.wait_for(stdout.readline(), timeout=60)).decode()
        )
        content = json.loads(response["result"]["content"][0]["text"])
        assert content["success"] is True
        assert isinstance(content["data"]["results"], list)
        assert response["result"]["isError"] is False
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
        stdin, stdout = _require_stdio(proc)
        stdin.write(_build_initialize())
        await stdin.drain()
        await asyncio.wait_for(stdout.readline(), timeout=15)

        payload = (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "bogus/method",
                }
            )
            + "\n"
        )
        stdin.write(payload.encode())
        await stdin.drain()

        line = await asyncio.wait_for(stdout.readline(), timeout=15)
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
        stdin, stdout = _require_stdio(proc)
        stdin.write(_build_initialize())
        await stdin.drain()
        await asyncio.wait_for(stdout.readline(), timeout=15)

        payload = (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {"name": "nonexistent", "arguments": {}},
                }
            )
            + "\n"
        )
        stdin.write(payload.encode())
        await stdin.drain()

        line = await asyncio.wait_for(stdout.readline(), timeout=15)
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
        stdin, stdout = _require_stdio(proc)
        stdin.write(b"{not-json}\n")
        await stdin.drain()
        response = json.loads(
            (await asyncio.wait_for(stdout.readline(), timeout=15)).decode()
        )
        assert response["id"] is None
        assert response["error"]["code"] == -32700

        stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": 8, "method": "tools/list"}).encode()
            + b"\n"
        )
        await stdin.drain()
        response = json.loads(
            (await asyncio.wait_for(stdout.readline(), timeout=15)).decode()
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
        stdin, stdout = _require_stdio(proc)
        stdin.write(
            b'{"jsonrpc":"2.0","id":12,"method":"tools/list","params":{"value":NaN}}\n'
        )
        await stdin.drain()
        response = json.loads(
            (await asyncio.wait_for(stdout.readline(), timeout=15)).decode()
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
        stdin, stdout = _require_stdio(proc)
        stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                }
            ).encode()
            + b"\n"
        )
        stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": 9, "method": "tools/list"}).encode()
            + b"\n"
        )
        await stdin.drain()

        response = json.loads(
            (await asyncio.wait_for(stdout.readline(), timeout=15)).decode()
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
        stdin, stdout = _require_stdio(proc)
        stdin.write(_build_initialize())
        await stdin.drain()
        await asyncio.wait_for(stdout.readline(), timeout=15)
        stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "tools/call",
                    "params": {"name": "media_list_rss_feeds", "arguments": {}},
                }
            ).encode()
            + b"\n"
        )
        await stdin.drain()

        response = json.loads(
            (await asyncio.wait_for(stdout.readline(), timeout=15)).decode()
        )
        content = json.loads(response["result"]["content"][0]["text"])
        assert content["success"] is False
        assert content["error_type"] == "not_configured"
        assert response["result"]["isError"] is True
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
        stdin, stdout = _require_stdio(proc)
        stdin.write(b"x" * (MAX_REQUEST_SIZE + 1) + b"\n")
        await stdin.drain()
        response = json.loads(
            (await asyncio.wait_for(stdout.readline(), timeout=15)).decode()
        )
        assert response["error"]["code"] == -32600

        stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": 11, "method": "tools/list"}).encode()
            + b"\n"
        )
        await stdin.drain()
        response = json.loads(
            (await asyncio.wait_for(stdout.readline(), timeout=15)).decode()
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

    stdin, _ = _require_stdio(proc)
    stdin.close()
    await asyncio.wait_for(proc.wait(), timeout=15)
    assert proc.returncode == 0


async def _cleanup_proc(proc: asyncio.subprocess.Process) -> None:
    """Close stdin and verify graceful stdio shutdown before forcing exit."""
    try:
        stdin = proc.stdin
        if proc.returncode is None and stdin is not None:
            stdin.close()
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
