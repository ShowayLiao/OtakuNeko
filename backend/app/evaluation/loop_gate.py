"""Deterministic, offline certification of the Runtime-owned Agent loop."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.evaluation.entrypoint import isolated_headless_session
from app.evaluation.offline import offline_network
from app.evaluation.scripted_llm import (
    ExpectedMessage,
    ObservationExpectation,
    ScriptedLLM,
    ScriptedObservation,
    ScriptedStep,
)
from app.harness.budget import CancellationToken
from app.harness.checkpoint import SqliteCheckpointStore
from app.harness.contracts import ExecutionContext
from app.harness.execution import build_runtime
from app.harness.policy import Approval
from app.harness.task import AgentTask
from app.trace.sql_store import SqlTraceStore


CASE_IDS = (
    "multi_step",
    "read_recovery",
    "policy_denied",
    "approval_resume",
    "cancelled_before_start",
    "cancelled_inflight",
    "unknown_write",
)
_READ = "loop_gate.read"
_WAIT = "loop_gate.wait"
_WRITE = "loop_gate.write"
_REPLAY_SCHEMA = 1


def _revision() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


class _LoopCapability(BaseCapability):
    name = "loop_gate"
    description = "Synthetic offline loop gate capability"

    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        self.executions: list[dict[str, Any]] = []
        self.sink: list[str] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    def actions(self) -> list[ActionDescriptor]:
        read_schema = {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        }
        write_schema = {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "idempotency_key": {"type": "string"},
            },
            "required": ["value", "idempotency_key"],
            "additionalProperties": False,
        }
        output_schema = {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }
        return [
            ActionDescriptor(
                name="read",
                public_name=_READ,
                description=self.description,
                input_schema=read_schema,
                output_schema=output_schema,
                requires_auth=True,
                retry_class="read_only",
            ),
            ActionDescriptor(
                name="wait",
                public_name=_WAIT,
                description=self.description,
                input_schema=read_schema,
                output_schema=output_schema,
                requires_auth=True,
                retry_class="read_only",
            ),
            ActionDescriptor(
                name="write",
                public_name=_WRITE,
                description=self.description,
                input_schema=write_schema,
                output_schema={"type": "object"},
                requires_auth=True,
                is_side_effect=True,
                approval_required=True,
                idempotency_mode="required",
            ),
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        arguments = dict(kwargs)
        record: dict[str, Any] = {
            "action": action,
            "arguments": arguments,
            "result": None,
        }
        self.executions.append(record)
        try:
            if action == "wait":
                self.started.set()
                await self.release.wait()
            if action == "read":
                if self.case_id == "read_recovery" and arguments.get("value") == "bad":
                    result = CapabilityResult.fail(
                        "Synthetic read failure", error_type="read_failure"
                    ).to_dict()
                else:
                    result = CapabilityResult.ok(
                        value=f"observed:{arguments['value']}"
                    ).to_dict()
            elif action == "write":
                self.sink.append(str(arguments["value"]))
                if self.case_id == "unknown_write":
                    result = CapabilityResult.fail(
                        "Synthetic outcome requires review",
                        error_type="attention_required",
                    ).to_dict()
                else:
                    result = CapabilityResult.ok(
                        appended=str(arguments["value"])
                    ).to_dict()
            else:
                result = CapabilityResult.ok(value="released").to_dict()
            record["result"] = result
            return result
        except asyncio.CancelledError:
            record["result"] = {"status": "cancelled"}
            raise


class _RecordingScriptedLLM(ScriptedLLM):
    def __init__(self, steps: list[ScriptedStep]) -> None:
        super().__init__(steps, provider="loop-gate", model="loop-gate-v1")
        self.decisions: list[dict[str, Any]] = []

    async def infer(self, **kwargs: Any):
        result = await super().infer(**kwargs)
        if result.status == "completed":
            try:
                decision = result.decision or json.loads(result.text)
                if isinstance(decision, dict):
                    self.decisions.append(decision)
            except (TypeError, json.JSONDecodeError):
                pass
        return result


def _decision(observation, action: str, index: int, **fields: Any) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "decision_id": f"{observation.run_id}-decision-{index}",
        "run_id": observation.run_id,
        "action": action,
        **fields,
    }


def _invoke(
    observation, capability: str, value: str, index: int, *, key: str | None = None
):
    arguments: dict[str, Any] = {"value": value}
    if key is not None:
        arguments["idempotency_key"] = key
    return _decision(
        observation,
        "invoke",
        index,
        capability=capability,
        capability_version="v1",
        arguments=arguments,
    )


def _respond(observation, text: str, index: int):
    return _decision(observation, "respond", index, content=text)


def _steps(
    case_id: str, frozen_decisions: list[dict[str, Any]] | None = None
) -> list[ScriptedStep]:
    first = ObservationExpectation(tool_results=0)
    if frozen_decisions is not None:
        if case_id == "multi_step":
            expectations = [
                first,
                ObservationExpectation(
                    tool_results=1,
                    last_tool_result={"safe_output": {"value": "observed:seed"}},
                ),
                ObservationExpectation(tool_results=2),
            ]
        elif case_id == "read_recovery":
            expectations = [
                first,
                ObservationExpectation(
                    tool_results=1,
                    history_contains=(
                        ExpectedMessage("user", "untrusted capability result data"),
                    ),
                ),
                ObservationExpectation(tool_results=2),
            ]
        elif case_id == "approval_resume":
            expectations = [first, ObservationExpectation(tool_results=1)]
        elif case_id == "unknown_write":
            expectations = [first, first]
        else:
            expectations = [first] * len(frozen_decisions)
        counts: dict[str, int] = {}
        steps = []
        for index, frozen in enumerate(frozen_decisions):
            original_run = str(frozen["run_id"])
            counts[original_run] = counts.get(original_run, 0) + 1
            local_index = counts[original_run]
            decision = {
                key: value
                for key, value in frozen.items()
                if key not in {"run_id", "decision_id"}
            }

            def replay_decision(
                observation: ScriptedObservation,
                value: dict[str, Any] = decision,
                local: int = local_index,
            ) -> dict[str, Any]:
                return {
                    **value,
                    "run_id": observation.run_id,
                    "decision_id": f"{observation.run_id}-decision-{local}",
                }

            steps.append(
                ScriptedStep(decision=replay_decision, expect=expectations[index])
            )
        return steps
    if case_id == "multi_step":
        return [
            ScriptedStep(
                decision=lambda obs: _invoke(obs, _READ, "seed", 1), expect=first
            ),
            ScriptedStep(
                decision=lambda obs: _invoke(
                    obs,
                    _READ,
                    str((obs.last_tool_result or {})["safe_output"]["value"]),
                    2,
                ),
                expect=ObservationExpectation(
                    tool_results=1,
                    last_tool_result={"safe_output": {"value": "observed:seed"}},
                ),
            ),
            ScriptedStep(
                decision=lambda obs: _respond(obs, "two observations", 3),
                expect=ObservationExpectation(tool_results=2),
            ),
        ]
    if case_id == "read_recovery":
        return [
            ScriptedStep(
                decision=lambda obs: _invoke(obs, _READ, "bad", 1), expect=first
            ),
            ScriptedStep(
                decision=lambda obs: _invoke(obs, _READ, "good", 2),
                expect=ObservationExpectation(
                    tool_results=1,
                    history_contains=(
                        ExpectedMessage("user", "untrusted capability result data"),
                    ),
                ),
            ),
            ScriptedStep(
                decision=lambda obs: _respond(obs, "recovered", 3),
                expect=ObservationExpectation(tool_results=2),
            ),
        ]
    if case_id == "policy_denied":
        return [
            ScriptedStep(
                decision=lambda obs: _invoke(obs, _READ, "denied", 1), expect=first
            )
        ]
    if case_id == "approval_resume":
        return [
            ScriptedStep(
                decision=lambda obs: _invoke(
                    obs, _WRITE, "approved", 1, key="approval-key"
                ),
                expect=first,
            ),
            ScriptedStep(
                decision=lambda obs: _respond(obs, "approved and resumed", 2),
                expect=ObservationExpectation(tool_results=1),
            ),
        ]
    if case_id == "cancelled_inflight":
        return [
            ScriptedStep(
                decision=lambda obs: _invoke(obs, _WAIT, "pause", 1), expect=first
            )
        ]
    if case_id == "unknown_write":
        return [
            ScriptedStep(
                decision=lambda obs: _invoke(
                    obs, _WRITE, "uncertain", 1, key="unknown-key"
                ),
                expect=first,
            )
            for _ in range(2)
        ]
    return []


def _json_safe(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _observation_snapshot(gateway: _RecordingScriptedLLM) -> list[dict[str, Any]]:
    snapshots = []
    for item in gateway.calls:
        context = item.context or {}
        snapshots.append(
            {
                "call_number": item.call_number,
                "run_id": item.run_id,
                "trace_id": item.trace_id,
                "goal": item.goal,
                "messages": [
                    {"role": message.get("role"), "content": message.get("content")}
                    for message in item.messages
                    if message.get("role") in {"user", "assistant"}
                ],
                "context_identity": {
                    key: context[key]
                    for key in ("run_id", "trace_id", "principal_id")
                    if key in context
                },
                "tool_result_count": len(item.tool_results),
            }
        )
    return snapshots


def _actual_decisions(gateway: _RecordingScriptedLLM, events: list[dict[str, Any]]):
    emitted = [event for event in events if event.get("type") == "model_decision"]
    decisions = []
    for index, decision in enumerate(gateway.decisions):
        assistant_json = []
        if index < len(gateway.calls):
            for message in gateway.calls[index].messages:
                if message.get("role") != "assistant" or not isinstance(
                    message.get("content"), str
                ):
                    continue
                try:
                    parsed = json.loads(message["content"])
                    if (
                        isinstance(parsed, dict)
                        and parsed.get("schema_version") == "v1"
                    ):
                        assistant_json.append(parsed)
                except json.JSONDecodeError:
                    continue
        decisions.append(
            {
                "call_number": index + 1,
                "assistant_json_in_history": assistant_json,
                "proposed_decision": decision,
                "emitted_event": next(
                    (
                        {
                            key: event[key]
                            for key in (
                                "type",
                                "run_id",
                                "sequence",
                                "decision_id",
                                "action",
                                "capability",
                                "capability_version",
                                "argument_keys",
                            )
                            if key in event
                        }
                        for event in emitted
                        if event.get("decision_id") == decision.get("decision_id")
                    ),
                    None,
                ),
            }
        )
    return decisions


async def _execute_case(
    case_id: str,
    output_dir: Path,
    *,
    frozen_decisions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    run_ids = [
        f"loop-gate-{case_id}-{uuid4().hex}"
        for _ in range(2 if case_id == "unknown_write" else 1)
    ]
    gateway = _RecordingScriptedLLM(_steps(case_id, frozen_decisions))
    capability = _LoopCapability(case_id)
    registry = CapabilityRegistry()
    registry.register(capability)
    all_events: list[dict[str, Any]] = []
    run_facts: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    expected_terminal = {
        "multi_step": "completed",
        "read_recovery": "completed",
        "policy_denied": "failed",
        "approval_resume": "completed",
        "cancelled_before_start": "cancelled",
        "cancelled_inflight": "cancelled",
        "unknown_write": "failed",
    }[case_id]
    error_category = None
    run_ids_seen: list[str] = []

    try:
        with offline_network():
            async with isolated_headless_session(41) as (session, user):
                trace_store = SqlTraceStore(session)
                checkpoint_context: Any = None
                checkpoint_store = None
                if case_id == "approval_resume":
                    checkpoint_context = tempfile.TemporaryDirectory()
                    checkpoint_store = SqliteCheckpointStore(
                        str(Path(checkpoint_context.name) / "checkpoint.db")
                    )
                runtime = build_runtime(
                    session=session,
                    user=user,
                    registry=registry,
                    model_gateway=gateway,
                    trace_store=trace_store,
                    allow_side_effects=case_id in {"approval_resume", "unknown_write"},
                    checkpoint_store=checkpoint_store,
                )
                for index, run_id in enumerate(run_ids):
                    run_ids_seen.append(run_id)
                    messages = [
                        {
                            "role": "user",
                            "content": f"Synthetic {case_id} request {index + 1}",
                        }
                    ]
                    task = AgentTask(
                        user_id=user.id,
                        goal=f"Synthetic offline loop case: {case_id}",
                        task_metadata={
                            "model": "loop-gate-v1",
                            "run_id": run_id,
                            "trace_id": run_id,
                            "thread_id": run_id,
                            "messages": messages,
                        },
                    )
                    allowed = {_READ, _WAIT, _WRITE}
                    if case_id == "policy_denied":
                        allowed = {"loop_gate.other"}
                    context = ExecutionContext(
                        principal_id=user.id,
                        run_id=run_id,
                        trace_id=run_id,
                        thread_id=run_id,
                        capability_allowlist=frozenset(allowed),
                    )
                    token = CancellationToken()
                    if case_id == "cancelled_before_start":
                        token.cancel()
                    if runtime.run_store is None or runtime.event_store is None:
                        raise AssertionError("durable runtime stores unavailable")

                    async def stream(
                        approval: Approval | None,
                        capture: list[dict[str, Any]],
                    ) -> None:
                        async for event in runtime.stream_decision(
                            task, context=context, cancellation=token, approval=approval
                        ):
                            capture.append(event)

                    events: list[dict[str, Any]] = []
                    resumed: list[dict[str, Any]] = []
                    writes_before_resume = len(capability.sink)
                    run: Any = None
                    persisted = []
                    persisted_terminals = []
                    trace: Any = None
                    terminal: dict[str, Any] = {}
                    try:
                        if case_id == "cancelled_inflight":
                            task_stream = asyncio.create_task(stream(None, events))
                            try:
                                await asyncio.wait_for(
                                    capability.started.wait(), timeout=5
                                )
                                token.cancel()
                                await task_stream
                            finally:
                                if not task_stream.done():
                                    task_stream.cancel()
                                try:
                                    await task_stream
                                except BaseException:
                                    pass
                        else:
                            approval = (
                                Approval(
                                    approval_id=f"approval:{run_id}",
                                    principal_id=user.id,
                                    action="write",
                                )
                                if case_id == "unknown_write"
                                else None
                            )
                            await stream(approval, events)
                        writes_before_resume = len(capability.sink)
                        if case_id == "approval_resume":
                            await stream(
                                Approval(
                                    approval_id=f"approval:{run_id}-decision-1",
                                    principal_id=user.id,
                                    action="write",
                                ),
                                resumed,
                            )
                    finally:
                        per_run_events = [*events, *resumed]
                        all_events.extend(per_run_events)
                        terminal_events = [
                            event
                            for event in per_run_events
                            if event.get("run_id") == run_id
                            and event.get("type", "").startswith("run_")
                        ]
                        terminal = terminal_events[-1] if terminal_events else {}
                        run = await runtime.run_store.get(run_id, user_id=user.id)
                        persisted = await runtime.event_store.list_after(run_id)
                        persisted_terminals = [
                            event
                            for event in persisted
                            if event.event_type
                            in {"run.succeeded", "run.failed", "run.cancelled"}
                        ]
                        run_facts.append(
                            {
                                "run_id": run_id,
                                "status": run.status if run is not None else "missing",
                                "terminal": terminal,
                            }
                        )
                        for event in persisted:
                            try:
                                payload = json.loads(event.payload_json or "{}")
                            except json.JSONDecodeError:
                                payload = {}
                            all_events.append(
                                {
                                    "run_id": event.run_id,
                                    "sequence": event.sequence,
                                    "event_type": event.event_type,
                                    "invocation_id": event.invocation_id,
                                    "payload": payload,
                                }
                            )
                        trace = await trace_store.query(run_id, user_id=user.id)
                        if trace is not None:
                            traces.append(trace.model_dump(mode="json"))

                    terminal = terminal_events[-1] if terminal_events else {}
                    terminal_type = terminal.get("type")
                    terminal_status = {
                        "run_completed": "completed",
                        "run_failed": "failed",
                        "run_cancelled": "cancelled",
                        "run_timeout": "timeout",
                    }.get(terminal_type if isinstance(terminal_type, str) else "")
                    expected_reason = (
                        "attention_required" if case_id == "unknown_write" else None
                    )
                    if terminal_status != expected_terminal or (
                        expected_reason
                        and terminal.get("termination_reason") != expected_reason
                    ):
                        raise AssertionError("unexpected terminal outcome")
                    if run is None or len(persisted_terminals) != 1:
                        raise AssertionError("canonical terminal persistence mismatch")
                    if case_id == "approval_resume" and (
                        writes_before_resume != 0 or len(capability.sink) != 1
                    ):
                        raise AssertionError(
                            "approval did not gate the synthetic write"
                        )
                    if trace is None:
                        raise AssertionError("trace persistence missing")
                    expected_trace_status = {
                        "completed": "completed",
                        "failed": "failed",
                        "cancelled": "cancelled",
                    }.get(terminal_status)
                    if trace.status != expected_trace_status:
                        raise AssertionError("trace terminal status mismatch")
                if case_id == "approval_resume" and capability.sink != ["approved"]:
                    raise AssertionError("approval resume did not execute exactly once")
                if case_id == "unknown_write" and capability.sink != ["uncertain"]:
                    raise AssertionError(
                        "idempotency replay duplicated the synthetic sink"
                    )
                if case_id == "cancelled_inflight" and (
                    capability.sink
                    or len(capability.executions) != 1
                    or capability.executions[0]["action"] != "wait"
                    or capability.executions[0]["result"] != {"status": "cancelled"}
                ):
                    raise AssertionError(
                        "in-flight cancellation did not stop capability execution"
                    )
                if case_id == "read_recovery" and [
                    item["arguments"].get("value") for item in capability.executions
                ] != ["bad", "good"]:
                    raise AssertionError(
                        "read retry did not change the failed arguments"
                    )
                if case_id == "multi_step" and [
                    item["arguments"].get("value") for item in capability.executions
                ] != ["seed", "observed:seed"]:
                    raise AssertionError("second read did not use observed safe output")
                if case_id == "policy_denied" and capability.executions:
                    raise AssertionError("policy-denied capability executed")
    except Exception as exc:
        error_category = type(exc).__name__

    # Export a bounded, synthetic-only bundle even when execution or an
    # assertion failed. No exception text or provider payload is exported.
    terminal = next(
        (fact["terminal"] for fact in reversed(run_facts) if fact.get("terminal")), {}
    )
    calls_expected = sum(step.expect is not None for step in gateway.steps)
    observation_summary = gateway.observation_summary()
    passed = (
        error_category is None
        and len(run_facts) == len(run_ids)
        and all(
            fact.get("status")
            == ("succeeded" if expected_terminal == "completed" else expected_terminal)
            for fact in run_facts
        )
    )
    bundle = {
        "schema_version": _REPLAY_SCHEMA,
        "case_id": case_id,
        "revision": _revision(),
        "run_id": run_ids_seen[0] if run_ids_seen else run_ids[0],
        "trace_id": run_ids_seen[0] if run_ids_seen else run_ids[0],
        "runs": run_facts,
        "input_messages": [
            {"role": "user", "content": f"Synthetic {case_id} request {index + 1}"}
            for index in range(len(run_ids))
        ],
        "decisions": _actual_decisions(gateway, all_events),
        "capability_executions": _json_safe(capability.executions),
        "persisted_events": [event for event in all_events if "event_type" in event],
        "trace": traces[0] if len(traces) == 1 else traces,
        "model_observations": _observation_snapshot(gateway),
        "terminal": {
            "status": terminal.get("type", "").removeprefix("run_") or "missing",
            "error_code": terminal.get("error_code"),
            "termination_reason": terminal.get("termination_reason"),
        },
        "observation_summary": observation_summary,
        "expected_observations": calls_expected,
        "passed": passed,
        "error_category": error_category,
    }
    case_dir = output_dir / "cases"
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / f"{case_id}.replay.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if passed:
        try:
            read_replay(case_dir / f"{case_id}.replay.json")
        except (OSError, ValueError):
            passed = False
            error_category = error_category or "replay_validation_failed"
            bundle["passed"] = False
            bundle["error_category"] = error_category
            (case_dir / f"{case_id}.replay.json").write_text(
                json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
    actual_calls = capability.executions
    return {
        "case_id": case_id,
        "passed": passed,
        "error_category": error_category,
        "runs": run_facts,
        "expectations_verified": observation_summary["expectations_verified"],
        "expected_observations": calls_expected,
        "capability_executions": actual_calls,
        "sink_writes": len(capability.sink),
        "recovery_success": case_id == "read_recovery" and passed,
        "terminal": bundle["terminal"],
        "bundle_path": str(case_dir / f"{case_id}.replay.json"),
    }


def _ratio(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def compute_gate_metrics(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    passed = {case["case_id"] for case in cases if case.get("passed")}
    expected_observations = sum(
        int(case.get("expected_observations", 0)) for case in cases
    )
    verified = sum(int(case.get("expectations_verified", 0)) for case in cases)
    read_recovery = next(
        (case for case in cases if case.get("case_id") == "read_recovery"), None
    )
    executions = [
        execution
        for case in cases
        for execution in case.get("capability_executions", [])
    ]
    duplicates = 0
    for case in cases:
        signatures: dict[str, int] = {}
        for execution in case.get("capability_executions", []):
            args = {
                key: value
                for key, value in execution.get("arguments", {}).items()
                if key != "user_id"
            }
            signature = json.dumps(
                [execution.get("action"), args],
                sort_keys=True,
                separators=(",", ":"),
            )
            signatures[signature] = signatures.get(signature, 0) + 1
        duplicates += sum(count - 1 for count in signatures.values() if count > 1)
    return {
        "loop_pass_rate": _ratio(
            sum(case_id in passed for case_id in CASE_IDS), len(CASE_IDS)
        ),
        "observation_accuracy": _ratio(verified, expected_observations),
        "recovery_rate": _ratio(
            int(bool(read_recovery and read_recovery.get("passed"))), 1
        ),
        "duplicate_call_rate": _ratio(duplicates, len(executions)),
    }


async def run_gate(output_dir: Path) -> dict[str, Any]:
    output_dir = Path(output_dir)
    results = []
    for case_id in CASE_IDS:
        results.append(await _execute_case(case_id, output_dir))
    metrics = compute_gate_metrics(results)
    failures = [case["case_id"] for case in results if not case["passed"]]
    missing = sorted(set(CASE_IDS) - {case["case_id"] for case in results})
    metric_failures = []
    thresholds = {
        "loop_pass_rate": 1.0,
        "observation_accuracy": 1.0,
        "recovery_rate": 1.0,
        "duplicate_call_rate": 0.0,
    }
    for name, threshold in thresholds.items():
        value = metrics[name]["value"]
        if value is None or (
            value < threshold if name != "duplicate_call_rate" else value > threshold
        ):
            metric_failures.append(name)
    if (
        metrics["observation_accuracy"]["denominator"] <= 0
        or metrics["recovery_rate"]["denominator"] <= 0
    ):
        metric_failures.append("coverage")
    passed = (
        not failures
        and not missing
        and not metric_failures
        and len(results) == len(CASE_IDS)
    )
    report = {
        "schema_version": 1,
        "revision": _revision(),
        "passed": passed,
        "case_count": len(results),
        "failed_cases": failures,
        "missing_cases": missing,
        "skipped_cases": [],
        "metric_failures": metric_failures,
        "metrics": metrics,
        "cases": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report


def _validate_replay_bundle(bundle: Any) -> dict[str, Any]:
    if not isinstance(bundle, dict) or bundle.get("schema_version") != _REPLAY_SCHEMA:
        raise ValueError("invalid replay schema")
    if bundle.get("case_id") not in CASE_IDS:
        raise ValueError("unknown replay case")
    events = bundle.get("persisted_events")
    if not isinstance(events, list) or not events:
        raise ValueError("invalid replay events")
    by_run: dict[str, list[int]] = {}
    terminals: dict[str, int] = {}
    last_events: dict[str, str] = {}
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("sequence"), int):
            raise ValueError("invalid replay event")
        run_id = event.get("run_id")
        event_type = event.get("event_type")
        if not isinstance(run_id, str) or not isinstance(event_type, str):
            raise ValueError("invalid replay event")
        by_run.setdefault(run_id, []).append(event["sequence"])
        last_events[run_id] = event_type
        if event_type in {"run.succeeded", "run.failed", "run.cancelled"}:
            terminals[run_id] = terminals.get(run_id, 0) + 1
    if any(
        sequences != sorted(sequences) or len(sequences) != len(set(sequences))
        for sequences in by_run.values()
    ):
        raise ValueError("replay event order invalid")
    if any(
        terminals.get(run_id, 0) != 1
        or last_events.get(run_id)
        not in {"run.succeeded", "run.failed", "run.cancelled"}
        for run_id in by_run
    ):
        raise ValueError("replay terminal invalid")
    terminal = bundle.get("terminal")
    if not isinstance(terminal, dict) or terminal.get("status") not in {
        "completed",
        "failed",
        "cancelled",
        "timeout",
        "missing",
    }:
        raise ValueError("invalid replay terminal")
    last_run_id = bundle.get("run_id")
    run_facts = bundle.get("runs")
    if isinstance(run_facts, list) and run_facts:
        last_run_id = (
            run_facts[-1].get("run_id") if isinstance(run_facts[-1], dict) else None
        )
    terminal_event = {
        "completed": "run.succeeded",
        "failed": "run.failed",
        "cancelled": "run.cancelled",
        "timeout": "run.failed",
    }.get(terminal["status"])
    if (
        not isinstance(last_run_id, str)
        or last_events.get(last_run_id) != terminal_event
    ):
        raise ValueError("replay summary does not match persisted terminal")
    return bundle


def read_replay(path: Path) -> dict[str, Any]:
    try:
        bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid replay bundle") from exc
    return _validate_replay_bundle(bundle)


def _validate_frozen_decisions(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    case_id = bundle["case_id"]
    specs: dict[str, list[tuple[str, str, dict[str, Any] | None, str | None]]] = {
        "multi_step": [
            (_READ, "invoke", {"value": "seed"}, None),
            (_READ, "invoke", {"value": "observed:seed"}, None),
            ("", "respond", None, "two observations"),
        ],
        "read_recovery": [
            (_READ, "invoke", {"value": "bad"}, None),
            (_READ, "invoke", {"value": "good"}, None),
            ("", "respond", None, "recovered"),
        ],
        "policy_denied": [(_READ, "invoke", {"value": "denied"}, None)],
        "approval_resume": [
            (
                _WRITE,
                "invoke",
                {"value": "approved", "idempotency_key": "approval-key"},
                None,
            ),
            ("", "respond", None, "approved and resumed"),
        ],
        "cancelled_before_start": [],
        "cancelled_inflight": [(_WAIT, "invoke", {"value": "pause"}, None)],
        "unknown_write": [
            (
                _WRITE,
                "invoke",
                {"value": "uncertain", "idempotency_key": "unknown-key"},
                None,
            )
        ]
        * 2,
    }
    run_facts = bundle.get("runs")
    decisions = bundle.get("decisions")
    if not isinstance(run_facts, list) or not isinstance(decisions, list):
        raise ValueError("invalid replay decisions")
    expected = specs[case_id]
    if len(decisions) != len(expected):
        raise ValueError("replay decision count does not match the catalog")
    raw_run_ids = [fact.get("run_id") for fact in run_facts if isinstance(fact, dict)]
    if any(not isinstance(run_id, str) for run_id in raw_run_ids):
        raise ValueError("invalid replay run identity")
    run_ids = [str(run_id) for run_id in raw_run_ids]
    if len(run_ids) != (2 if case_id == "unknown_write" else 1):
        raise ValueError("replay run count does not match the catalog")
    counters: dict[str, int] = {}
    frozen = []
    for index, (record, (capability, action, arguments, content)) in enumerate(
        zip(decisions, expected, strict=True)
    ):
        if not isinstance(record, dict) or record.get("call_number") != index + 1:
            raise ValueError("invalid replay decision record")
        decision = record.get("proposed_decision")
        if not isinstance(decision, dict):
            raise ValueError("invalid frozen Decision")
        run_id = run_ids[1] if case_id == "unknown_write" and index == 1 else run_ids[0]
        counters[run_id] = counters.get(run_id, 0) + 1
        common: dict[str, Any] = {
            "schema_version": "v1",
            "decision_id": f"{run_id}-decision-{counters[run_id]}",
            "run_id": run_id,
            "action": action,
        }
        if action == "invoke" and arguments is not None:
            common.update(
                capability=capability,
                capability_version="v1",
                arguments=arguments,
            )
        elif content is not None:
            common["content"] = content
        else:
            raise ValueError("incomplete replay Decision specification")
        if decision != common:
            raise ValueError("frozen Decision does not match the catalog")
        event = record.get("emitted_event")
        if not isinstance(event, dict) or any(
            event.get(key) != value
            for key, value in {
                "type": "model_decision",
                "run_id": run_id,
                "decision_id": common["decision_id"],
                "action": action,
                "capability": capability or None,
            }.items()
        ):
            raise ValueError("frozen Decision event does not match the catalog")
        if record.get("assistant_json_in_history") != [] and not isinstance(
            record.get("assistant_json_in_history"), list
        ):
            raise ValueError("invalid replay assistant history")
        frozen.append(common)
    return frozen


async def rerun_bundle(bundle: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    # Validation projects to the catalog case id; bundle-provided decisions,
    # imports, capability names and messages are never used as configuration.
    bundle = _validate_replay_bundle(bundle)
    case_id = str(bundle["case_id"])
    if bundle.get("schema_version") != _REPLAY_SCHEMA:
        raise ValueError("invalid replay schema")
    canonical_inputs = 2 if case_id == "unknown_write" else 1
    messages = bundle.get("input_messages")
    if (
        not isinstance(messages, list)
        or len(messages) != canonical_inputs
        or any(
            not isinstance(message, dict)
            or set(message) != {"role", "content"}
            or message.get("role") != "user"
            or message.get("content") != f"Synthetic {case_id} request {index + 1}"
            for index, message in enumerate(messages)
        )
    ):
        raise ValueError("replay synthetic inputs do not match the catalog")
    frozen_decisions = _validate_frozen_decisions(bundle)
    result = await _execute_case(
        case_id, Path(output_dir), frozen_decisions=frozen_decisions
    )
    if not result["passed"]:
        raise RuntimeError("replayed catalog case failed")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline Agent loop certification gate"
    )
    parser.add_argument("--output", default=".runtime/agent-gate")
    parser.add_argument("--replay", help="rerun one validated known catalog case")
    args = parser.parse_args(argv)
    try:
        if args.replay:
            bundle = read_replay(Path(args.replay))
            result = asyncio.run(rerun_bundle(bundle, Path(args.output)))
            return 0 if result["passed"] else 1
        report = asyncio.run(run_gate(Path(args.output)))
        return 0 if report["passed"] else 1
    except Exception as exc:
        print(f"loop gate failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
