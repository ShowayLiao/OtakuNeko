# Tool Registry 重构 & MCP 接入计划

> 状态：待确认
> 日期：2026-05-20
> 目标：(1) 将硬编码工具列表重构为可扩展的 `ToolRegistry` 架构；(2) 预留 MCP (Model Context Protocol) 动态工具接入接口

---

## 1. 目标

- **消解硬编码**：废除 `graph.py` 中 `TOOLS = [...]` 模块级常量，引入 `ToolRegistry` 作为统一的工具注册、发现、执行入口
- **MCP 就绪**：在不破坏现有功能的前提下，预留 MCP Transport 抽象层、Tool Schema 适配器，使未来接入 MCP Server 只需添加配置即可
- **提升可观测性**：为所有工具补全结构化日志（调用参数、耗时、成功/失败）
- **标准化错误返回**：统一 `ToolResult` schema，让 LLM 和前端都能区分成功/业务错误/系统错误

## 2. 现状问题清单

### 2.1 致命级 (Blocker)

| # | 问题 | 位置 |
|---|------|------|
| 1 | 无 Tool Registry 抽象 — `TOOLS` 硬编码列表 | `graph.py:L11` |
| 2 | `bind_tools(TOOLS)` 每次 `stream_chat` 重新执行 | `graph.py:L50` |
| 3 | `ToolNode(TOOLS)` 编译时固化，无法动态增删工具 | `graph.py:L26` |
| 4 | 全部 7 个工具零日志记录 | `tools.py` 全文 |

### 2.2 严重级 (Major)

| # | 问题 | 位置 |
|---|------|------|
| 5 | `search_anime_advanced` 单函数 175 行（日期解析 + fallback + 结果简化混合） | `tools.py:L81-L256` |
| 6 | `generate_user_profile_tool` 让 LLM 传入完整收藏数据（反模式） | `tools.py:L316` |
| 7 | 所有工具返回裸 `dict`，无类型区分 | 全部 7 个工具 |
| 8 | 错误无区分：`return {"error": str(e)}` 对 LLM 是"合法结果" | 全部 7 个工具 |
| 9 | 与 `langchain_core.BaseTool` 强耦合 | `tools.py:L1` |

### 2.3 改善级 (Minor)

| # | 问题 | 位置 |
|---|------|------|
| 10 | `datetime` / `calendar` import 在函数体内部 | `tools.py:L140, L187` |
| 11 | 无工具级权限控制 | 全局 |
| 12 | 无工具版本号 / schema versioning | 全局 |

## 3. 技术方案

### 3.1 新增 `ToolRegistry` — 核心抽象

```
新建: app/agents/registry.py
```

```python
class ToolRegistry:
    """
    统一工具注册中心。
    生命周期: 启动注册本地 → 运行时注册 MCP → get_runtime_tools() → 动态编译 ToolNode
    """
    def __init__(self):
        self._local_tools: Dict[str, BaseTool] = {}
        self._mcp_clients: List["MCPTransport"] = []

    def register_local(self, tool: BaseTool, namespace: str = "local") -> None: ...

    def register_mcp(self, client: "MCPTransport") -> None: ...

    async def get_runtime_tools(self) -> List[BaseTool]:
        """
        动态拉取本地 + MCP 工具，返回 BaseTool 列表。
        供 executor 节点的动态 ToolNode 使用。
        MCP 工具会被包装为 async callable tool，内部调用 transport.call_tool()。
        """
        tools = list(self._local_tools.values())
        for client in self._mcp_clients:
            for tool_def in await client.list_tools():
                tools.append(
                    MCPToolAdapter.to_langchain_tool(tool_def, client)
                )
        return tools

    async def get_all_schemas(self) -> List[Dict[str, Any]]:
        """合并本地 + MCP 工具 schema，供 llm.bind_tools() 使用"""
        ...
```

### 3.2 拆分 `tools.py` → `tools/` 目录

```
app/agents/tools/
├── __init__.py          # 导出 register_all(registry)
├── anime.py             # get_anime_info, fetch_audience_reviews, get_anime_staff, get_anime_cast
├── search.py            # search_anime_advanced (重构拆分)
├── datetime.py          # get_current_time
├── profile.py           # generate_user_profile_tool
└── base.py              # ToolResult schema, 通用装饰器
```

**`search.py` 重构要点**：
- 将日期范围解析提取为独立函数 `_build_air_date_ranges()`
- 将结果简化提取为 `_simplify_results()`
- 将 fallback 逻辑提取为 `_fallback_search()`

### 3.3 统一 ToolResult Schema

```python
# tools/base.py
from pydantic import BaseModel

class ToolResult(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None
    error_type: Literal["network", "not_found", "invalid_args", "internal"] | None = None
    tool_name: str
    duration_ms: float
```

### 3.4 结构化日志

```python
# 所有工具统一日志格式
logger.info("tool_called", extra={
    "tool_name": "get_anime_info",
    "args": {"subject_id": 12345},
    "duration_ms": 234.5,
    "success": True,
})
```

### 3.5 MCP 接口预留

#### MCPTransport 抽象

```python
# agents/mcp/transport.py

class MCPTransport(ABC):
    """MCP 传输层抽象基类"""

    server_name: str  # 用于命名空间前缀

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def list_tools(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any: ...
```

#### MCPToolAdapter

```python
# agents/mcp/adapter.py

class MCPToolAdapter:
    """将 MCP tool schema 转换为 LangChain 兼容格式"""
    
    @staticmethod
    def to_openai_function(tool_def: Dict) -> Dict:
        """MCP tool schema → OpenAI function calling schema"""
        ...
    
    @staticmethod 
    def to_langchain_tool(tool_def: Dict, transport: MCPTransport) -> BaseTool:
        """MCP tool schema → 可注入到 ToolRegistry 的 BaseTool"""
        ...
```

#### MCP 配置

```json
// mcp_servers.json (环境变量 MCP_SERVERS 也可)
{
  "servers": [
    {
      "name": "filesystem",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-filesystem", "/data"]
    },
    {
      "name": "database",
      "transport": "sse",
      "url": "http://localhost:8001/sse"
    }
  ]
}
```

### 3.6 graph.py 改动 — 动态 ToolNode

```python
# 旧
from app.agents.tools import get_anime_info, ...
TOOLS = [get_anime_info, ...]
class ChatWorkflow:
    def __init__(self, ...):
        self.app = self._compile_graph()
    def _compile_graph(self):
        workflow.add_node("tools", ToolNode(TOOLS))

# 新 — 动态 ToolNode（本地 + MCP 统一为 LangGraph ToolNode）
import asyncio
from app.agents.registry import ToolRegistry
from app.agents.tools import register_all

class ChatWorkflow:
    def __init__(self, ..., registry: ToolRegistry):
        self.registry = registry
        self.app = self._compile_graph()

    def _compile_graph(self):
        # 动态 ToolNode：每次 graph 初始化时拉取全量工具
        # MCP 工具通过 MCPToolAdapter 包装为 BaseTool，与本地工具无差别
        runtime_tools = asyncio.run(self.registry.get_runtime_tools())
        
        workflow = StateGraph(CodingAgentState)
        workflow.add_node("planner", self._plan_task)
        workflow.add_node("executor", ToolNode(runtime_tools))  # ← 统一动态 ToolNode
        workflow.add_node("verifier", self._verify_result)
        # ... 路由逻辑不变 ...
        return workflow.compile(checkpointer=self.checkpointer)
```

