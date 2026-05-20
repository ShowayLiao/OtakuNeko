import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import StateGraph, START, END, MessagesState


def _config(thread_id="default"):
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}


def _make_noop_graph():
    def noop(state):
        return {}

    workflow = StateGraph(MessagesState)
    workflow.add_node("n", noop)
    workflow.add_edge(START, "n")
    workflow.add_edge("n", END)
    return workflow


class TestAsyncSqliteSaverCheckpoint:
    """Phase A — checkpoint 持久化基石 测试套件"""

    @pytest.mark.asyncio
    async def test_persistence_across_connections(self, temp_db_path):
        config = _config("thread-1")

        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as saver_a:
            app = _make_noop_graph().compile(checkpointer=saver_a)
            await app.ainvoke({"messages": []}, config)

        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as saver_b:
            state = await saver_b.aget_tuple(config)

        assert state is not None
        assert state.checkpoint["channel_values"] is not None

    @pytest.mark.asyncio
    async def test_completed_steps_accumulate_with_reducer(self, temp_db_path):
        from app.agents.graph import CodingAgentState

        def accumulate_step(state: CodingAgentState):
            return {"completed_steps": ["step-1"]}

        workflow = StateGraph(CodingAgentState)
        workflow.add_node("step", accumulate_step)
        workflow.add_edge(START, "step")
        workflow.add_edge("step", END)

        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as saver:
            app = workflow.compile(checkpointer=saver)
            result = await app.ainvoke(
                {"messages": [], "completed_steps": ["init"], "current_dir": "", "plan": "", "last_terminal_output": ""},
                _config("thread-acc")
            )
            assert "init" in result["completed_steps"]
            assert "step-1" in result["completed_steps"]

    @pytest.mark.asyncio
    async def test_delete_thread_removes_persisted_state(self, temp_db_path):
        thread_id = "thread-del"
        config = _config(thread_id)

        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as saver:
            app = _make_noop_graph().compile(checkpointer=saver)
            await app.ainvoke({"messages": []}, config)

            assert await saver.aget_tuple(config) is not None

            await saver.adelete_thread(thread_id)
            assert await saver.aget_tuple(config) is None

    @pytest.mark.asyncio
    async def test_list_checkpoints_returns_all_threads(self, temp_db_path):
        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as saver:
            app = _make_noop_graph().compile(checkpointer=saver)

            for tid in ("th-a", "th-b", "th-c"):
                await app.ainvoke({"messages": []}, _config(tid))

            configs = [c async for c in saver.alist(None)]
            thread_ids = {c.config["configurable"]["thread_id"] for c in configs}
            assert thread_ids >= {"th-a", "th-b", "th-c"}

    @pytest.mark.asyncio
    async def test_nonexistent_thread_returns_none(self, temp_db_path):
        async with AsyncSqliteSaver.from_conn_string(temp_db_path) as saver:
            result = await saver.aget_tuple(_config("ghost-thread"))
            assert result is None

    @pytest.mark.asyncio
    async def test_auto_create_database_on_nonexistent_path(self, tmp_path):
        import os
        db_dir = tmp_path / "nested" / "db"
        os.makedirs(db_dir, exist_ok=True)
        db_path = str(db_dir / "checkpoints.db")

        async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
            app = _make_noop_graph().compile(checkpointer=saver)
            config = _config("auto-create")
            await app.ainvoke({"messages": []}, config)

            assert os.path.exists(db_path)
            state = await saver.aget_tuple(config)
            assert state is not None
