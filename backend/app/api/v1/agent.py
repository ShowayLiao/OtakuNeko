import os
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
import httpx
from app.schemas.agent import ChatRequest

router = APIRouter()

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

    # 初始化 OpenAI 客户端 (无状态，每次请求新建)
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    # 定义流式生成器
    async def stream_generator():
        try:
            stream = await client.chat.completions.create(
                model=request.model,
                messages=[msg.model_dump() for msg in request.messages],
                stream=True,
                temperature=request.temperature,
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    # SSE 格式：可以直接发纯文本，或者发 JSON 字符串
                    # 这里直接发内容，前端接收起来最简单
                    yield chunk.choices[0].delta.content

        except Exception as e:
            yield f"\n[Error: {str(e)}]"

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