**关键点**：
- `get_runtime_tools()` 每次 graph 初始化时调用一次，确保 MCP 工具被纳入 ToolNode
- MCP 工具通过 `MCPToolAdapter.to_langchain_tool()` 包装为标准 `BaseTool`，`ToolNode` 对其无感知差异
- 所有工具（本地+MCP）统一走 LangGraph 的 `ToolNode` 执行器，享受完整的流式输出/错误处理/可观测性
- 图拓扑保持干净：`planner → executor → verifier`，无手动工具路由分支

### 3.7 API 层改动

```python
# api/v1/agent.py

# 启动时创建全局 ToolRegistry
from app.agents.registry import ToolRegistry
from app.agents.tools import register_all

_tool_registry = ToolRegistry()
register_all(_tool_registry)  # 注册本地工具

# 可选: 加载 MCP 配置
# await load_mcp_servers(_tool_registry, "mcp_servers.json")

@router.post("/chat")
async def chat_endpoint(...):
    workflow = ChatWorkflow(..., registry=_tool_registry)
    ...
```

## 4. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/agents/registry.py` | **新增** | ToolRegistry 核心 |
| `app/agents/tools/__init__.py` | **新增** | `register_all(registry)` |
| `app/agents/tools/base.py` | **新增** | `ToolResult` schema, 通用装饰器 |
| `app/agents/tools/anime.py` | **新增** | 拆分 anime 相关工具 |
| `app/agents/tools/search.py` | **新增** | 拆分 + 重构 search_anime_advanced |
| `app/agents/tools/datetime.py` | **新增** | 拆分 get_current_time |
| `app/agents/tools/profile.py` | **新增** | 拆分 generate_user_profile_tool |
| `app/agents/tools.py` | **删除** | 不再需要 |
| `app/agents/mcp/__init__.py` | **新增** | MCP bridge 包 |
| `app/agents/mcp/transport.py` | **新增** | MCPTransport 抽象 + StdioTransport/SSETransport |
| `app/agents/mcp/adapter.py` | **新增** | MCPToolAdapter |
| `app/agents/mcp/loader.py` | **新增** | 从配置文件加载 MCP Server |
| `app/agents/graph.py` | **重构** | 移除 TOOLS 常量，注入 ToolRegistry |
| `app/api/v1/agent.py` | **修改** | 初始化 ToolRegistry，传递给 ChatWorkflow |
| `pyproject.toml` | **修改** | 添加 `mcp>=1.0.0` |

## 5. 执行步骤

### Step 1: 工具体系重构（不涉及 MCP）

1. 创建 `app/agents/tools/base.py` — 定义 `ToolResult` schema
2. 创建 `app/agents/registry.py` — 实现 `ToolRegistry` (仅本地工具部分)
3. 拆分 `tools.py` → `tools/` 目录下的各个文件
4. 每个工具补全结构化日志
5. `tools/__init__.py` 实现 `register_all(registry)`
6. 重构 `graph.py`：注入 `ToolRegistry` 替代 `TOOLS = [...]`
7. 修改 `api/v1/agent.py`：初始化 `ToolRegistry`
8. **测试回归**：现有功能不受影响

### Step 2: MCP 接口预留（接口定义，暂不连接真实 MCP Server）

1. 创建 `app/agents/mcp/transport.py` — `MCPTransport` 抽象基类
2. 创建 `app/agents/mcp/adapter.py` — `MCPToolAdapter`
3. 创建 `app/agents/mcp/loader.py` — 配置文件加载器（stub 实现）
4. `ToolRegistry` 补全 MCP 相关方法（`register_mcp`, `get_all_schemas` 合并逻辑, `execute` 路由）
5. 编写 MCP transport 的单元测试（mock MCP server）

### Step 3: MCP 真实接入（后续迭代）

1. 实现 `StdioTransport`
2. 实现 `SSETransport`
3. 连接池 / 断线重连 / 心跳
4. 工具权限白名单
5. 审计日志

## 6. 测试策略

严格遵循镜像原则，测试文件结构：

```
tests/
├── agents/
│   ├── test_registry.py             # ToolRegistry 单元测试
│   ├── tools/
│   │   ├── test_anime.py            # anime 工具测试
│   │   ├── test_search.py           # search 工具测试
│   │   ├── test_datetime.py         # 时间工具测试
│   │   ├── test_profile.py          # 画像工具测试
│   │   └── test_base.py             # ToolResult schema 测试
│   └── mcp/
│       ├── test_transport.py        # MCPTransport 抽象测试
│       ├── test_adapter.py          # MCPToolAdapter 测试
│       └── test_integration.py      # ToolRegistry + MCP 集成测试
```

运行命令：
```bash
uv run pytest tests/agents/ -v
```

## 7. 风险与注意事项

| 风险 | 缓解措施 |
|------|---------|
| `bind_tools` 每次用合并 schema 可能导致 LLM context 膨胀 | 可选：按用户/场景按需加载 MCP 工具子集 |
| MCP Server 宕机影响 Agent 响应 | MCP 工具调用加超时 + 熔断，降级为仅本地工具 |
| MCP 工具命名冲突 | 强制 `mcp://server/tool` 命名空间前缀 |
| `ToolNode` 不支持动态工具 | 使用 `get_runtime_tools()` 在 graph 初始化时一次性拉取全量工具，动态注入 ToolNode |

## 8. 自动化测试脚本（pytest）

> 以下所有测试脚本遵循 **AAA（Arrange → Act → Assert）** 原则与**后端镜像原则**。
> 外部依赖（Bangumi API、MCP Server）全部使用 `unittest.mock.AsyncMock` 隔离。
> 测试可直接通过 `uv run pytest tests/agents/ -v` 一键运行。

### 8.1 共享 fixtures — `tests/conftest.py`

