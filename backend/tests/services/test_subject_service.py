from __future__ import annotations

import asyncio

import pytest

from app.schemas.subject import SubjectSearchBase
from app.services import subject_service


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled_side", ["local", "remote"])
async def test_search_mixed_propagates_cancellation(monkeypatch, cancelled_side):
    async def cancelled_search(*_args, **_kwargs):
        raise asyncio.CancelledError()

    async def empty_remote_search(*_args, **_kwargs):
        return subject_service.UnifiedList(total=0, items=[])

    monkeypatch.setattr(
        subject_service,
        "search_subject_by_name",
        cancelled_search if cancelled_side == "local" else empty_remote_search,
    )
    monkeypatch.setattr(
        subject_service,
        "search_subject_cloud",
        cancelled_search if cancelled_side == "remote" else empty_remote_search,
    )

    with pytest.raises(asyncio.CancelledError):
        await subject_service.search_mixed(
            db=None,
            search_data=SubjectSearchBase(keyword="anime"),
        )
