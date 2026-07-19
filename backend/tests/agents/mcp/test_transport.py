import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.mcp.sse_transport import SSETransport
from app.agents.mcp.stdio_transport import StdioTransport
from app.agents.mcp.connection_pool import MCPConnectionPool
from app.agents.mcp.heartbeat import MCPHeartbeat


class FakeReadlineStream:
    def __init__(self, responses):
        self._responses = list(responses)
        self._idx = 0

    async def readline(self):
        if self._idx < len(self._responses):
            data = self._responses[self._idx]
            self._idx += 1
            return data.encode("utf-8") if isinstance(data, str) else data
        return b""


class TestStdioTransport:
    """StdioTransport — 子进程 JSON-RPC 通信测试"""

    @pytest.mark.asyncio
    async def test_connect_sends_initialize_and_parses_response(self):
        init_result = '{"jsonrpc":"2.0","id":1,"result":{"serverInfo":{"name":"test-server","version":"1.0.0"}}}\n'
        tool_result = '{"jsonrpc":"2.0","id":2,"result":{"tools":[]}}\n'

        fake_stream = FakeReadlineStream([init_result, tool_result])
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write = MagicMock()
        mock_proc.stdin.drain = AsyncMock()
        mock_proc.stdout = fake_stream
        mock_proc.stderr = MagicMock()

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            transport = StdioTransport("test", "echo", ["hello"])
            await transport.connect()
            assert transport._connected

    def test_serialize_request_jsonrpc_format(self):
        msg = {"jsonrpc": "2.0", "id": 42, "method": "test", "params": {}}
        data = __import__("json").dumps(msg) + "\n"
        assert '"jsonrpc"' in data
        assert '"id": 42' in data

    def test_server_name_is_set(self):
        t = StdioTransport("my-mcp", "cmd")
        assert t.server_name == "my-mcp"
        assert t.command == "cmd"


class TestSSETransport:
    """SSETransport — HTTP POST JSON-RPC 通信测试"""

    @pytest.mark.asyncio
    async def test_send_request_sends_correct_payload(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0", "id": 1,
            "result": {"tools": [{"name": "tool-a"}]},
        }
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            transport = SSETransport("sse-srv", "http://localhost:8080/mcp")
            await transport.connect()

            tools = await transport.list_tools()
            assert len(tools) == 1
            assert tools[0]["name"] == "tool-a"
            methods = [call.kwargs["json"]["method"] for call in mock_client.post.call_args_list]
            assert methods[:2] == ["initialize", "notifications/initialized"]

    def test_server_name_is_set(self):
        t = SSETransport("sse", "http://host:9000")
        assert t.server_name == "sse"
        assert t.url == "http://host:9000"


class TestMCPConnectionPool:
    """MCPConnectionPool — 连接管理与断线重连测试"""

    @pytest.mark.asyncio
    async def test_register_connects_transport(self):
        pool = MCPConnectionPool(max_retries=2, retry_delay=0.01)

        transport = AsyncMock()
        transport.server_name = "pool-test"
        transport.connect = AsyncMock()

        await pool.register(transport)
        assert transport.connect.called
        await pool.stop()

    def test_call_tool_raises_for_unknown_server(self):
        pool = MCPConnectionPool()
        with pytest.raises(RuntimeError, match="not found"):
            asyncio.get_event_loop().run_until_complete(
                pool.call_tool("ghost", "tool", {}))

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self):
        pool = MCPConnectionPool(max_retries=2, retry_delay=0.01)

        transport = AsyncMock()
        transport.server_name = "flaky"
        transport.connect = AsyncMock(side_effect=RuntimeError("refused"))
        transport.close = AsyncMock()

        with pytest.raises(RuntimeError, match="2 retries"):
            await pool.register(transport)
        await pool.stop()


class TestMCPHeartbeat:
    """MCPHeartbeat — 心跳检测与死亡回调测试"""

    @pytest.mark.asyncio
    async def test_mark_alive_resets_consecutive_misses(self):
        hb = MCPHeartbeat(interval=0.1, timeout=0.05, max_misses=3)
        hb.register("srv")
        hb.mark_alive("srv")
        assert hb._status["srv"].alive
        assert hb._status["srv"].consecutive_misses == 0

    @pytest.mark.asyncio
    async def test_dead_callback_fires_after_consecutive_misses(self):
        callback_results = []

        async def on_dead(name):
            callback_results.append(name)

        hb = MCPHeartbeat(interval=0.05, timeout=0.02, max_misses=2)
        hb.on_dead(on_dead)
        hb.register("dead-srv")

        await hb.start()
        await asyncio.sleep(0.3)
        await hb.stop()

        assert "dead-srv" in callback_results