```python
"""
tests/conftest.py — 全局共享 fixtures
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_subject_detail():
    """构造一个合法的 SubjectDetail 对象供 anime 工具测试复用"""
    from app.schemas.bangumi import SubjectDetail, StaffInfo, CastInfo
    return SubjectDetail(
        id=12345,
        name="Test Anime",
        name_cn="测试动画",
        summary="A test anime summary.",
        score=8.5,
        rank=42,
        core_staff=[
            StaffInfo(name="Director Name", role="Director (监督)"),
            StaffInfo(name="Studio Name", role="Studio (制作公司)"),
        ],
        main_cast=[
            CastInfo(character_name="Hero", role="主角", cv_names=["CV A"]),
            CastInfo(character_name="Sidekick", role="配角", cv_names=["CV B"]),
        ],
    )


@pytest.fixture
def mock_audience_feedback():
    """构造一个合法的 AudienceFeedback 对象"""
    from app.schemas.bangumi import AudienceFeedback, ShortComment, LongReview
    return AudienceFeedback(
        subject_id=12345,
        comments=[
            ShortComment(user_name="User1", content="Great!", rating=9, created_at="2025-01-01"),
            ShortComment(user_name="User2", content="Not bad.", rating=7, created_at="2025-02-01"),
        ],
        reviews=[
            LongReview(user_name="Reviewer1", title="深度解析", summary="这是一部...", rating=9, created_at="2025-01-15"),
        ],
    )


@pytest.fixture
def mock_staff_list():
    """构造 StaffInfo 列表"""
    from app.schemas.bangumi import StaffInfo
    return [
        StaffInfo(name="Director A", role="Director (监督)"),
        StaffInfo(name="Writer B", role="Script (脚本)"),
    ]


@pytest.fixture
def mock_cast_list():
    """构造 CastInfo 列表"""
    from app.schemas.bangumi import CastInfo
    return [
        CastInfo(character_name="Hero", role="主角", cv_names=["CV X"]),
        CastInfo(character_name="Villain", role="配角", cv_names=["CV Y", "CV Z"]),
    ]


@pytest.fixture
def mock_search_response():
    """构造 Bangumi 搜索 API 返回体"""
    return {
        "total": 5,
        "data": [
            {
                "id": 1, "name": "Anime A", "name_cn": "动画A",
                "summary": "Summary A" * 50,
                "rating": {"score": 8.0, "rank": 10},
                "type": 2, "air_date": "2025-04-01",
                "images": {"large": "http://example.com/a.jpg"},
            },
            {
                "id": 2, "name": "Anime B", "name_cn": "动画B",
                "summary": "Summary B" * 50,
                "rating": {"score": 7.5, "rank": 20},
                "type": 2, "air_date": "2025-04-05",
                "images": {},
            },
        ],
    }


@pytest.fixture
def mock_empty_search_response():
    """构造空搜索结果（触发 fallback）"""
    return {
        "total": 1,
        "data": [
            {
                "id": 1, "name": "Anime A", "name_cn": None,
                "summary": None,
                "rating": {"score": 0, "rank": 0},
                "type": 2, "air_date": "2026-04-01",
                "images": {},
            },
        ],
    }
```

### 8.2 ToolRegistry 核心测试 — `tests/agents/test_registry.py`

```python
"""
tests/agents/test_registry.py
测试 ToolRegistry 的工具注册、查询、执行路由能力
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.tools import tool as langchain_tool


# ─── 假 MCP Transport 实现（仅用于测试） ───
class FakeMCPTransport:
    """模拟 MCP Transport，可在测试中直接注入 ToolRegistry"""
    server_name = "fake-server"

    async def connect(self):
        pass

    async def close(self):
        pass

    async def list_tools(self):
        return [
            {
                "name": "remote_search",
                "description": "Search remote database",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        ]

    async def call_tool(self, name: str, arguments: dict):
        return {"result": f"remote: {name}({arguments})"}


# ─── 假本地 LangChain tool ───
@langchain_tool
async def fake_local_tool(value: int) -> dict:
    """A fake local tool for testing."""
    return {"doubled": value * 2}


@pytest.fixture
def registry():
    """初始化一个已注册本地工具的 ToolRegistry"""
    from app.agents.registry import ToolRegistry
    reg = ToolRegistry()
    reg.register_local(fake_local_tool, namespace="local")
    return reg


# ── 本地工具注册与动态 ToolNode 集成 ──

class TestLocalToolRegistration:
    """本地工具注册与动态 ToolNode（get_runtime_tools）测试"""

    def test_register_local_stores_tool_with_namespace_key(self, registry):
        """注册后的 key 应为 'namespace/tool_name'"""
        assert "local/fake_local_tool" in registry._local_tools

    @pytest.mark.asyncio
    async def test_get_runtime_tools_returns_all_base_tools(self, registry):
        """get_runtime_tools 返回 BaseTool 列表供动态 ToolNode 使用"""
        tools = await registry.get_runtime_tools()
        assert len(tools) == 1
        from langchain_core.tools import BaseTool
        for t in tools:
            assert isinstance(t, BaseTool)

    @pytest.mark.asyncio
    async def test_get_runtime_tools_includes_mcp_tools(self, registry):
        """注册 MCP client 后，get_runtime_tools 返回本地 + MCP 工具"""
        registry.register_mcp(FakeMCPTransport())
        tools = await registry.get_runtime_tools()
        assert len(tools) == 2  # 1 local + 1 MCP


# ── 全 schema 合并 ──

class TestSchemaMerging:
    """get_all_schemas 合并本地 + MCP schema 测试（供 llm.bind_tools）"""

    @pytest.mark.asyncio
    async def test_get_all_schemas_merges_local_and_mcp(self, registry):
        """合并后应包含本地工具 schema + MCP 工具 schema"""
        registry.register_mcp(FakeMCPTransport())
        schemas = await registry.get_all_schemas()
        assert len(schemas) == 2

    @pytest.mark.asyncio
    async def test_get_all_schemas_without_mcp_returns_only_local(self, registry):
        """无 MCP 时只返回本地工具 schema"""
        schemas = await registry.get_all_schemas()
        assert len(schemas) == 1
```

### 8.4 MCP Adapter 测试 — `tests/agents/mcp/test_adapter.py`

```python
"""
测试 MCPToolAdapter 的 schema 转换正确性
"""
import pytest
from app.agents.mcp.adapter import MCPToolAdapter


class TestMCPToolAdapter:

    def test_to_langchain_tool_wraps_mcp_definition_as_base_tool(self):
        """MCP tool definition 被正确包装为 async callable BaseTool"""
        from langchain_core.tools import BaseTool

        mcp_def = {
            "name": "remote_search",
            "description": "Search remote database",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }
        
        fake_transport = type("FakeTransport", (), {
            "call_tool": lambda self, name, args: {"result": f"{name}: {args}"},
            "server_name": "fake",
        })()

        tool = MCPToolAdapter.to_langchain_tool(mcp_def, fake_transport)
        assert isinstance(tool, BaseTool)
        assert tool.name == "remote_search"
        assert tool.description == "Search remote database"

    def test_to_openai_function_returns_valid_schema(self):
        """MCP schema 成功转换为 OpenAI function calling 格式"""
        mcp_def = {
            "name": "calc",
            "description": "Calculate",
            "inputSchema": {
                "type": "object",
                "properties": {"expr": {"type": "string"}},
            },
        }
        schema = MCPToolAdapter.to_openai_function(mcp_def)
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "calc"
```
```

### 8.3 ToolResult Schema 测试 — `tests/agents/tools/test_base.py`

```python
"""
tests/agents/tools/test_base.py
测试 ToolResult 统一返回 schema 的序列化/反序列化与边界情况
"""
import json
import pytest
from pydantic import ValidationError


@pytest.fixture
def ToolResult():
    from app.agents.tools.base import ToolResult
    return ToolResult


class TestToolResultSuccess:
    """成功场景的 ToolResult 测试"""

    def test_success_serialization_includes_all_fields(self, ToolResult):
        """成功时序列化后的 JSON 应包含 success/data/tool_name/duration_ms"""
        tr = ToolResult(
            success=True,
            data={"anime_id": 12345, "name": "Test"},
            tool_name="get_anime_info",
            duration_ms=123.4,
        )
        d = tr.model_dump()
        assert d["success"] is True
        assert d["data"] == {"anime_id": 12345, "name": "Test"}
        assert d["tool_name"] == "get_anime_info"
        assert d["duration_ms"] == 123.4
        assert d["error"] is None
        assert d["error_type"] is None

    def test_success_json_roundtrip(self, ToolResult):
        """序列化为 JSON 再反序列化应无损"""
        tr = ToolResult(
            success=True, data=[1, 2, 3], tool_name="test", duration_ms=1.0
        )
        json_str = json.dumps(tr.model_dump())
        loaded = ToolResult.model_validate(json.loads(json_str))
        assert loaded.success is True
        assert loaded.data == [1, 2, 3]


