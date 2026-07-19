import pytest

from app.agents.graph import ChatWorkflow


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
