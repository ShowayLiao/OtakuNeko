from typing import AsyncGenerator, Dict, Any, List
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import InMemorySaver
from app.agents.tools import get_anime_info, fetch_audience_reviews, get_anime_staff, get_anime_cast, search_anime_advanced, get_current_time, generate_user_profile_tool

TOOLS = [get_anime_info, fetch_audience_reviews, get_anime_staff, get_anime_cast, search_anime_advanced, get_current_time, generate_user_profile_tool]


class ChatWorkflow:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
        self.checkpointer = InMemorySaver()
        self.app = self._compile_graph()

    def _compile_graph(self):
        workflow = StateGraph(MessagesState)
        workflow.add_node("agent", self._call_model)
        workflow.add_node("tools", ToolNode(TOOLS))
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges("agent", tools_condition)
        workflow.add_edge("tools", "agent")
        return workflow.compile(checkpointer=self.checkpointer)

    async def _call_model(self, state: MessagesState):
        response = await self.llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    async def stream_chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        thread_id: str = "default"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        self.llm = ChatOpenAI(
            model=model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=temperature,
            streaming=True
        )
        self.llm_with_tools = self.llm.bind_tools(TOOLS)

        config = {"configurable": {"thread_id": thread_id}}

        try:
            async for event in self.app.astream_events({"messages": messages}, config=config, version="v2"):
                event_type = event["event"]

                if event_type == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if hasattr(chunk, "content") and isinstance(chunk.content, str) and chunk.content:
                        yield {"type": "message_chunk", "content": chunk.content}

                elif event_type == "on_tool_start":
                    tool_name = event["name"]
                    inputs = event["data"].get("input", {})
                    yield {"type": "tool_start", "name": tool_name, "inputs": inputs}

                elif event_type == "on_tool_end":
                    tool_name = event["name"]
                    raw_output = event["data"].get("output")

                    if hasattr(raw_output, "content"):
                        output_data = raw_output.content
                    elif isinstance(raw_output, (dict, list, str, int, float, bool, type(None))):
                        output_data = raw_output
                    else:
                        output_data = str(raw_output)

                    yield {"type": "tool_end", "name": tool_name, "output": output_data}

        except Exception as e:
            yield {"type": "error", "detail": f"Graph Execution Error: {str(e)}"}