class TestToolResultError:
    """失败场景的 ToolResult 测试"""

    def test_error_values_are_present_on_failure(self, ToolResult):
        """失败时 error 和 error_type 应有值"""
        tr = ToolResult(
            success=False,
            error="Connection timeout",
            error_type="network",
            tool_name="fetch_anime",
            duration_ms=5001.0,
        )
        d = tr.model_dump()
        assert d["success"] is False
        assert d["error"] == "Connection timeout"
        assert d["error_type"] == "network"
        assert d["data"] is None

    def test_invalid_error_type_raises_validation_error(self, ToolResult):
        """error_type 不在枚举值中时应拒绝"""
        with pytest.raises(ValidationError):
            ToolResult(
                success=False,
                error="oops",
                error_type="unknown_category",
                tool_name="x",
                duration_ms=0,
            )

    @pytest.mark.parametrize("error_type", ["network", "not_found", "invalid_args", "internal"])
    def test_all_valid_error_types_accepted(self, ToolResult, error_type):
        """所有合法 error_type 值应被接受"""
        tr = ToolResult(
            success=False, error="test", error_type=error_type,
            tool_name="x", duration_ms=0,
        )
        assert tr.error_type == error_type


class TestToolResultEdgeCases:
    """边界情况测试"""

    def test_duration_ms_zero_is_valid(self, ToolResult):
        """duration_ms 最小值为 0"""
        tr = ToolResult(success=True, tool_name="t", duration_ms=0)
        assert tr.duration_ms == 0

    def test_data_can_be_none_on_success(self, ToolResult):
        """成功但无返回数据（如 void 操作）"""
        tr = ToolResult(success=True, tool_name="void_tool", duration_ms=1.0)
        assert tr.success is True
        assert tr.data is None

    def test_large_data_payload(self, ToolResult):
        """大数据量 data 字段不丢数据"""
        large_data = {"items": [{"id": i, "name": f"item_{i}"} for i in range(1000)]}
        tr = ToolResult(success=True, data=large_data, tool_name="bulk", duration_ms=100)
        result = tr.model_dump()
        assert len(result["data"]["items"]) == 1000
```

### 8.4 Anime 工具测试 — `tests/agents/tools/test_anime.py`

```python
"""
tests/agents/tools/test_anime.py
测试所有动画相关工具（get_anime_info, fetch_audience_reviews, get_anime_staff, get_anime_cast）
"""
import pytest
from unittest.mock import AsyncMock, patch


# ── get_anime_info ──

class TestGetAnimeInfo:
    """get_anime_info 工具测试"""

    @pytest.mark.asyncio
    async def test_returns_subject_detail_as_dict(self, mock_subject_detail):
        """正常情况应返回 SubjectDetail.model_dump(exclude_none=True) 的结果"""
        with patch("app.agents.tools.anime.fetch_subject_by_id",
                   AsyncMock(return_value=mock_subject_detail)):
            from app.agents.tools.anime import get_anime_info
            result = await get_anime_info.ainvoke({"subject_id": 12345})

        assert isinstance(result, dict)
        assert result["id"] == 12345
        assert result["name"] == "Test Anime"
        assert result["name_cn"] == "测试动画"
        assert result["score"] == 8.5
        assert "core_staff" in result
        assert len(result["core_staff"]) == 2

    @pytest.mark.asyncio
    async def test_exclude_none_fields_are_absent(self, mock_subject_detail):
        """exclude_none=True 应去掉 None 字段"""
        mock_subject_detail.name_cn = None
        with patch("app.agents.tools.anime.fetch_subject_by_id",
                   AsyncMock(return_value=mock_subject_detail)):
            from app.agents.tools.anime import get_anime_info
            result = await get_anime_info.ainvoke({"subject_id": 12345})

        assert "name_cn" not in result

    @pytest.mark.asyncio
    async def test_handles_service_exception_gracefully(self):
        """Service 异常应返回 error dict 而非抛出"""
        with patch("app.agents.tools.anime.fetch_subject_by_id",
                   AsyncMock(side_effect=Exception("Network error"))):
            from app.agents.tools.anime import get_anime_info
            result = await get_anime_info.ainvoke({"subject_id": 99999})

        assert "error" in result
        assert "Network error" in result["error"]


# ── fetch_audience_reviews ──

class TestFetchAudienceReviews:
    """fetch_audience_reviews 工具测试"""

    @pytest.mark.asyncio
    async def test_returns_audience_feedback_as_dict(self, mock_audience_feedback):
        """正常情况应返回 AudienceFeedback.model_dump()"""
        with patch("app.agents.tools.anime.get_audience_feedback",
                   AsyncMock(return_value=mock_audience_feedback)):
            from app.agents.tools.anime import fetch_audience_reviews
            result = await fetch_audience_reviews.ainvoke({"subject_id": 12345})

        assert isinstance(result, dict)
        assert result["subject_id"] == 12345
        assert "comments" in result
        assert len(result["comments"]) == 2
        assert "reviews" in result
        assert len(result["reviews"]) == 1

    @pytest.mark.asyncio
    async def test_handles_service_exception_gracefully(self):
        """Service 异常应返回 error dict"""
        with patch("app.agents.tools.anime.get_audience_feedback",
                   AsyncMock(side_effect=Exception("Timeout"))):
            from app.agents.tools.anime import fetch_audience_reviews
            result = await fetch_audience_reviews.ainvoke({"subject_id": 12345})

        assert "error" in result
        assert "Timeout" in result["error"]


# ── get_anime_staff ──

class TestGetAnimeStaff:
    """get_anime_staff 工具测试"""

    @pytest.mark.asyncio
    async def test_returns_staff_wrapped_in_key(self, mock_staff_list):
        """返回的 dict 中 staff 键包含 StaffInfo 列表"""
        with patch("app.agents.tools.anime.get_staff_info",
                   AsyncMock(return_value=mock_staff_list)):
            from app.agents.tools.anime import get_anime_staff
            result = await get_anime_staff.ainvoke({"subject_id": 12345})

        assert "staff" in result
        assert len(result["staff"]) == 2
        assert result["staff"][0]["name"] == "Director A"
        assert result["staff"][0]["role"] == "Director (监督)"

    @pytest.mark.asyncio
    async def test_handles_service_exception_gracefully(self):
        """Service 异常应返回 error dict"""
        with patch("app.agents.tools.anime.get_staff_info",
                   AsyncMock(side_effect=Exception("DB error"))):
            from app.agents.tools.anime import get_anime_staff
            result = await get_anime_staff.ainvoke({"subject_id": 12345})

        assert "error" in result
        assert "DB error" in result["error"]


# ── get_anime_cast ──

