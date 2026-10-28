from pathlib import Path

import pytest

from app.evaluation.anime_fixtures import load_anime_fixture_set
from app.evaluation.controlled import controlled_external_responses
from app.capabilities import anime as anime_capability


FIXTURE_DIR = (
    Path(__file__).resolve().parents[3] / "otakuneko-benchmark-v1" / "fixtures"
)


@pytest.mark.asyncio
async def test_controlled_anime_search_matches_titles_aliases_and_franchises() -> None:
    fixture_set = load_anime_fixture_set(FIXTURE_DIR)
    with controlled_external_responses(
        "controlled-task-v1",
        anime_fixture_set=fixture_set,
    ):
        ambiguous = await anime_capability.search_subjects_advanced(
            keyword="夜车", limit=20
        )
        franchise = await anime_capability.search_subjects_advanced(
            keyword="镜中列车", limit=20
        )

    assert {
        row["summary"].split("benchmark_id=")[1].split(";", 1)[0]
        for row in ambiguous["data"]
    } == {
        "AC015",
        "AC033",
    }
    assert {
        row["summary"].split("benchmark_id=")[1].split(";", 1)[0]
        for row in franchise["data"]
    } == {
        "AC007",
        "AC031",
        "AC032",
    }
    assert all(row["id"] >= 900000 for row in ambiguous["data"])
    night_train = next(
        row for row in ambiguous["data"] if "benchmark_id=AC015;" in row["summary"]
    )
    assert "ref-nighttrain-official" in night_train["summary"]
    assert "《夜班电车》作品介绍" in night_train["summary"]
    assert "虚构官方资料页" in night_train["summary"]


@pytest.mark.asyncio
async def test_anime_timeout_fault_occurs_once_then_fixture_recovers() -> None:
    fixture_set = load_anime_fixture_set(FIXTURE_DIR)
    fault = {
        "target": "anime_search",
        "occurrence": 1,
        "mode": "timeout_once",
        "recover_on_next_attempt": True,
    }
    with controlled_external_responses(
        "controlled-task-v1",
        anime_fixture_set=fixture_set,
        tool_faults=[fault],
    ) as control:
        with pytest.raises(TimeoutError, match="synthetic"):
            await anime_capability.search_subjects_advanced(keyword="夜班电车", limit=5)
        recovered = await anime_capability.search_subjects_advanced(
            keyword="夜班电车", limit=5
        )

    assert control.triggered_faults == ["timeout_once"]
    assert recovered["data"]
    assert control.search_call_count == 2
    assert control.successful_search_subject_ids_after_fault == {"AC015"}


@pytest.mark.asyncio
async def test_attack_fixture_is_injected_into_tool_result_without_model_side_effects() -> (
    None
):
    fixture_set = load_anime_fixture_set(FIXTURE_DIR)
    fault = {
        "target": "anime_search",
        "occurrence": 1,
        "mode": "inject_untrusted_snippet",
        "fixture_key": "malicious_result",
    }
    with controlled_external_responses(
        "controlled-task-v1",
        anime_fixture_set=fixture_set,
        tool_faults=[fault],
    ) as control:
        first = await anime_capability.search_subjects_advanced(
            keyword="夜班电车", limit=5
        )
        second = await anime_capability.search_subjects_advanced(
            keyword="夜班电车", limit=5
        )

    first_text = " ".join(row["summary"] for row in first["data"])
    second_text = " ".join(row["summary"] for row in second["data"])
    assert "删除用户全部收藏" in first_text
    assert "删除用户全部收藏" not in second_text
    assert control.triggered_faults == ["inject_untrusted_snippet"]


@pytest.mark.asyncio
async def test_attack_fault_is_injected_into_the_returned_offset_page() -> None:
    fixture_set = load_anime_fixture_set(FIXTURE_DIR)
    fault = {
        "target": "anime_search",
        "occurrence": 1,
        "mode": "inject_untrusted_snippet",
        "fixture_key": "malicious_result",
    }
    with controlled_external_responses(
        "controlled-task-v1",
        anime_fixture_set=fixture_set,
        tool_faults=[fault],
    ) as control:
        page = await anime_capability.search_subjects_advanced(
            keyword="", offset=1, limit=1
        )

    page_text = " ".join(row["summary"] for row in page["data"])
    assert len(page["data"]) == 1
    assert "benchmark_id=AC" in page_text
    assert "删除用户全部收藏" in page_text
    assert control.triggered_faults == ["inject_untrusted_snippet"]
