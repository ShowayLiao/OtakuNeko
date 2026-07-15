from typing import List, Optional, Any
from pydantic import BaseModel
from enum import StrEnum


class StreamEventType(StrEnum):
    THINKING_START = "thinking_start"
    THINKING_CHUNK = "thinking_chunk"
    THINKING_END = "thinking_end"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    MESSAGE_START = "message_start"
    MESSAGE_CHUNK = "message_chunk"
    MESSAGE_END = "message_end"
    REASONING_TRACE = "reasoning_trace"
    INTERRUPT = "interrupt"
    PLAN_UPDATE = "plan_update"
    PROGRESS = "progress"
    ERROR = "error"


class StreamEvent(BaseModel):
    type: StreamEventType
    content: Optional[str] = None
    name: Optional[str] = None
    inputs: Optional[dict] = None
    output: Optional[Any] = None
    status: Optional[str] = None
    duration_ms: Optional[float] = None
    tool_count: Optional[int] = None
    detail: Optional[str] = None
    id: Optional[str] = None
    delta: Optional[str] = None


# 定义前端传来的数据结构
class Message(BaseModel):
    role: str
    content: str

class PromptConfig(BaseModel):
    persona: str = ""
    tone: str = ""
    rules: str = ""

class ChatRequest(BaseModel):
    model: str
    messages: List[Message]
    temperature: float = 0.6
    prompt_config: Optional[PromptConfig] = None
    thread_id: Optional[str] = None