class TestGetAnimeCast:
    """get_anime_cast 工具测试"""

    @pytest.mark.asyncio
    async def test_returns_cast_wrapped_in_key(self, mock_cast_list):
        """返回的 dict 中 cast 键包含 CastInfo 列表"""
        with patch("app.agents.tools.anime.get_cast_info",
                   AsyncMock(return_value=mock_cast_list)):
            from app.agents.tools.anime import get_anime_cast
            result = await get_anime_cast.ainvoke({"subject_id": 12345})

        assert "cast" in result
        assert len(result["cast"]) == 2
        assert result["cast"][0]["character_name"] == "Hero"
        assert result["cast"][0]["cv_names"] == ["CV X"]

    @pytest.mark.asyncio
    async def test_handles_service_exception_gracefully(self):
        """Service 异常应返回 error dict"""
        with patch("app.agents.tools.anime.get_cast_info",
                   AsyncMock(side_effect=Exception("API down"))):
            from app.agents.tools.anime import get_anime_cast
            result = await get_anime_cast.ainvoke({"subject_id": 12345})

        assert "error" in result
        assert "API down" in result["error"]
```

### 8.5 Search 工具测试 — `tests/agents/tools/test_search.py`

```python
"""
tests/agents/tools/test_search.py
测试 search_anime_advanced 工具 — 日期解析 / fallback / 结果简化
"""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime


@pytest.fixture
def current_year():
    return datetime.now().year


class TestSearchByKeyword:
    """按关键词搜索"""

    @pytest.mark.asyncio
    async def test_returns_simplified_results_in_correct_format(self, mock_search_response):
        """搜索结果应被简化为 id/name/score/rank/type/air_date/images 等核心字段"""
        with patch("app.agents.tools.search.search_subjects_advanced",
                   AsyncMock(return_value=mock_search_response)):
            from app.agents.tools.search import search_anime_advanced
            result = await search_anime_advanced.ainvoke({"keyword": "test"})

        assert result["total"] == 5
        assert len(result["results"]) == 2
        item = result["results"][0]
        assert "id" in item
        assert "name" in item
        assert "score" in item
        assert "rank" in item
        assert "type" in item
        assert "air_date" in item

    @pytest.mark.asyncio
    async def test_summary_is_truncated_to_203_chars(self):
        """summary 超过 200 字符应截断并加 '...'"""
        long_summary_response = {
            "total": 1,
            "data": [{
                "id": 1, "name": "Long", "name_cn": None,
                "summary": "X" * 500,
                "rating": {"score": 5.0, "rank": 100},
                "type": 2, "air_date": "2025-01-01",
                "images": {},
            }],
        }
        with patch("app.agents.tools.search.search_subjects_advanced",
                   AsyncMock(return_value=long_summary_response)):
            from app.agents.tools.search import search_anime_advanced
            result = await search_anime_advanced.ainvoke({"keyword": "test"})

        item = result["results"][0]
        assert len(item["summary"]) == 203  # 200 + "..."
        assert item["summary"].endswith("...")

    @pytest.mark.asyncio
    async def test_empty_summary_remains_empty_string(self):
        """无 summary 时应返回空字符串"""
        no_summary_response = {
            "total": 1,
            "data": [{
                "id": 1, "name": "NoSummary", "name_cn": None,
                "summary": None,
                "rating": {"score": 0, "rank": 0},
                "type": 2, "air_date": None,
                "images": {},
            }],
        }
        with patch("app.agents.tools.search.search_subjects_advanced",
                   AsyncMock(return_value=no_summary_response)):
            from app.agents.tools.search import search_anime_advanced
            result = await search_anime_advanced.ainvoke({"keyword": "test"})

        assert result["results"][0]["summary"] == ""


class TestDateRangeParsing:
    """日期范围解析测试"""

    @pytest.mark.asyncio
    async def test_month_only_defaults_to_current_year(self, current_year):
        """只传月份时应默认使用当前年份"""
        with patch("app.agents.tools.search.search_subjects_advanced",
                   AsyncMock(return_value={"total": 0, "data": []})) as mock_search:
            from app.agents.tools.search import search_anime_advanced
            await search_anime_advanced.ainvoke({
                "keyword": "test", "min_month": 4, "max_month": 4
            })

            call_kwargs = mock_search.call_args_list[0].kwargs
            dr = call_kwargs["air_date_ranges"]
            assert f">={current_year}-04-01" in dr
            assert f"<={current_year}-04-30" in dr

    @pytest.mark.asyncio
    async def test_full_date_range_passed_correctly(self):
        """完整年月日范围应正确格式化"""
        with patch("app.agents.tools.search.search_subjects_advanced",
                   AsyncMock(return_value={"total": 0, "data": []})) as mock_search:
            from app.agents.tools.search import search_anime_advanced
            await search_anime_advanced.ainvoke({
                "keyword": "test",
                "min_year": 2024, "min_month": 1, "min_day": 15,
                "max_year": 2024, "max_month": 6, "max_day": 30,
            })

            call_kwargs = mock_search.call_args_list[0].kwargs
            dr = call_kwargs["air_date_ranges"]
            assert ">=2024-01-15" in dr
            assert "<=2024-06-30" in dr

    @pytest.mark.asyncio
    async def test_year_month_without_day_uses_month_bounds(self):
        """年月无日时，开始日为当月 1 号，结束日为当月最后一天"""
        with patch("app.agents.tools.search.search_subjects_advanced",
                   AsyncMock(return_value={"total": 0, "data": []})) as mock_search:
            from app.agents.tools.search import search_anime_advanced
            await search_anime_advanced.ainvoke({
                "keyword": "test", "min_year": 2024, "min_month": 2,
                "max_year": 2024, "max_month": 2,
            })

            call_kwargs = mock_search.call_args_list[0].kwargs
            dr = call_kwargs["air_date_ranges"]
            assert ">=2024-02-01" in dr
            assert "<=2024-02-29" in dr  # 2024 is leap year

    @pytest.mark.asyncio
    async def test_tags_parsed_from_comma_separated_string(self):
        """逗号分隔的 tags 字符串应被正确 split"""
        with patch("app.agents.tools.search.search_subjects_advanced",
                   AsyncMock(return_value={"total": 0, "data": []})) as mock_search:
            from app.agents.tools.search import search_anime_advanced
            await search_anime_advanced.ainvoke({
                "keyword": "test", "tags": "治愈, 热血, 原创"
            })

            call_kwargs = mock_search.call_args_list[0].kwargs
            assert call_kwargs["tags"] == ["治愈", "热血", "原创"]

    @pytest.mark.asyncio
    async def test_rating_ranges_built_correctly(self):
        """评分范围应正确格式化为 >=N 和 <=N"""
        with patch("app.agents.tools.search.search_subjects_advanced",
                   AsyncMock(return_value={"total": 0, "data": []})) as mock_search:
            from app.agents.tools.search import search_anime_advanced
            await search_anime_advanced.ainvoke({
                "keyword": "test", "min_rating": 7.0, "max_rating": 9.5
            })

            call_kwargs = mock_search.call_args_list[0].kwargs
            assert call_kwargs["rating_ranges"] == [">=7.0", "<=9.5"]


