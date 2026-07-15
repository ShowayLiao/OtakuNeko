from abc import ABC, abstractmethod
from typing import List, Dict, Any


class MCPTransport(ABC):
    """MCP 传输层抽象基类"""

    server_name: str

    @abstractmethod
    async def connect(self) -> None:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...

    @abstractmethod
    async def list_tools(self) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        ...
