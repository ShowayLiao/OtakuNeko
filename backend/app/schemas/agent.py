from typing import List
from pydantic import BaseModel

# 定义前端传来的数据结构
class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    model: str = "gpt-3.5-turbo" # 默认模型，前端可以覆盖
    temperature: float = 0.7