class TestFallbackSearch:
    """fallback 搜索逻辑测试"""

    @pytest.mark.asyncio
    async def test_fallback_triggered_when_total_le_3_and_date_range_set(self, mock_empty_search_response):
        """total <= 3 且设置了 air_date_ranges 时应触发 fallback（去掉日期范围再搜）"""
        with patch("app.agents.tools.search.search_subjects_advanced") as mock_search:
            # 第一次调用返回空结果（有日期范围），第二次（无日期范围）返回有数据
            fallback_response = {"total": 10, "data": [
                {"id": 99, "name": "Fallback", "name_cn": "兜底",
                 "summary": "fallback result",
                 "rating": {"score": 8.0, "rank": 5},
                 "type": 2, "air_date": "2025-01-01",
                 "images": {}},
            ]}
            mock_search.side_effect = [mock_empty_search_response, fallback_response]

            from app.agents.tools.search import search_anime_advanced
            result = await search_anime_advanced.ainvoke({
                "keyword": "test", "min_month": 4, "max_month": 4
            })

            assert result["total"] == 10
            assert len(result["results"]) == 1
            assert result["results"][0]["id"] == 99
            assert "note" in result
            assert "已展示相关结果" in result["note"]

    @pytest.mark.asyncio
    async def test_fallback_not_triggered_when_no_date_range(self, mock_empty_search_response):
        """无日期范围时即使结果少也不触发 fallback"""
        with patch("app.agents.tools.search.search_subjects_advanced",
                   AsyncMock(return_value=mock_empty_search_response)):
            from app.agents.tools.search import search_anime_advanced
            result = await search_anime_advanced.ainvoke({"keyword": "test"})

            assert result["total"] == 1
            assert "note" not in result


class TestSearchErrorHandling:
    """搜索异常处理测试"""

    @pytest.mark.asyncio
    async def test_handles_api_exception_gracefully(self):
        """API 异常应返回 error dict 而非崩溃"""
        with patch("app.agents.tools.search.search_subjects_advanced",
                   AsyncMock(side_effect=Exception("500 Server Error"))):
            from app.agents.tools.search import search_anime_advanced
            result = await search_anime_advanced.ainvoke({"keyword": "test"})

        assert "error" in result
        assert "高级搜索失败" in result["error"]
```

### 8.6 Datetime 工具测试 — `tests/agents/tools/test_datetime.py`

```python
"""
tests/agents/tools/test_datetime.py
测试 get_current_time 工具
"""
import pytest
from datetime import datetime
from unittest.mock import patch


class TestGetCurrentTime:
    """get_current_time 工具全面测试"""

    @pytest.mark.asyncio
    async def test_returns_all_expected_keys(self):
        """返回的 dict 应包含所有文档声明的字段"""
        from app.agents.tools.datetime import get_current_time
        result = await get_current_time.ainvoke({})

        expected_keys = {
            "current_time", "current_date", "current_year",
            "current_month", "current_day", "current_hour",
            "current_minute", "current_second", "weekday",
            "weekday_cn", "timestamp", "timezone",
        }
        assert expected_keys.issubset(set(result.keys()))

    @pytest.mark.asyncio
    async def test_current_year_matches_system_year(self):
        """current_year 应与系统年份一致"""
        from app.agents.tools.datetime import get_current_time
        result = await get_current_time.ainvoke({})
        assert result["current_year"] == datetime.now().year

    @pytest.mark.asyncio
    async def test_current_month_between_1_and_12(self):
        """current_month 应在 1-12 之间"""
        from app.agents.tools.datetime import get_current_time
        result = await get_current_time.ainvoke({})
        assert 1 <= result["current_month"] <= 12

    @pytest.mark.asyncio
    async def test_current_day_between_1_and_31(self):
        """current_day 应在 1-31 之间"""
        from app.agents.tools.datetime import get_current_time
        result = await get_current_time.ainvoke({})
        assert 1 <= result["current_day"] <= 31

    @pytest.mark.asyncio
    async def test_weekday_range_0_to_6(self):
        """weekday 应为 0-6（0=周一, 6=周日）"""
        from app.agents.tools.datetime import get_current_time
        result = await get_current_time.ainvoke({})
        assert 0 <= result["weekday"] <= 6

    @pytest.mark.asyncio
    async def test_weekday_cn_is_valid(self):
        """weekday_cn 应为中文星期名称之一"""
        from app.agents.tools.datetime import get_current_time
        result = await get_current_time.ainvoke({})
        valid_weekdays = {"星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"}
        assert result["weekday_cn"] in valid_weekdays

    @pytest.mark.asyncio
    async def test_time_format_matches_pattern(self):
        """current_time 格式应为 YYYY-MM-DD HH:MM:SS"""
        from app.agents.tools.datetime import get_current_time
        result = await get_current_time.ainvoke({})
        import re
        assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", result["current_time"])

    @pytest.mark.asyncio
    async def test_date_format_matches_pattern(self):
        """current_date 格式应为 YYYY-MM-DD"""
        from app.agents.tools.datetime import get_current_time
        result = await get_current_time.ainvoke({})
        import re
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", result["current_date"])

    @pytest.mark.asyncio
    async def test_timestamp_is_positive_float(self):
        """timestamp 应为正浮点数"""
        from app.agents.tools.datetime import get_current_time
        result = await get_current_time.ainvoke({})
        assert isinstance(result["timestamp"], float)
        assert result["timestamp"] > 0

    @pytest.mark.asyncio
    async def test_hour_minute_second_in_valid_range(self):
        """时/分/秒应在合法范围内"""
        from app.agents.tools.datetime import get_current_time
        result = await get_current_time.ainvoke({})
        assert 0 <= result["current_hour"] <= 23
        assert 0 <= result["current_minute"] <= 59
        assert 0 <= result["current_second"] <= 59

    @pytest.mark.asyncio
    async def test_consistency_between_date_and_time(self):
        """current_date 应与 current_time 的前 10 位一致"""
        from app.agents.tools.datetime import get_current_time
        result = await get_current_time.ainvoke({})
        assert result["current_time"].startswith(result["current_date"])
```

### 8.7 Profile 工具测试 — `tests/agents/tools/test_profile.py`

```python
"""
tests/agents/tools/test_profile.py
测试 generate_user_profile_tool 工具
"""
import pytest
from unittest.mock import patch


@pytest.fixture
def valid_collections():
    """构造合法的用户收藏数据"""
    return [
        {
            "collection": {"rate": 8, "type": 2},
            "subject": {
                "id": 1, "name": "Anime A",
                "tags": [{"name": "治愈"}, {"name": "日常"}],
            },
        },
        {
            "collection": {"rate": 9, "type": 2},
            "subject": {
                "id": 2, "name": "Anime B",
                "tags": [{"name": "热血"}, {"name": "战斗"}],
            },
        },
        {
            "collection": {"rate": 7, "type": 2},
            "subject": {
                "id": 3, "name": "Anime C",
                "tags": [{"name": "治愈"}, {"name": "奇幻"}],
            },
        },
    ]


@pytest.fixture
def mock_profile():
    """构造 generate_user_profile 的返回结果"""
    return {
        "llm_summary": {
            "total_rated": 3,
            "taste_dictionary": {
                "治愈": [2, 7.5],
                "日常": [1, 8.0],
                "热血": [1, 9.0],
                "战斗": [1, 9.0],
                "奇幻": [1, 7.0],
            },
        },
        "chart_data": {
            "radar": [{"tag": "热血", "preference": 90}, {"tag": "战斗", "preference": 90}],
            "bar_count": [{"tag": "治愈", "count": 2}],
            "bar_score": [{"tag": "热血", "avg_score": 9.0}],
        },
        "watched_ids": [1, 2, 3],
    }


