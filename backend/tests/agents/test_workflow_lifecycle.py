import pytest

from app.agents.graph import ChatWorkflow
from app.harness.budget import CancellationToken, RunCancellationError


@pytest.mark.asyncio
async def test_workflow_close_releases_checkpointer_connection(temp_db_path):
    workflow = ChatWorkflow(
        api_key="test-key",
        base_url="https://provider.example/v1",
        db_path=temp_db_path,
    )

    await workflow._ensure_checkpointer()
    try:
        connection = workflow._db_connection
        assert connection is not None
        assert workflow.app is not None

        await workflow.close()

        assert workflow._db_connection is None
        assert workflow.checkpointer is None
        assert workflow.app is None

        with pytest.raises(Exception):
            await connection.execute("SELECT 1")
    finally:
        # Keep the red phase from leaving the old implementation's connection
        # alive and hanging the pytest worker.
        if workflow.checkpointer is not None:
            await workflow.checkpointer.conn.close()


@pytest.mark.asyncio
async def test_workflow_binds_checkpoint_path_and_run_thread_identity(temp_db_path):
    workflow = ChatWorkflow(
        api_key="test-key",
        base_url="https://provider.example/v1",
        checkpoint_path=temp_db_path,
        run_id="run-identity",
        thread_id="thread-identity",
    )

    config = workflow._checkpoint_config()

    assert workflow._db_path == temp_db_path
    assert config["configurable"]["thread_id"] == "thread-identity"
    assert config["configurable"]["checkpoint_ns"] == "run-identity"
    assert config["metadata"]["run_id"] == "run-identity"

    await workflow.close()


@pytest.mark.asyncio
async def test_workflow_cancel_token_stops_before_opening_provider(temp_db_path):
    token = CancellationToken()
    token.cancel()
    workflow = ChatWorkflow(
        api_key="test-key",
        base_url="https://provider.example/v1",
        checkpoint_path=temp_db_path,
        run_id="run-cancel",
        thread_id="thread-cancel",
        cancellation=token,
    )

    with pytest.raises(RunCancellationError):
        await anext(
            workflow.stream_chat(
                model="test-model",
                messages=[],
                temperature=0.1,
            )
        )

    assert workflow.checkpointer is None
