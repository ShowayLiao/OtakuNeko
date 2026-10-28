from pathlib import Path
import json

import pytest

from app.evaluation import anime_live
from app.evaluation import adapter, entrypoint
from app.evaluation.adapter import ProductionRuntimeTarget
from app.evaluation.anime_benchmark import (
    load_anime_benchmark_suite,
    scenario_to_eval_case,
)
from app.evaluation.anime_live import (
    main,
    _parse_args,
    _not_run_report,
    assemble_anime_report,
    select_scenarios,
    write_anime_markdown_report,
)
from app.evaluation.reporting import report_payload
from app.evaluation.config import load_config
from app.evaluation.types import (
    AgentMetadata,
    CaseResult,
    EvalReport,
    ExecutionResult,
    RunUsage,
)


PACKAGE_DIR = Path(__file__).resolve().parents[3] / "otakuneko-benchmark-v1"


def test_regression_selection_reports_all_twelve_and_runs_only_supported_cases() -> (
    None
):
    suite = load_anime_benchmark_suite(PACKAGE_DIR)

    selected, dataset = select_scenarios(suite, suite_name="regression")

    assert len(selected) == 12
    assert len(dataset.cases) == 8
    assert "ANIME-005" in {case.id for case in dataset.cases}
    progress_case = next(case for case in dataset.cases if case.id == "ANIME-005")
    assert progress_case.approvals[0].action == "update_collection"


def test_router_diagnostic_does_not_change_final_task_success() -> None:
    suite = load_anime_benchmark_suite(PACKAGE_DIR)
    scenario = suite.case_by_id("ANIME-001")
    run_report = EvalReport(
        task="ANIME-AGENT-BENCHMARK-V1",
        dataset_version=suite.dataset_version,
        config_name="test",
        code_revision="test",
        agent=AgentMetadata(name="test", model="live", provider="test"),
        cases=[
            CaseResult(
                case_id="ANIME-001",
                category="recommendation",
                passed=True,
                functional_passed=True,
                benchmark_status="PASS",
                route_agent="fallback",
                route_observed=True,
            )
        ],
    )

    report = assemble_anime_report(
        run_report,
        suite,
        selected_ids={scenario.id},
        suite_name="custom",
        repeats=1,
        run_id="test-run",
    )

    result = report.cases[0]
    assert result.passed is True
    assert result.router_expected_agent == "recommendation"
    assert result.router_match is False
    assert report.aggregates["loop_success_rate"] == 1.0
    assert report.aggregates["pass_at_1"] == 1.0
    assert report.aggregates["all_repeats_success_rate"] == 1.0
    assert report.aggregates["router_accuracy"] == 0.0
    assert report.status == "PASS"
    assert all(case.benchmark_status == "SKIP" for case in report.cases[1:])


def test_missing_selected_live_case_counts_as_execution_failure() -> None:
    suite = load_anime_benchmark_suite(PACKAGE_DIR)
    run_report = EvalReport(
        task="ANIME-AGENT-BENCHMARK-V1",
        dataset_version=suite.dataset_version,
        config_name="test",
        code_revision="test",
        agent=AgentMetadata(name="test", model="live", provider="test"),
    )

    report = assemble_anime_report(
        run_report,
        suite,
        selected_ids={"ANIME-001"},
        suite_name="custom",
        repeats=1,
        run_id="missing-case-test",
    )

    assert report.cases[0].benchmark_status == "ERROR"
    assert report.aggregates["loop_run_count"] == 1
    assert report.aggregates["loop_success_rate"] == 0.0
    assert report.aggregates["execution_error_rate"] == 1.0
    assert report.aggregates["router_accuracy"] is None
    assert report.aggregates["functional_pass_rate"] is None
    assert report.aggregates["functional_not_run_count"] == 11.0
    assert report.aggregates["functional_execution_failure_count"] == 1.0