class TestGenerateUserProfile:
    """generate_user_profile_tool 测试"""

    @pytest.mark.asyncio
    async def test_returns_success_with_profile_data(self, valid_collections, mock_profile):
        """正常情况返回 success=True + profile 三部分数据"""
        with patch("app.agents.tools.profile.generate_user_profile",
                   return_value=mock_profile):
            from app.agents.tools.profile import generate_user_profile_tool
            result = await generate_user_profile_tool.ainvoke({"collections": valid_collections})

        assert result["success"] is True
        assert "profile" in result
        assert result["profile"]["llm_summary"]["total_rated"] == 3
        assert "summary" in result
        assert "3个有效评分" in result["summary"]

    @pytest.mark.asyncio
    async def test_profile_contains_three_sections(self, valid_collections, mock_profile):
        """profile 应包含 llm_summary, chart_data, watched_ids 三部分"""
        with patch("app.agents.tools.profile.generate_user_profile",
                   return_value=mock_profile):
            from app.agents.tools.profile import generate_user_profile_tool
            result = await generate_user_profile_tool.ainvoke({"collections": valid_collections})

        profile = result["profile"]
        assert "llm_summary" in profile
        assert "chart_data" in profile
        assert "watched_ids" in profile

    @pytest.mark.asyncio
    async def test_watched_ids_are_deduplicated(self, valid_collections, mock_profile):
        """watched_ids 应已去重"""
        with patch("app.agents.tools.profile.generate_user_profile",
                   return_value=mock_profile):
            from app.agents.tools.profile import generate_user_profile_tool
            result = await generate_user_profile_tool.ainvoke({"collections": valid_collections})

        ids = result["profile"]["watched_ids"]
        assert len(ids) == len(set(ids))

    @pytest.mark.asyncio
    async def test_handles_service_exception_with_fallback_profile(self, valid_collections):
        """Service 异常应返回 success=False + 空 profile + error"""
        with patch("app.agents.tools.profile.generate_user_profile",
                   side_effect=Exception("Algorithm crash")):
            from app.agents.tools.profile import generate_user_profile_tool
            result = await generate_user_profile_tool.ainvoke({"collections": valid_collections})

        assert result["success"] is False
        assert "error" in result
        assert "Algorithm crash" in result["error"]
        # 即使失败也返回空结构防止上游崩
        fallback = result["profile"]
        assert fallback["llm_summary"]["total_rated"] == 0
        assert fallback["llm_summary"]["taste_dictionary"] == {}
        assert fallback["chart_data"] == {"radar": [], "bar_count": [], "bar_score": []}
        assert fallback["watched_ids"] == []

    @pytest.mark.asyncio
    async def test_empty_collections_handled(self):
        """空收藏列表不应崩溃"""
        with patch("app.agents.tools.profile.generate_user_profile",
                   return_value={
                       "llm_summary": {"total_rated": 0, "taste_dictionary": {}},
                       "chart_data": {"radar": [], "bar_count": [], "bar_score": []},
                       "watched_ids": [],
                   }):
            from app.agents.tools.profile import generate_user_profile_tool
            result = await generate_user_profile_tool.ainvoke({"collections": []})

        assert result["success"] is True
        assert result["profile"]["llm_summary"]["total_rated"] == 0
```

### 8.8 MCP Transport 抽象测试 — `tests/agents/mcp/test_transport.py`

```python
"""
tests/agents/mcp/test_transport.py
测试 MCPTransport 抽象基类的接口约定
"""
import pytest
from abc import ABC, abstractmethod


class TestMCPTransportAbstract:
    """MCPTransport 抽象基类接口约束测试"""

    def test_cannot_instantiate_directly(self):
        """直接实例化抽象类应抛出 TypeError"""
        from app.agents.mcp.transport import MCPTransport
        with pytest.raises(TypeError):
            MCPTransport()

    def test_concrete_subclass_must_implement_connect(self):
        """缺少 connect 的派生类不可实例化"""
        from app.agents.mcp.transport import MCPTransport

        class BadTransport(MCPTransport):
            server_name = "bad"
            async def close(self): pass
            async def list_tools(self): return []
            async def call_tool(self, name, arguments): return {}

        with pytest.raises(TypeError):
            BadTransport()

    def test_concrete_subclass_must_implement_close(self):
        """缺少 close 的派生类不可实例化"""
        from app.agents.mcp.transport import MCPTransport

        class BadTransport(MCPTransport):
            server_name = "bad"
            async def connect(self): pass
            async def list_tools(self): return []
            async def call_tool(self, name, arguments): return {}

        with pytest.raises(TypeError):
            BadTransport()

    def test_concrete_subclass_must_implement_list_tools(self):
        """缺少 list_tools 的派生类不可实例化"""
        from app.agents.mcp.transport import MCPTransport

        class BadTransport(MCPTransport):
            server_name = "bad"
            async def connect(self): pass
            async def close(self): pass
            async def call_tool(self, name, arguments): return {}

        with pytest.raises(TypeError):
            BadTransport()

    def test_concrete_subclass_must_implement_call_tool(self):
        """缺少 call_tool 的派生类不可实例化"""
        from app.agents.mcp.transport import MCPTransport

        class BadTransport(MCPTransport):
            server_name = "bad"
            async def connect(self): pass
            async def close(self): pass
            async def list_tools(self): return []

        with pytest.raises(TypeError):
            BadTransport()

    def test_valid_subclass_is_instantiable(self):
        """全部方法均实现的派生类可正常实例化"""
        from app.agents.mcp.transport import MCPTransport

        class GoodTransport(MCPTransport):
            server_name = "good"
            async def connect(self): pass
            async def close(self): pass
            async def list_tools(self): return []
            async def call_tool(self, name, arguments): return {}

        transport = GoodTransport()
        assert transport.server_name == "good"
        assert isinstance(transport, MCPTransport)
```

### 8.9 MCP Adapter 测试 — `tests/agents/mcp/test_adapter.py`

```python
"""
tests/agents/mcp/test_adapter.py
测试 MCPToolAdapter 的 schema 转换能力
"""
import pytest


SIMPLE_MCP_TOOL = {
    "name": "get_weather",
    "description": "Get weather for a city",
    "inputSchema": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City name"},
        },
        "required": ["city"],
    },
}

COMPLEX_MCP_TOOL = {
    "name": "analyze_data",
    "description": "Analyze dataset with filters",
    "inputSchema": {
        "type": "object",
        "properties": {
            "dataset": {"type": "string", "description": "Dataset ID"},
            "filters": {
                "type": "object",
                "properties": {
                    "from": {"type": "string", "format": "date"},
                    "to": {"type": "string", "format": "date"},
                },
            },
            "aggregate": {"type": "boolean", "default": True},
        },
        "required": ["dataset"],
    },
}


