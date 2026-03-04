import os
import json
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from openai import AsyncOpenAI
from app.schemas.agent import ChatRequest
from app.agents.graph import ChatWorkflow

router = APIRouter()

def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    # 核心：从 Header 获取前端传来的配置 (BYOK)
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
):
    # 本地调试时的 fallback (可选)
    api_key = x_api_key or os.getenv("OPENAI_API_KEY")
    base_url = x_base_url or "https://api.openai.com/v1"

    if not api_key and "localhost" not in base_url: # Ollama 不需要 Key
        raise HTTPException(status_code=401, detail="Missing API Key")

    # 处理消息格式
    formatted_messages = []
    
    # 如果提供了 prompt_config，生成系统提示
    if request.prompt_config:
        system_content = f"[角色设定]\n{request.prompt_config.persona}\n\n[语气风格]\n{request.prompt_config.tone}\n\n[行为准则]\n{request.prompt_config.rules}"
        formatted_messages.append({"role": "system", "content": system_content})

    # 过滤掉前端传来的旧 system 消息，只保留 user 和 assistant 的历史记录
    for msg in request.messages:
        if msg.role != "system":
            formatted_messages.append(msg.model_dump())

    # 定义流式生成器
    async def stream_generator():
        try:
            # 实例化 ChatWorkflow
            workflow = ChatWorkflow(api_key=api_key, base_url=base_url)
            
            # 调用 stream_chat 生成流
            async for chunk_data in workflow.stream_chat(
                model=request.model,
                messages=formatted_messages,
                temperature=request.temperature
            ):
                event_type = chunk_data.get("type", "message")
                yield format_sse(event=event_type, data=chunk_data)

        except Exception as e:
            yield format_sse(event="error", data={"detail": str(e)})

    # 返回流式响应
    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@router.get("/models/check")
async def check_connection(
    provider: str,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint")
):
    try:
        # 1. 针对不同厂商选择检查方式
        if provider == "ollama":
            # Ollama 的特殊检查路径
            async with httpx.AsyncClient() as client:
                # 检查标签列表
                resp = await client.get(f"{x_base_url}/api/tags", timeout=5.0)
                if resp.status_code == 200: return {"status": "ok"}
        
        # 2. 通用 OpenAI 兼容检查 (DeepSeek, OpenAI, Qwen 等)
        client = AsyncOpenAI(api_key=x_api_key, base_url=x_base_url)
        
        # 尝试获取模型列表（验证 Key 和 Endpoint 的最快方式）
        await client.models.list()
        
        return {"status": "ok", "message": "Connection successful"}

    except Exception as e:
        # 返回具体的错误信息供前端展示
        raise HTTPException(status_code=400, detail=str(e))
