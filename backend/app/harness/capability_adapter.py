from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from typing import Any

from app.agents.base import BaseAgent
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.contracts import ExecutionContext
from app.harness.authority import contains_runtime_owned_field
from app.harness.policy import Approval, PolicyEngine, Principal
from app.harness.result import AgentResult
from app.trace import TraceEventType
from app.trace.recorder import safe_argument_shape, trace_span


def _contains_model_forbidden_field(value: Any) -> bool:
    return contains_runtime_owned_field(value)


def _payload_hash(arguments: dict[str, Any]) -> str:
    payload = {
        key: value for key, value in arguments.items() if key != "idempotency_key"
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CapabilityAdapter:
    """Runtime boundary for authenticated, policy-gated capability calls."""

    def __init__(
        self,
        capability: Any,
        *,
        policy_engine: PolicyEngine | None = None,
        approval: Approval | None = None,
        approval_provider: Callable[[ExecutionContext, str], Approval | None]
        | None = None,
        idempotency_store: Any | None = None,
        trusted_args: dict[str, Any] | None = None,
    ) -> None:
        self._capability = capability
        self._policy_engine = policy_engine or PolicyEngine()
        self._approval = approval
        self._approval_provider = approval_provider
        self._idempotency_store = idempotency_store
        self._trusted_args = dict(trusted_args or {})

    async def execute(
        self,
        context: ExecutionContext | None,
        action: str,
        public_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        public = dict(public_args or {})
        if _contains_model_forbidden_field(public):
            return CapabilityResult.fail(
                "Identity and runtime dependency fields are not accepted as model arguments",
                error_type="identity_spoofing",
            ).to_dict()

        descriptor = self._find_descriptor(action)
        if descriptor is None:
            return CapabilityResult.fail(
                f"Unknown action: {action}", error_type="invalid_action"
            ).to_dict()

        principal = None
        if context is not None and context.principal_id is not None:
            principal = Principal(principal_id=context.principal_id)
        if descriptor.requires_auth and principal is None:
            return CapabilityResult.fail(
                "Authenticated principal required", error_type="unauthorized"
            ).to_dict()
        if context is not None and context.capability_allowlist:
            public_name = descriptor.public_name or ""
            if not {
                self._capability.name,
                action,
                public_name,
            }.intersection(context.capability_allowlist):
                return CapabilityResult.fail(
                    "Capability is not allowed for this run", error_type="policy_denied"
                ).to_dict()

        approval = self._approval
        if self._approval_provider is not None and context is not None:
            approval = self._approval_provider(context, action)
        idempotency_key = public.get("idempotency_key")
        decision = self._policy_engine.authorize(
            principal, descriptor, approval, idempotency_key
        )
        if not decision.allowed:
            return CapabilityResult.fail(
                decision.reason or "Capability action denied",
                error_type=decision.error_type,
            ).to_dict()

        if descriptor.is_side_effect and self._idempotency_store is None:
            return CapabilityResult.fail(
                "An idempotency store is required for writes",
                error_type="idempotency_required",
            ).to_dict()

        internal_args = dict(public)
        internal_args.update(self._trusted_args)
        if principal is not None and descriptor.requires_auth:
            # This is an internal service argument, never a public/model field.
            internal_args["user_id"] = principal.principal_id

        async def invoke() -> dict[str, Any]:
            raw = await self._capability.execute(action, **internal_args)
            return self._as_dict(raw)

        async def operation() -> dict[str, Any]:
            result = await invoke()
            return {
                "status": "succeeded" if result.get("success", True) else "failed",
                "result": result,
                **(
                    {"error_code": result.get("error_type")}
                    if not result.get("success", True)
                    else {}
                ),
            }

        if descriptor.is_side_effect:
            if principal is None or self._idempotency_store is None:
                return CapabilityResult.fail(
                    "Authenticated principal and idempotency store required",
                    error_type="idempotency_required",
                ).to_dict()
            resource_key = self._resource_key(action, public)
            scope = f"{principal.principal_id}:{self._capability.name}:{resource_key}"
            execution = await self._idempotency_store.execute_once(
                scope,
                str(idempotency_key),
                _payload_hash(public),
                operation,
            )
            if execution.status == "conflict":
                return CapabilityResult.fail(
                    "The idempotency key was reused with different arguments",
                    error_type="idempotency_conflict",
                ).to_dict()
            return self._unwrap_idempotency_result(execution.result)

        try:
            return await invoke()
        except Exception:
            return CapabilityResult.fail(
                "Capability execution failed", error_type="internal"
            ).to_dict()

    def _find_descriptor(self, action: str) -> ActionDescriptor | None:
        for descriptor in self._capability.actions():
            if action in {descriptor.name, descriptor.public_name}:
                return descriptor
        return None

    @staticmethod
    def _resource_key(action: str, public_args: dict[str, Any]) -> str:
        if action in {"update_schedule", "delete_schedule"}:
            return f"schedule:{public_args.get('schedule_id', 'unknown')}"
        if action in {
            "create_schedule",
            "upsert_schedule",
            "bulk_upsert_schedules",
            "sync_bangumi_schedule",
        }:
            return "schedule:collection"
        if action in {
            "create_collection",
            "update_collection",
            "delete_collection",
            "upsert_collection",
        }:
            return f"collection:{public_args.get('source', 'unknown')}:{public_args.get('source_id', 'unknown')}"
        if action in {
            "batch_upsert_collections",
            "import_json_collections",
            "sync_bangumi_collections",
            "sync_douban_collections",
        }:
            return "collection:bulk"
        if action in {"add_rss_feed", "upsert_rss_feed"}:
            return f"rss:feed:{public_args.get('name') or public_args.get('url', 'unknown')}"
        if action == "remove_rss_feed":
            return f"rss:feed:{public_args.get('item_path', 'unknown')}"
        if action in {"set_rss_rule", "remove_rss_rule"}:
            return f"rss:rule:{public_args.get('rule_name', 'unknown')}"
        return action

    @staticmethod
    def _as_dict(raw: Any) -> dict[str, Any]:
        if isinstance(raw, CapabilityResult):
            return raw.to_dict()
        if isinstance(raw, dict):
            return raw
        return {"success": True, "value": raw}

    @staticmethod
    def _unwrap_idempotency_result(result: dict[str, Any]) -> dict[str, Any]:
        nested = result.get("result")
        if isinstance(nested, dict):
            return nested
        if result.get("status") == "attention_required":
            return CapabilityResult.fail(
                "The operation state requires manual verification",
                error_type="attention_required",
            ).to_dict()
        return result


class CapabilityAgent(BaseAgent):
    """Adapt a single Capability operation to the generic agent protocol."""

    def __init__(
        self,
        *,
        name: str,
        capability: Any,
        action: str,
        input_builder: Callable[[Any], dict[str, Any]] | None = None,
        adapter: CapabilityAdapter | None = None,
        context: ExecutionContext | None = None,
    ) -> None:
        self.name = name
        self._capability = capability
        self._action = action
        self._input_builder = input_builder or (lambda task: {})
        self._adapter = adapter
        self._context = context

    async def execute(self, task: Any) -> AgentResult:
        arguments = self._input_builder(task)
        actions = getattr(self._capability, "actions", None)
        descriptors = actions() if callable(actions) else ()
        descriptor = next(
            (item for item in descriptors if item.name == self._action), None
        )
        if (
            descriptor is not None
            and descriptor.is_side_effect
            and (self._adapter is None or self._context is None)
        ):
            return AgentResult(
                kind="capability",
                name=self.name,
                status="failed",
                error_code="dispatcher_required",
            )
        async with trace_span(
            TraceEventType.CAPABILITY_CALL,
            f"capability.{self.name}",
            {
                "action": self._action,
                "argument_shape": safe_argument_shape(arguments),
            },
        ):
            raw = (
                await self._adapter.execute(self._context, self._action, arguments)
                if self._adapter is not None and self._context is not None
                else await self._capability.execute(self._action, **arguments)
            )

        if isinstance(raw, AgentResult):
            return raw
        if not isinstance(raw, dict):
            return AgentResult(
                kind="capability",
                name=self.name,
                data={"value": raw},
            )

        success = bool(raw.get("success", True))
        data = {
            key: value
            for key, value in raw.items()
            if key not in {"success", "evidence", "error_code"}
        }
        return AgentResult(
            kind="capability",
            name=self.name,
            status="completed" if success else "failed",
            data=data,
            evidence=raw.get("evidence") or {},
            error_code=raw.get("error_code"),
        )

    async def plan(self, task: Any) -> dict[str, Any]:
        return {
            "goal": getattr(task, "goal", ""),
            "steps": [f"Call capability {self.name}"],
            "estimated_tools": [self.name],
        }

    async def reflect(self, task: Any, result: Any) -> dict[str, Any]:
        status = result.status if isinstance(result, AgentResult) else "unknown"
        return {
            "goal_achieved": status == "completed",
            "observations": [f"Capability {self.name} returned {status}"],
        }