class TestToOpenAIFunction:
    """to_openai_function 转换测试"""

    def test_simple_tool_converts_correctly(self):
        """简单 MCP tool → OpenAI function calling schema"""
        from app.agents.mcp.adapter import MCPToolAdapter

        schema = MCPToolAdapter.to_openai_function(SIMPLE_MCP_TOOL)

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "get_weather"
        assert schema["function"]["description"] == "Get weather for a city"
        params = schema["function"]["parameters"]
        assert params["type"] == "object"
        assert "city" in params["properties"]
        assert params["required"] == ["city"]

    def test_complex_tool_preserves_nested_properties(self):
        """复杂 MCP tool 的嵌套 properties 应被保留"""
        from app.agents.mcp.adapter import MCPToolAdapter

        schema = MCPToolAdapter.to_openai_function(COMPLEX_MCP_TOOL)

        params = schema["function"]["parameters"]
        assert "filters" in params["properties"]
        filters_prop = params["properties"]["filters"]
        assert filters_prop["type"] == "object"
        assert "from" in filters_prop["properties"]
        assert "to" in filters_prop["properties"]

    def test_complex_tool_required_fields_preserved(self):
        """required 字段应被保留"""
        from app.agents.mcp.adapter import MCPToolAdapter

        schema = MCPToolAdapter.to_openai_function(COMPLEX_MCP_TOOL)
        params = schema["function"]["parameters"]
        assert params["required"] == ["dataset"]

    def test_default_values_are_kept(self):
        """参数的 default 值应保留"""
        from app.agents.mcp.adapter import MCPToolAdapter

        schema = MCPToolAdapter.to_openai_function(COMPLEX_MCP_TOOL)
        aggregate = schema["function"]["parameters"]["properties"]["aggregate"]
        assert aggregate["default"] is True


class TestToLangchainTool:
    """to_langchain_tool 转换测试"""

    def test_creates_valid_base_tool_instance(self):
        """返回的对象应是 BaseTool 实例且可调用"""
        from app.agents.mcp.adapter import MCPToolAdapter
        from langchain_core.tools import BaseTool

        class FakeTransport:
            server_name = "test"
            async def call_tool(self, name, arguments):
                return {"temp": 25}

        tool = MCPToolAdapter.to_langchain_tool(SIMPLE_MCP_TOOL, FakeTransport())
        assert isinstance(tool, BaseTool)
        assert tool.name == "mcp/test/get_weather"

    @pytest.mark.asyncio
    async def test_calling_tool_delegates_to_transport(self):
        """调用 LangChain Tool 应委托到 transport.call_tool"""
        from app.agents.mcp.adapter import MCPToolAdapter

        class FakeTransport:
            server_name = "w"
            async def call_tool(self, name, arguments):
                assert name == "get_weather"
                assert arguments == {"city": "Tokyo"}
                return {"temp": 30}

        tool = MCPToolAdapter.to_langchain_tool(SIMPLE_MCP_TOOL, FakeTransport())
        result = await tool.ainvoke({"city": "Tokyo"})
        assert result == {"temp": 30}
```

### 8.10 集成测试 — `tests/agents/mcp/test_integration.py`

```python
"""
tests/agents/mcp/test_integration.py
ToolRegistry + MCP 集成测试：模拟完整工具注册→Schema 合并→执行流程
"""
import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_transport_with_two_tools():
    """构造一个注册了 2 个工具的假 MCP Transport"""
    transport = AsyncMock()
    transport.server_name = "multi-tool-server"
    transport.list_tools.return_value = [
        {
            "name": "fetch_file",
            "description": "Fetch file content",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
        {
            "name": "save_file",
            "description": "Save content to file",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    ]
    transport.call_tool.return_value = {"status": "ok"}
    return transport


class TestFullIntegration:
    """端到端流程集成测试"""

    @pytest.mark.asyncio
    async def test_registry_with_mock_mcp_discoverable(self, mock_transport_with_two_tools):
        """注册 MCP transport 后，get_all_schemas 应可发现 MCP 工具"""
        from app.agents.registry import ToolRegistry
        from langchain_core.tools import tool

        @tool
        async def local_tool(x: int) -> dict:
            return {"result": x * 3}

        registry = ToolRegistry()
        registry.register_local(local_tool)
        registry.register_mcp(mock_transport_with_two_tools)

        schemas = await registry.get_all_schemas()

        local_names = [s["name"] for s in schemas if s["name"].startswith("local/")]
        mcp_names = [s["name"] for s in schemas if s["name"].startswith("mcp/")]

        assert len(local_names) == 1
        assert len(mcp_names) == 2
        assert "mcp/multi-tool-server/fetch_file" in mcp_names
        assert "mcp/multi-tool-server/save_file" in mcp_names

    @pytest.mark.asyncio
    async def test_execute_mcp_tool_via_registry(self, mock_transport_with_two_tools):
        """通过 Registry 执行 MCP 工具应返回正确结果"""
        from app.agents.registry import ToolRegistry

        mock_transport_with_two_tools.call_tool.return_value = {"status": "ok"}

        registry = ToolRegistry()
        registry.register_mcp(mock_transport_with_two_tools)

        result = await registry.execute(
            "mcp/multi-tool-server/fetch_file", {"path": "/data/test.txt"}
        )

        mock_transport_with_two_tools.call_tool.assert_called_once_with(
            "fetch_file", {"path": "/data/test.txt"}
        )
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_schema_merging_preserves_local_tool_integrity(self, mock_transport_with_two_tools):
        """schema 合并后，本地工具的 schema 不应被修改"""
        from app.agents.registry import ToolRegistry
        from langchain_core.tools import tool

        @tool
        async def local_tool(val: str) -> dict:
            return {"echo": val}

        registry = ToolRegistry()
        registry.register_local(local_tool)
        registry.register_mcp(mock_transport_with_two_tools)

        schemas = await registry.get_all_schemas()

        local_schema = next(s for s in schemas if s["name"] == "local/local_tool")
        params = local_schema["parameters"]
        assert params["type"] == "object"
        assert "val" in params["properties"]
        assert params["properties"]["val"]["type"] == "string"

    @pytest.mark.asyncio
    async def test_multiple_mcp_clients_namespace_isolation(self):
        """多个 MCP client 不应相互覆盖"""
        from app.agents.registry import ToolRegistry

        transport_a = AsyncMock()
        transport_a.server_name = "server-a"
        transport_a.list_tools.return_value = [
            {"name": "tool_x", "description": "A", "inputSchema": {"type": "object", "properties": {}}},
        ]
        transport_b = AsyncMock()
        transport_b.server_name = "server-b"
        transport_b.list_tools.return_value = [
            {"name": "tool_x", "description": "B", "inputSchema": {"type": "object", "properties": {}}},
        ]

        registry = ToolRegistry()
        registry.register_mcp(transport_a)
        registry.register_mcp(transport_b)

        schemas = await registry.get_all_schemas()

        mcp_names = [s["name"] for s in schemas if s["name"].startswith("mcp/")]
        assert "mcp/server-a/tool_x" in mcp_names
        assert "mcp/server-b/tool_x" in mcp_names
        assert len(mcp_names) == 2
```

## 9. 一键运行命令

```bash
# 在 backend/ 目录下执行

# 运行全部 agents 相关测试
uv run pytest tests/agents/ -v

# 单独运行某个测试文件
uv run pytest tests/agents/test_registry.py -v

# 运行并显示覆盖率
uv run pytest tests/agents/ -v --cov=app.agents --cov-report=term-missing

# 仅运行 MCP 相关测试
uv run pytest tests/agents/mcp/ -v

# 显示最慢的 10 个测试
uv run pytest tests/agents/ -v --durations=10
```

> **依赖说明**：测试依赖 `pytest-asyncio` 和 `pytest-cov`，需在 `pyproject.toml` 的 `[dependency-groups].dev` 中添加：
> ```toml
> [dependency-groups]
> dev = [
>     "ruff>=0.15.12",
>     "pytest>=8.0.0",
>     "pytest-asyncio>=0.24.0",
>     "pytest-cov>=5.0.0",
> ]
> ```
