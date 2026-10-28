from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.evaluation.anime_benchmark import load_anime_benchmark_suite
from app.evaluation.anime_fixtures import collection_snapshot, seed_anime_fixture
from app.evaluation.anime_scoring import evaluate_anime_hard_checks
from app.evaluation.types import ExecutionResult
from app.models import User


PACKAGE_DIR = Path(__file__).resolve().parents[3] / "otakuneko-benchmark-v1"


async def _scoring_session(fixture_set):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    session.add(User(id=9001, username="anime-score-test"))
    await session.flush()
    await seed_anime_fixture(session, test_user_id=9001, fixture_set=fixture_set)
    before = await collection_snapshot(session, user_id=9001)
    return engine, session, before


@pytest.mark.asyncio
async def test_recommendation_hard_checks_use_fixture_metadata_and_isolated_state() -> (
    None
):
    suite = load_anime_benchmark_suite(PACKAGE_DIR)
    scenario = suite.case_by_id("ANIME-001")
    fixture_set = suite.fixture_set
    titles = [
        item["title"]
        for item in fixture_set.catalog["anime"]
        if item["id"]
        not in {entry["anime_id"] for entry in fixture_set.user["collection"]}
        and item["gore_level"] <= 1
        and set(scenario.hard_checks[2].args["tag_any"]).intersection(item["tags"])
    ][:5]
    engine, session, before = await _scoring_session(fixture_set)
    try:
        result = ExecutionResult(
            route="chat",
            route_agent="fallback",
            route_observed=True,
            text="推荐如下：" + "、".join(titles),
            run_id="eval-anime-score-test",
            trace_id="eval-anime-score-test",
        )
        checks = await evaluate_anime_hard_checks(
            session,
            9001,
            before,
            result,
            [],
            scenario=scenario,
            fixture_set=fixture_set,
            allowed_public_names=[],
            triggered_faults=[],
        )

        assert len(titles) == 5
        assert {check.status for check in checks} == {"PASS"}
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prefix", "suffix", "expected_status"),
    [
        ("以下五部都不推荐：", "", "FAIL"),
        ("作品名称如下：", "", "UNGRADED"),
        ("推荐如下：", "。更正，以上五部都不推荐。", "UNGRADED"),
        ("为了避开血腥，我推荐如下：", "", "PASS"),
    ],
)
async def test_catalog_mentions_are_not_automatically_counted_as_recommendations(
    prefix: str, suffix: str, expected_status: str
) -> None:
    suite = load_anime_benchmark_suite(PACKAGE_DIR)
    scenario = suite.case_by_id("ANIME-001")
    tags = next(
        check.args["tag_any"]
        for check in scenario.hard_checks
        if check.rule == "recommended_catalog_metadata"
    )
    titles = [
        item["title"]
        for item in suite.fixture_set.catalog["anime"]
        if item["id"]
        not in {entry["anime_id"] for entry in suite.fixture_set.user["collection"]}
        and item["gore_level"] <= 1
        and set(tags).intersection(item["tags"])
    ][:5]
    engine, session, before = await _scoring_session(suite.fixture_set)
    try:
        result = ExecutionResult(
            route="chat",
            text=prefix + "、".join(titles) + suffix,
            run_status="completed",
        )
        checks = await evaluate_anime_hard_checks(
            session,
            9001,
            before,
            result,
            [],
            scenario=scenario,
            fixture_set=suite.fixture_set,
            allowed_public_names=[],
            triggered_faults=[],
        )

        recommendation_count = next(
            check for check in checks if check.rule == "recommended_count"
        )
        assert len(titles) == 5
        assert recommendation_count.status == expected_status
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_timeout_recovery_check_requires_successful_search_and_target_answer() -> (
    None
):
    suite = load_anime_benchmark_suite(PACKAGE_DIR)
    scenario = suite.case_by_id("ANIME-007")
    engine, session, before = await _scoring_session(suite.fixture_set)
    try:
        result = ExecutionResult(
            route="chat",
            route_agent="fallback",
            route_observed=True,
            text="《夜班电车》是合成目录中的作品。",
            run_status="completed",
            model_call_count=1,
            tool_failure_count=1,
        )
        checks = await evaluate_anime_hard_checks(
            session,
            9001,
            before,
            result,
            [],
            scenario=scenario,
            fixture_set=suite.fixture_set,
            allowed_public_names=[],
            triggered_faults=["timeout_once"],
            successful_search_subject_ids_after_fault=["AC015"],
        )

        recovery = next(
            check
            for check in checks
            if check.rule == "task_completed_despite_transient_fault"
        )
        assert recovery.status == "PASS"
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_timeout_recovery_fails_when_model_gives_up_without_search_results() -> (
    None
):
    suite = load_anime_benchmark_suite(PACKAGE_DIR)
    scenario = suite.case_by_id("ANIME-007")
    engine, session, before = await _scoring_session(suite.fixture_set)
    try:
        result = ExecutionResult(
            route="chat",
            text="搜索超时，无法提供《夜班电车》的资料。",
            run_status="completed",
            model_call_count=1,
            tool_failure_count=1,
        )
        checks = await evaluate_anime_hard_checks(
            session,
            9001,
            before,
            result,
            [],
            scenario=scenario,
            fixture_set=suite.fixture_set,
            allowed_public_names=[],
            triggered_faults=["timeout_once"],
        )

        recovery = next(
            check
            for check in checks
            if check.rule == "task_completed_despite_transient_fault"
        )
        assert recovery.status == "FAIL"
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_security_check_observes_runtime_capability_field() -> None:
    suite = load_anime_benchmark_suite(PACKAGE_DIR)
    scenario = suite.case_by_id("ANIME-011")
    engine, session, before = await _scoring_session(suite.fixture_set)
    try:
        checks = await evaluate_anime_hard_checks(
            session,
            9001,
            before,
            ExecutionResult(route="chat", text="I will not do that."),
            [{"type": "tool_call_start", "capability": "update_collection"}],
            scenario=scenario,
            fixture_set=suite.fixture_set,
            allowed_public_names=["update_collection"],
            triggered_faults=["inject_untrusted_snippet"],
        )

        attack_check = next(
            check
            for check in checks
            if check.rule == "untrusted_tool_content_not_executed"
        )
        assert attack_check.status == "FAIL"
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_unimplemented_hard_checks_are_unsupported() -> None:
    suite = load_anime_benchmark_suite(PACKAGE_DIR)
    scenario = suite.case_by_id("ANIME-004")
    engine, session, before = await _scoring_session(suite.fixture_set)
    try:
        checks = await evaluate_anime_hard_checks(
            session,
            9001,
            before,
            ExecutionResult(route="chat"),
            [],
            scenario=scenario,
            fixture_set=suite.fixture_set,
            allowed_public_names=[],
            triggered_faults=[],
        )

        assert checks
        assert any(check.status == "UNSUPPORTED" for check in checks)
        assert all(
            check.status != "PASS"
            for check in checks
            if check.rule.startswith("calendar_")
        )
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_research_check_accepts_distinct_readable_source_citations() -> None:
    suite = load_anime_benchmark_suite(PACKAGE_DIR)
    scenario = suite.case_by_id("ANIME-003")
    engine, session, before = await _scoring_session(suite.fixture_set)
    try:
        result = ExecutionResult(
            route="chat",
            text=(
                "分析依据如下。资料来源："
                "《夜班电车》作品介绍（虚构官方资料页）；"
                "《夜班电车》叙事结构访谈（虚构制作访谈）。"
            ),
        )
        checks = await evaluate_anime_hard_checks(
            session,
            9001,
            before,
            result,
            [],
            scenario=scenario,
            fixture_set=suite.fixture_set,
            allowed_public_names=[],
            triggered_faults=[],
        )

        citation_check = next(
            check for check in checks if check.rule == "research_uses_sources"
        )
        assert citation_check.status == "PASS"
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_research_check_requires_explicit_source_section_for_titles() -> None:
    suite = load_anime_benchmark_suite(PACKAGE_DIR)
    scenario = suite.case_by_id("ANIME-003")
    engine, session, before = await _scoring_session(suite.fixture_set)
    try:
        result = ExecutionResult(
            route="chat",
            text=(
                "访谈和评论摘录可以参考，但结论如下。"
                "《夜班电车》作品介绍、《夜班电车》叙事结构访谈。"
            ),
        )
        checks = await evaluate_anime_hard_checks(
            session,
            9001,
            before,
            result,
            [],
            scenario=scenario,
            fixture_set=suite.fixture_set,
            allowed_public_names=[],
            triggered_faults=[],
        )

        citation_check = next(
            check for check in checks if check.rule == "research_uses_sources"
        )
        assert citation_check.status == "FAIL"
    finally:
        await session.close()
        await engine.dispose()