def test_live_aggregates_distinguish_not_run_execution_and_assertion_failures() -> None:
    suite = load_anime_benchmark_suite(PACKAGE_DIR)
    run_report = EvalReport(
        task="ANIME-AGENT-BENCHMARK-V1",
        dataset_version=suite.dataset_version,
        config_name="test",
        code_revision="test",
        agent=AgentMetadata(name="test", model="live", provider="test"),
        cases=[
            CaseResult(
                case_id="ANIME-001",
                category="recommendation",
                passed=False,
                functional_passed=False,
                benchmark_status="FAIL",
                outcome="functional_failure",
            ),
            CaseResult(
                case_id="ANIME-002",
                category="recommendation",
                passed=False,
                functional_passed=None,
                benchmark_status="ERROR",
                outcome="execution_error",
            ),
        ],
    )

    report = assemble_anime_report(
        run_report,
        suite,
        selected_ids={"ANIME-001", "ANIME-002"},
        suite_name="custom",
        repeats=1,
        run_id="functional-states-test",
    )

    assert [report.cases[0].functional_status, report.cases[1].functional_status] == [
        "ASSERTION_FAILED",
        "EXECUTION_FAILED",
    ]
    assert report.aggregates["functional_pass_rate"] == 0.0
    assert report.aggregates["functional_not_run_count"] == 10.0
    assert report.aggregates["functional_execution_failure_count"] == 1.0
    assert report.aggregates["functional_assertion_failure_count"] == 1.0


def test_provider_network_reachability_is_recorded_in_environment() -> None:
    suite = load_anime_benchmark_suite(PACKAGE_DIR)
    reached_report = EvalReport(
        task="ANIME-AGENT-BENCHMARK-V1",
        dataset_version=suite.dataset_version,
        config_name="test",
        code_revision="test",
        agent=AgentMetadata(name="test", model="live", provider="test"),
        cases=[
            CaseResult(
                case_id="ANIME-003",
                category="anime_knowledge",
                passed=True,
                functional_passed=True,
                benchmark_status="PASS",
                outcome="passed",
                run_status="completed",
                usage=RunUsage(model_calls=2),
            )
        ],
    )
    blocked_report = EvalReport(
        task="ANIME-AGENT-BENCHMARK-V1",
        dataset_version=suite.dataset_version,
        config_name="test",
        code_revision="test",
        agent=AgentMetadata(name="test", model="live", provider="test"),
        cases=[
            CaseResult(
                case_id="ANIME-003",
                category="anime_knowledge",
                passed=False,
                functional_passed=None,
                functional_status="EXECUTION_FAILED",
                benchmark_status="ERROR",
                outcome="provider_error",
                run_status="failed",
                provider_failure={"category": "network_blocked", "http_status": None},
                usage=RunUsage(model_calls=1),
            )
        ],
    )
    failed_after_model_report = EvalReport(
        task="ANIME-AGENT-BENCHMARK-V1",
        dataset_version=suite.dataset_version,
        config_name="test",
        code_revision="test",
        agent=AgentMetadata(name="test", model="live", provider="test"),
        cases=[
            CaseResult(
                case_id="ANIME-007",
                category="recovery",
                passed=False,
                functional_passed=None,
                functional_status="EXECUTION_FAILED",
                benchmark_status="ERROR",
                outcome="execution_error",
                run_status="failed",
                usage=RunUsage(model_calls=1),
            )
        ],
    )

    reached = assemble_anime_report(
        reached_report,
        suite,
        selected_ids={"ANIME-003"},
        suite_name="custom",
        repeats=1,
        run_id="network-reached-test",
    )
    blocked = assemble_anime_report(
        blocked_report,
        suite,
        selected_ids={"ANIME-003"},
        suite_name="custom",
        repeats=1,
        run_id="network-blocked-test",
    )
    failed_after_model = assemble_anime_report(
        failed_after_model_report,
        suite,
        selected_ids={"ANIME-007"},
        suite_name="custom",
        repeats=1,
        run_id="network-reached-execution-failure-test",
    )

    assert reached.environment["provider_network_reachability"] == "reachable"
    assert blocked.environment["provider_network_reachability"] == "blocked"
    assert (
        failed_after_model.environment["provider_network_reachability"] == "reachable"
    )


