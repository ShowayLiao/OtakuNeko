# MCP stdio offline tests

`backend/tests/mcp/test_stdio_e2e.py` 的默认 `anime_search` 用例通过测试子进程 bootstrap 将
`httpx.AsyncClient` 的 transport 替换为严格的 `httpx.MockTransport`。因此
`anime_search` 默认测试仍会经过真实的 MCP stdio、entry、Capability 和
`BangumiClient` 路径，但不会访问公网；mock 只在 child test process 中生效，
不改变 production source。

运行默认离线检查：

```powershell
$env:RUN_LIVE_BANGUMI_TESTS=$null
$env:DEBUG="false"
$env:JWT_SECRET_KEY="test-key-for-mcp-stdio"
$env:ENABLE_QB_PROXY="false"
uv run --locked --offline --directory backend pytest tests/mcp/test_stdio_e2e.py -q
```

默认通过只证明本地 MCP 与 fake upstream 合约可用，不证明公网 Bangumi 可达。
如需独立真实检查，显式启用并等待网络请求完成：

```powershell
$env:RUN_LIVE_BANGUMI_TESTS="1"
$env:DEBUG="false"
$env:JWT_SECRET_KEY="test-key-for-mcp-stdio"
$env:ENABLE_QB_PROXY="false"
uv run --locked --directory backend pytest tests/mcp/test_stdio_e2e.py::test_live_tools_call_anime_search -q
$env:RUN_LIVE_BANGUMI_TESTS=$null
```

真实检查必须返回 `success=true` 和结果列表；网络失败不会被视为通过。
