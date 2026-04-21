from typing import AsyncGenerator, Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessageChunk
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from app.agents.tools import get_anime_info, fetch_audience_reviews, get_anime_staff, get_anime_cast, search_anime_advanced, get_current_time, generate_user_profile_tool

class ChatWorkflow:
    """
    基于 LangGraph 的工作流引擎。
    包含 agent 节点和 tools 节点，支持工具调用。
    """
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url

    async def stream_chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float
    ) -> AsyncGenerator[Dict[str, Any], None]:
        
        # 1. 初始化 LangChain 的 ChatOpenAI 模型
        llm = ChatOpenAI(
            model=model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=temperature,
            streaming=True # 开启流式支持
        )

        # 2. 定义工具列表
        tools = [get_anime_info, fetch_audience_reviews, get_anime_staff, get_anime_cast, search_anime_advanced, get_current_time, generate_user_profile_tool]

        # 3. 绑定工具到大模型
        llm_with_tools = llm.bind_tools(tools)

        # 4. 定义处理节点
        async def call_model(state: MessagesState):
            # 将对话历史传给大模型
            response = await llm_with_tools.ainvoke(state["messages"])
            # 返回新的消息追加到状态中
            return {"messages": [response]}

        # 5. 构建 LangGraph 图
        workflow = StateGraph(MessagesState)
        workflow.add_node("agent", call_model)
        workflow.add_node("tools", ToolNode(tools))
        
        # 定义图的边
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges("agent", tools_condition)
        workflow.add_edge("tools", "agent")
        workflow.add_edge("agent", END)

        # 编译图
        app = workflow.compile()

        # 6. 运行图并流式输出事件
        try:
            # 使用 astream_events 来捕获图事件
            async for event in app.astream_events({"messages": messages}, version="v2"):
                event_type = event["event"]
                
                # 处理模型流输出 (普通文本打字机效果)
                if event_type == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    # 必须通过属性访问 (.content)，并且过滤掉空内容(比如生成工具调用时的隐藏 token)
                    if hasattr(chunk, "content") and isinstance(chunk.content, str) and chunk.content:
                        yield {"type": "message_chunk", "content": chunk.content}
                
                # 处理工具调用开始
                elif event_type == "on_tool_start":
                    tool_name = event["name"]
                    # 这里的 input 确实是字典，可以用 .get
                    inputs = event["data"].get("input", {})
                    yield {"type": "tool_start", "name": tool_name, "inputs": inputs}
                
                # 处理工具调用结束
                elif event_type == "on_tool_end":
                    tool_name = event["name"]
                    raw_output = event["data"].get("output")
                    
                    # === 新增：处理 ToolMessage 的序列化 ===
                    # 如果输出是 LangChain 的 Message 对象，提取它的 content
                    if hasattr(raw_output, "content"):
                        output_data = raw_output.content
                    # 兼容：如果是普通可序列化的类型，直接保留
                    elif isinstance(raw_output, (dict, list, str, int, float, bool, type(None))):
                        output_data = raw_output
                    # 兜底：强制转成字符串，防止 json.dumps 再次崩溃
                    else:
                        output_data = str(raw_output)
                        
                    yield {"type": "tool_end", "name": tool_name, "output": output_data}
                    
        except Exception as e:
            # 这里的报错会被抛给 agent.py，包装成 SSE 的 error 事件
            yield {"type": "error", "detail": f"Graph Execution Error: {str(e)}"}
