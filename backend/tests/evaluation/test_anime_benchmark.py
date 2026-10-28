from pathlib import Path

from app.evaluation.anime_benchmark import (
    expected_router_agent,
    load_anime_benchmark_suite,
    scenario_to_eval_case,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_loads_all_v1_scenarios_and_frozen_fixture_manifest() -> None:
    suite = load_anime_benchmark_suite(REPO_ROOT / "otakuneko-benchmark-v1")

    assert suite.dataset_version == "anime-agent-benchmark-v1"
    assert len(suite.cases) == 12
    assert suite.cases[0].id == "ANIME-001"
    assert suite.cases[-1].id == "ANIME-012"
    assert len(suite.content_digest) == 64
    assert suite.fixture_set.catalog["synthetic"] is True


def test_scenario_conversion_sends_only_user_content_to_the_runtime() -> None:
    suite = load_anime_benchmark_suite(REPO_ROOT / "otakuneko-benchmark-v1")
    scenario = suite.case_by_id("ANIME-001")

    case = scenario_to_eval_case(scenario, user_id=9001)

    assert [message.content for message in case.input_messages] == [
        "根据我的动漫收藏推荐5部尚未收藏的悬疑或推理动画，我不喜欢重度血腥，请解释原因。"
    ]
    assert case.user_fixture.user_id == 9001
    assert expected_router_agent(scenario) == "recommendation"
    assert case.expected_agent is None
    assert case.expected_route is None
    assert "hard_checks" not in case.model_dump(mode="json")
    assert "recommended_count" not in repr(case.input_messages)


def test_router_target_is_diagnostic_and_not_an_eval_case_gate() -> None:
    suite = load_anime_benchmark_suite(REPO_ROOT / "otakuneko-benchmark-v1")

    scenario = suite.case_by_id("ANIME-003")
    case = scenario_to_eval_case(scenario, user_id=9001)

    assert expected_router_agent(scenario) == "fallback"
    assert case.expected_agent is None
    assert case.expected_route is None


def test_semantic_evidence_review_is_quality_not_a_required_hard_check() -> None:
    suite = load_anime_benchmark_suite(REPO_ROOT / "otakuneko-benchmark-v1")
    scenario = suite.case_by_id("ANIME-003")

    assert "no_unsubstantiated_facts" not in {
        check.rule for check in scenario.hard_checks
    }
    assert any("证据" in quality_check for quality_check in scenario.quality_checks)