def test_auto_baseline_requires_exact_dataset_and_verifies_legacy_run_ids(
    tmp_path: Path,
) -> None:
    from app.evaluation.trend import build_baseline

    current_report = EvalReport(
        task="ANIME-AGENT-BENCHMARK-V1",
        dataset_version="anime-v1/smoke",
        dataset_digest="dataset-digest",
        config_name="test",
        code_revision="current-code",
        agent=AgentMetadata(name="test", model="test-model", provider="test"),
        cases=[
            CaseResult(
                case_id="ANIME-001",
                category="recommendation",
                passed=True,
                functional_passed=True,
                benchmark_status="PASS",
                run_id="current-run",
                outcome="passed",
            )
        ],
    )
    current = build_baseline(current_report, repeats=1)
    history_dir = tmp_path / "historical-run"
    history_dir.mkdir()
    historical = current.model_copy(update={"executed_runs": 0})
    (history_dir / "current-baseline.json").write_text(
        historical.model_dump_json(), encoding="utf-8"
    )
    (history_dir / "run-manifest.json").write_text(
        json.dumps(
            {"run_index": [{"case_id": "ANIME-001", "run_id": "verified-runtime-run"}]}
        ),
        encoding="utf-8",
    )

    selected = anime_live._auto_select_baseline(
        tmp_path,
        current,
        exclude_run_dir=tmp_path / "current-run",
    )

    assert selected is not None
    baseline_path, baseline = selected
    assert baseline_path == history_dir / "current-baseline.json"
    assert baseline.executed_runs == 1

    incompatible = current.model_copy(update={"dataset_digest": "other-dataset"})
    assert (
        anime_live._auto_select_baseline(
            tmp_path,
            incompatible,
            exclude_run_dir=tmp_path / "current-run",
        )
        is None
    )


