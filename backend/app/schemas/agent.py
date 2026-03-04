from typing import List, Optional
from pydantic import BaseModel

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
    # 新增字段，允许为空以兼容旧请求
    prompt_config: Optional[PromptConfig] = None
