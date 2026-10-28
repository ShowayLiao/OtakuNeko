from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.capabilities.factory import build_capability_registry
from app.evaluation.entrypoint import run_headless_case
from app.evaluation.types import EvalCase
from app.harness.budget import DeadlineExceededError, RunBudget, RunCancellationError
from app.harness.model_types import ModelCallResult, ModelUsage, ProviderFailureDetails


def _case(case_id: str, prompt: str) -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": case_id,
            "category": "routing",
            "input_messages": [{"role": "user", "content": prompt}],
            "user_fixture": {"user_id": 9511},
            "assertions": {
                "response_schema": "text",
                "max_latency_ms": 10_000,
                "max_calls": 5,
            },
            "fixtures": {"events": [{"type": "message_chunk", "content": "done"}]},
        }
    )


class RouteAwareGateway:
    provider = "deepseek"
    model = "deepseek-flash"

    def __init__(self, *, route_output: str, route_status: str = "completed") -> None:
        self.route_output = route_output
        self.route_status = route_status
        self.route_requests: list[dict[str, object]] = []
        self.infer_calls: list[str] = []

    async def classify_route(self, **kwargs) -> ModelCallResult:
        self.route_requests.append(kwargs)
        failure = None
        if self.route_status == "failed":
            failure = ProviderFailureDetails(
                category="authentication",
                provider_error_code="auth",
                exception_type="AuthenticationError",
                call_stage="request",
                http_status=401,
            )
        return ModelCallResult(
            provider=self.provider,
            model=self.model,
            operation="route",
            call_id=str(kwargs.get("call_id") or "route-call"),
            trace_id=kwargs.get("trace_id"),
            status=self.route_status,
            text=self.route_output,
            usage=ModelUsage(
                prompt_tokens=11,
                completion_tokens=4,
                total_tokens=15,
                latency_ms=8,
            ),
            error_code="auth" if failure else None,
            provider_failure=failure,
        )

    async def infer(self, **kwargs) -> ModelCallResult:
        self.infer_calls.append(str(kwargs.get("goal", "")))
        return ModelCallResult(
            provider=self.provider,
            model=self.model,
            operation="complete",
            call_id="task-call",
            trace_id=kwargs.get("trace_id"),
            status="completed",
            text=json.dumps(
                {
                    "schema_version": "v1",
                    "decision_id": "task-finish",
                    "action": "finish",
                    "content": "handled by the task model",
                }
            ),
            usage=ModelUsage(
                prompt_tokens=13,
                completion_tokens=5,
                total_tokens=18,
                latency_ms=12,
            ),
        )


@pytest.mark.asyncio
async def test_model_router_calls_same_gateway_before_task_model_and_counts_usage(
    tmp_path: Path,
) -> None:
    gateway = RouteAwareGateway(
        route_output=json.dumps({"selected_agent": "fallback", "confidence": 0.98})
    )

    result, events = await run_headless_case(
        _case("model-router-order", "请推荐一些动画，但这次由主模型处理。"),
        registry=build_capability_registry(),
        model_gateway=gateway,
        model="deepseek-flash",
        fail_on_run_failure=True,
        transcript_dir=tmp_path,
        routing_enabled=True,
        routing_version="model-v1",
        run_budget=RunBudget(max_model_calls=2),
    )

    assert result.run_status == "completed"
    assert result.route_agent == "fallback"
    assert result.model_call_count == 2
    assert len(gateway.route_requests) == 1
    assert gateway.route_requests[0]["goal"] == "请推荐一些动画，但这次由主模型处理。"
    assert gateway.route_requests[0]["allowed_agents"] == ["recommendation", "fallback"]
    assert len(gateway.infer_calls) == 1
    assert [
        event.get("operation") for event in events if event.get("type") == "model_call"
    ] == [
        "route",
        None,
    ]
    assert (
        next(event for event in events if event.get("type") == "route_decision")[
            "agent"
        ]
        == "fallback"
    )
    trace_path = tmp_path / "traces" / "model-router-order.trace.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    trace_events = [event for step in trace["steps"] for event in step["events"]]
    route_trace = next(
        event
        for event in trace_events
        if event["event_type"] == "model_call"
        and event["data"].get("operation") == "route"
    )
    assert route_trace["data"]["call_role"] == "router"
    assert route_trace["provider"] == "deepseek"
    assert route_trace["model"] == "deepseek-flash"
    assert route_trace["usage"]["prompt_tokens"] == 11


@pytest.mark.asyncio
async def test_model_router_call_consumes_the_run_model_call_budget() -> None:
    gateway = RouteAwareGateway(
        route_output=json.dumps({"selected_agent": "fallback", "confidence": 0.9})
    )

    result, events = await run_headless_case(
        _case("model-router-budget", "Explain anime recommendations."),
        registry=build_capability_registry(),
        model_gateway=gateway,
        model="deepseek-flash",
        fail_on_run_failure=False,
        routing_enabled=True,
        routing_version="model-v1",
        run_budget=RunBudget(max_model_calls=1),
    )

    assert result.run_status == "failed"
    assert result.termination_reason == "max_model_calls"
    assert len(gateway.route_requests) == 1
    assert gateway.infer_calls == []
    assert sum(event.get("type") == "model_call" for event in events) == 1


@pytest.mark.asyncio
async def test_model_router_provider_error_fails_case_without_task_fallback() -> None:
    gateway = RouteAwareGateway(route_output="", route_status="failed")

    result, events = await run_headless_case(
        _case("model-router-provider-error", "Recommend anime."),
        registry=build_capability_registry(),
        model_gateway=gateway,
        model="deepseek-flash",
        fail_on_run_failure=False,
        routing_enabled=True,
        routing_version="model-v1",
        run_budget=RunBudget(max_model_calls=2),
    )

    route_call = next(event for event in events if event.get("type") == "model_call")
    route_decision = next(
        event for event in events if event.get("type") == "route_decision"
    )
    assert result.run_status == "failed"
    assert result.terminal_error_code == "provider_error"
    assert result.provider_failure is not None
    assert result.provider_failure["http_status"] == 401
    assert route_call["operation"] == "route"
    assert route_call["provider_failure"]["call_stage"] == "request"
    assert route_decision["router_status"] == "provider_error"
    assert gateway.infer_calls == []


@pytest.mark.parametrize(
    ("control_error", "expected_status"),
    [
        (DeadlineExceededError(), "timeout"),
        (RunCancellationError(), "cancelled"),
    ],
)
@pytest.mark.asyncio
async def test_model_router_control_exit_is_traced_with_its_actual_status(
    tmp_path: Path,
    control_error: BaseException,
    expected_status: str,
) -> None:
    class ControlErrorGateway(RouteAwareGateway):
        async def classify_route(self, **kwargs) -> ModelCallResult:
            self.route_requests.append(kwargs)
            raise control_error

    gateway = ControlErrorGateway(route_output="unused")
    result, events = await run_headless_case(
        _case(f"model-router-{expected_status}", "Recommend anime."),
        registry=build_capability_registry(),
        model_gateway=gateway,
        model="deepseek-flash",
        fail_on_run_failure=False,
        transcript_dir=tmp_path,
        routing_enabled=True,
        routing_version="model-v1",
    )

    route_call = next(event for event in events if event.get("operation") == "route")
    route_decision = next(
        event for event in events if event.get("type") == "route_decision"
    )
    assert result.run_status == expected_status
    assert route_call["status"] == expected_status
    assert route_call["call_role"] == "router"
    assert route_decision["router_status"] == expected_status
    assert result.model_call_count == 1
    assert gateway.infer_calls == []