def test_cli_single_repeat_joins_the_unexpanded_case_id(
    monkeypatch, tmp_path: Path
) -> None:
    async def fake_run_evaluation(config, dataset, _target, judge=None):
        assert judge is None
        case = dataset.cases[0]
        return EvalReport(
            task="ANIME-AGENT-BENCHMARK-V1",
            dataset_version=dataset.dataset_version,
            dataset_digest=dataset.content_digest,
            config_name=config.name,
            code_revision="test-revision",
            agent=AgentMetadata(name="test", model="test", provider="test"),
            prompt_version="test-prompt",
            cases=[
                CaseResult(
                    case_id=case.id,
                    category="recommendation",
                    passed=True,
                    functional_passed=True,
                    benchmark_status="PASS",
                    route_agent="recommendation",
                    route_observed=True,
                    step_count=2,
                    usage=RunUsage(
                        model_calls=1,
                        model_tokens=20,
                        latency_ms=10,
                    ),
                )
            ],
        )

    monkeypatch.setattr(
        anime_live, "build_real_model_target", lambda *_a, **_k: object()
    )
    monkeypatch.setattr(anime_live, "run_evaluation", fake_run_evaluation)

    exit_code = anime_live.main(
        [
            "--provider",
            "real",
            "--isolated",
            "--case",
            "ANIME-001",
            "--output-dir",
            str(tmp_path),
            "--run-id",
            "single-repeat",
        ]
    )

    report = json.loads(
        (tmp_path / "single-repeat" / "report.json").read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert report["aggregates"]["loop_run_count"] == 1
    assert report["aggregates"]["loop_success_rate"] == 1
    assert report["cases"][0]["case_id"] == "ANIME-001"
    assert report["baseline_comparison"]["status"] == "unavailable"
    assert report["baseline_comparison"]["improvements"] == []


@pytest.mark.asyncio
async def test_live_target_preserves_partial_usage_after_runtime_validation_error(
    monkeypatch, tmp_path: Path
) -> None:
    suite = load_anime_benchmark_suite(PACKAGE_DIR)
    case = scenario_to_eval_case(suite.case_by_id("ANIME-005"), user_id=98001)
    config = load_config("evals/config/anime-agent-benchmark-v1.yaml")
    gateway = type("Gateway", (), {"close": lambda self: None})()

    async def _close(self):
        return None

    gateway.close = _close.__get__(gateway)

    monkeypatch.setattr(adapter, "OpenAIModelGateway", lambda **_kwargs: gateway)

    async def fail_after_runtime(*_args, **kwargs):
        assert kwargs.get("approvals") == case.approvals
        transcript_path = Path(kwargs["transcript_dir"]) / f"{case.id}.json"
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text(
            json.dumps(
                {
                    "case_id": case.id,
                    "result": ExecutionResult(
                        route="chat",
                        text="synthetic partial result",
                        run_id="partial-run",
                        trace_id="partial-run",
                        model_call_count=3,
                        model_tokens=300,
                        prompt_tokens=200,
                        completion_tokens=100,
                        estimated_cost_unknown_count=1,
                    ).model_dump(mode="json"),
                    "trace": {"total_duration_ms": 42.5},
                }
            ),
            encoding="utf-8",
        )
        raise RuntimeError("validation failed after Runtime completion")

    monkeypatch.setattr(entrypoint, "run_headless_case", fail_after_runtime)
    target = ProductionRuntimeTarget(
        config,
        api_key="test-only-key",
        base_url="https://api.openai.com/v1",
        transcript_dir=tmp_path,
        allowed_public_names=config.controlled.allowed_capabilities,
        external_fixtures=config.controlled.external_fixtures,
        anime_benchmark_suite=suite,
    )

    result = await target.evaluate(case)

    assert result.run_status == "failed"
    assert result.benchmark_status == "ERROR"
    assert result.task_success is False
    assert result.terminal_error_code == "evaluation_error"
    assert result.model_call_count == 3
    assert result.model_tokens == 300
    assert result.latency_ms == 42.5


def test_missing_provider_report_contains_no_scores(tmp_path: Path) -> None:
    suite = load_anime_benchmark_suite(PACKAGE_DIR)
    selected, _dataset = select_scenarios(suite, suite_name="regression")
    config = type(
        "Config",
        (),
        {
            "name": "test",
            "agent": AgentMetadata(name="test", model="live", provider="test"),
            "routing": type(
                "Routing", (), {"enabled": True, "version": "keyword-v1"}
            )(),
        },
    )()

    report = _not_run_report(
        config,
        suite,
        selected_ids=selected,
        suite_name="regression",
        reason="real Provider credentials are not configured",
        run_id="test-run",
    )
    payload = report_payload(report)

    assert payload["status"] == "NOT_RUN"
    assert payload["aggregates"] == {}
    assert payload["passed_count"] is None
    assert payload["failed_count"] is None
    assert payload["pass_rate"] is None
    assert any(case.benchmark_status == "UNSUPPORTED" for case in report.cases)

    markdown_path = write_anime_markdown_report(report, tmp_path / "report.md")
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "NOT_RUN" in markdown
    assert "UNSUPPORTED" in markdown
    assert "ANIME-012" in markdown


def test_live_cli_requires_explicit_real_provider_and_isolation() -> None:
    with pytest.raises(SystemExit):
        _parse_args([])

    args = _parse_args(["--provider", "real", "--isolated"])

    assert args.provider == "real"
    assert args.isolated is True


def test_router_gate_failure_fails_the_live_command(
    monkeypatch, tmp_path: Path
) -> None:
    async def fake_run_evaluation(config, dataset, target, judge=None):
        assert config.thresholds == {}
        return EvalReport(
            task="ANIME-AGENT-BENCHMARK-V1",
            dataset_version=dataset.dataset_version,
            dataset_digest=dataset.content_digest,
            config_name=config.name,
            code_revision="test-revision",
            agent=config.agent,
            prompt_version="test-prompt",
            aggregates={"latency_ms": 1.0},
            cases=[
                CaseResult(
                    case_id="ANIME-001",
                    category="recommendation",
                    passed=True,
                    functional_passed=True,
                    benchmark_status="PASS",
                    route_agent="fallback",
                    route_observed=True,
                )
            ],
        )

    monkeypatch.setattr(
        "app.evaluation.anime_live.build_real_model_target", lambda *_a, **_k: object()
    )
    monkeypatch.setattr("app.evaluation.anime_live.run_evaluation", fake_run_evaluation)

    exit_code = main(
        [
            "--provider",
            "real",
            "--isolated",
            "--suite",
            "smoke",
            "--case",
            "ANIME-001",
            "--run-id",
            "router-gate-test",
            "--output-dir",
            str(tmp_path / "runs"),
        ]
    )

    report_path = tmp_path / "runs" / "router-gate-test" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["status"] == "FAIL"
    assert any("router_accuracy" in failure for failure in report["gate_failures"])


def test_unregistered_router_version_fails_before_any_provider_call() -> None:
    config = load_config("evals/config/anime-agent-benchmark-v1.yaml")
    config.routing.version = "unregistered-router"

    with pytest.raises(ValueError, match="unsupported specialist router version"):
        ProductionRuntimeTarget(config, api_key="test-key-not-used")
