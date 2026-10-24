"""UTC instants survive scheduled-task writes to the existing naive schema."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_task import AgentTaskDef, AgentTaskRun
from app.models.user import User


@pytest.mark.db
@pytest.mark.parametrize("kind", ["definition", "run"])
@pytest.mark.parametrize("aware", [True, False], ids=["offset-input", "legacy-naive"])
async def test_task_timestamp_roundtrip_preserves_utc_instant(
    db_session: AsyncSession, kind: str, aware: bool
) -> None:
    expected = datetime(2030, 1, 2, 3, 4, 5)
    instant = (
        expected.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
        if aware
        else expected
    )
    db_session.add(User(id=501, username="task-timestamp-bindings"))
    await db_session.commit()
    definition = AgentTaskDef(
        user_id=501,
        task_type="timestamp-regression",
        next_run=expected,
        created_at=expected,
        updated_at=expected,
    )
    if kind == "definition":
        definition.next_run = instant
        definition.created_at = instant
        definition.updated_at = instant
        definition.deleted_at = instant
        db_session.add(definition)
        await db_session.commit()
        await db_session.refresh(definition)
        assert definition.next_run == expected
        assert definition.created_at == expected
        assert definition.updated_at == expected
        assert definition.deleted_at == expected
    else:
        db_session.add(definition)
        await db_session.commit()
        assert definition.id is not None
        run = AgentTaskRun(
            task_def_id=definition.id,
            user_id=501,
            scheduled_slot=instant,
            lease_expires_at=instant,
            started_at=instant,
            finished_at=instant,
            created_at=instant,
        )
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)
        assert run.scheduled_slot == expected
        assert run.lease_expires_at == expected
        assert run.started_at == expected
        assert run.finished_at == expected
        assert run.created_at == expected
