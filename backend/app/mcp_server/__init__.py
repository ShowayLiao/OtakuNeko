"""Expose approved OtakuNeko capabilities through MCP over stdio.

Tool definitions come from capability action descriptors, while an explicit
exposure map controls the public surface. Authentication and write approval
are trusted server-side context, never tool arguments.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import json
import sys
import time
from typing import Any

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor
from app.core.logging import get_logger
from app.harness.capability_adapter import CapabilityAdapter
from app.harness.authority import strip_runtime_owned_fields
from app.harness.authority import reject_runtime_owned_fields
from app.harness.contracts import AgentDecision, ExecutionContext
from app.harness.dispatcher import Dispatcher
from app.harness.persistence.idempotency import InMemoryIdempotencyStore
from app.harness.policy import Approval, PolicyEngine
from app.harness.normalizer import SchemaContractError, validate_input
from app.mcp_server.context import MCPContext
from app.mcp_server.policy import Policy
from app.trace import TraceEventType
from app.trace.recorder import safe_argument_shape, trace_span

logger = get_logger(__name__)

RPC_VERSION = "2.0"
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "OtakuNeko-MCP-Server", "version": "0.2.0"}

MAX_REQUEST_SIZE = 256 * 1024
MAX_RESPONSE_SIZE = 1024 * 1024
IDEMPOTENCY_CACHE_MAX_ENTRIES = 1024
IDEMPOTENCY_CACHE_TTL_SECONDS = 24 * 60 * 60

_SUPPORTED_SCHEMA_TYPES = {
    "object",
    "array",
    "string",
    "integer",
    "number",
    "boolean",
    "null",
}


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-standard JSON constant: {value}")


class ExposureMap:
    """Immutable-by-copy allowlist of public capability actions."""

    def __init__(self, mappings: dict[str, list[str]] | None = None) -> None:
        source = mappings or {}
        self._mappings = {name: tuple(actions) for name, actions in source.items()}

    def is_exposed(self, capability_name: str, action_name: str) -> bool:
        return action_name in self._mappings.get(capability_name, ())

    def exposed_actions(
        self, capability_name: str, capability: BaseCapability
    ) -> list[ActionDescriptor]:
        allowed = self._mappings.get(capability_name, ())
        return [action for action in capability.actions() if action.name in allowed]

    @property
    def capabilities(self) -> dict[str, list[str]]:
        return {name: list(actions) for name, actions in self._mappings.items()}


def _validate_schema_node(schema: Any, path: str, *, root: bool = False) -> None:
    if not isinstance(schema, dict):
        raise ValueError(f"{path} must be a JSON schema object")

    schema_type = schema.get("type")
    if root and schema_type != "object":
        raise ValueError(f"{path} root type must be 'object'")
    if isinstance(schema_type, list):
        if not schema_type or any(
            not isinstance(item, str) or item not in _SUPPORTED_SCHEMA_TYPES
            for item in schema_type
        ):
            raise ValueError(f"{path} has unsupported schema type '{schema_type}'")
    elif schema_type not in _SUPPORTED_SCHEMA_TYPES:
        raise ValueError(f"{path} has unsupported schema type '{schema_type}'")

    if "enum" in schema and not isinstance(schema["enum"], list):
        raise ValueError(f"{path}.enum must be an array")

    schema_types = set(schema_type) if isinstance(schema_type, list) else {schema_type}

    if "object" in schema_types:
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict):
            raise ValueError(f"{path}.properties must be an object")
        if not isinstance(required, list) or not all(
            isinstance(item, str) for item in required
        ):
            raise ValueError(f"{path}.required must be an array of strings")
        unknown = sorted(set(required) - set(properties))
        if unknown:
            raise ValueError(
                f"{path} references unknown required field(s): {', '.join(unknown)}"
            )
        for name, child in properties.items():
            _validate_schema_node(child, f"{path}.properties.{name}")

    if "array" in schema_types:
        items = schema.get("items")
        if items is None:
            raise ValueError(f"{path}.items is required for array schemas")
        _validate_schema_node(items, f"{path}.items")


def _validate_input_schema(schema: dict[str, Any], public_name: str) -> None:
    try:
        json.dumps(schema, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Tool '{public_name}' schema is not JSON serializable") from exc
    _validate_schema_node(schema, f"Tool '{public_name}' inputSchema", root=True)


def _public_input_schema(descriptor: ActionDescriptor) -> dict[str, Any]:
    return strip_runtime_owned_fields(deepcopy(descriptor.input_schema))


def _validate_exposure_map(
    registry: CapabilityRegistry,
    exposure: ExposureMap,
) -> None:
    """Fail startup for unknown actions, duplicates, or invalid schemas."""
    seen_public_names: set[str] = set()

    for cap_name, action_names in exposure.capabilities.items():
        try:
            capability = registry.get(cap_name)
        except KeyError as exc:
            raise ValueError(
                f"Exposure map references unknown capability '{cap_name}'"
            ) from exc

        descriptors = {action.name: action for action in capability.actions()}
        for action_name in action_names:
            descriptor = descriptors.get(action_name)
            if descriptor is None:
                raise ValueError(
                    f"Capability '{cap_name}' has no action '{action_name}'"
                )
            public_name = f"{cap_name}_{action_name}"
            if public_name in seen_public_names:
                raise ValueError(f"Duplicate public MCP tool name '{public_name}'")
            seen_public_names.add(public_name)
            _validate_input_schema(_public_input_schema(descriptor), public_name)


def _build_tool_from_descriptor(
    descriptor: ActionDescriptor, capability_name: str
) -> dict[str, Any]:
    return {
        "name": f"{capability_name}_{descriptor.name}",
        "description": descriptor.description,
        "inputSchema": _public_input_schema(descriptor),
    }


def _build_tool_schema(cap: BaseCapability, action: str) -> dict[str, Any]:
    """Backward-compatible wrapper for descriptor-based schema building."""
    descriptor = cap._find_action(action)
    if descriptor is None:
        return {
            "name": f"{cap.name}_{action}",
            "description": f"{cap.name} {action}",
            "inputSchema": {"type": "object", "properties": {}},
        }
    return _build_tool_from_descriptor(descriptor, cap.name)


def _matches_json_type(value: Any, schema_type: str | list[str]) -> bool:
    if isinstance(schema_type, list):
        return any(_matches_json_type(value, item) for item in schema_type)
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return False


def _argument_error(value: Any, schema: dict[str, Any], path: str) -> str | None:
    schema_type = schema["type"]
    if not _matches_json_type(value, schema_type):
        return f"{path} must be of type {schema_type}"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path} must be one of {schema['enum']}"

    schema_types = set(schema_type) if isinstance(schema_type, list) else {schema_type}

    if "object" in schema_types and isinstance(value, dict):
        properties = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in value:
                return f"{path}.{required} is required"
        for name, child_value in value.items():
            child_schema = properties.get(name)
            if child_schema is not None:
                error = _argument_error(child_value, child_schema, f"{path}.{name}")
                if error:
                    return error

    if "array" in schema_types and isinstance(value, list):
        for index, item in enumerate(value):
            error = _argument_error(item, schema["items"], f"{path}[{index}]")
            if error:
                return error

    if ({"integer", "number"} & schema_types) and value is not None:
        if "minimum" in schema and value < schema["minimum"]:
            return f"{path} must be >= {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            return f"{path} must be <= {schema['maximum']}"

    if "string" in schema_types and isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            return f"{path} is shorter than minLength"
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return f"{path} is longer than maxLength"
    return None


def _rpc_error(
    request_id: str | int | None,
    code: int,
    message: str,
    data: Any | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": RPC_VERSION, "id": request_id, "error": error}


class MCPServer:
    """Capability registry adapter with fail-closed exposure and policy."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        exposure: ExposureMap | None = None,
    ) -> None:
        self._registry = registry
        self._exposure = exposure or ExposureMap({})
        self._adapter_idempotency_store = InMemoryIdempotencyStore()
        _validate_exposure_map(registry, self._exposure)
        self._completed_writes: dict[
            tuple[int, str, str], tuple[str, dict[str, Any], float]
        ] = {}
        self._inflight_writes: dict[
            tuple[int, str, str], tuple[str, asyncio.Future[dict[str, Any]]]
        ] = {}
        self._write_lock = asyncio.Lock()

    def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for cap_name in self._registry.list_names():
            capability = self._registry.get(cap_name)
            for action in self._exposure.exposed_actions(cap_name, capability):
                tools.append(_build_tool_from_descriptor(action, cap_name))
        return tools

    def _resolve_tool(
        self, tool_name: str
    ) -> tuple[BaseCapability, str, ActionDescriptor] | None:
        for cap_name in self._registry.list_names():
            capability = self._registry.get(cap_name)
            for action in capability.actions():
                if tool_name == f"{cap_name}_{action.name}":
                    return capability, cap_name, action
        return None

    @staticmethod
    def _denied(tool_name: str, error: str, error_type: str) -> dict[str, Any]:
        logger.warning(
            "mcp_tool_denied",
            extra={"tool_name": tool_name, "error_type": error_type},
        )
        return {"success": False, "error": error, "error_type": error_type}

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: MCPContext | None = None,
        policy: Policy | None = None,
    ) -> dict[str, Any]:
        ctx = context or MCPContext()
        pol = policy or Policy()
        resolved = self._resolve_tool(tool_name)
        if resolved is None:
            return self._denied(tool_name, f"Unknown tool: {tool_name}", "not_found")

        capability, cap_name, action = resolved
        if not self._exposure.is_exposed(cap_name, action.name):
            return self._denied(tool_name, f"Unknown tool: {tool_name}", "not_found")
        if not isinstance(arguments, dict):
            return self._denied(tool_name, "Tool arguments must be an object", "invalid_args")

        if action.requires_auth and not ctx.is_authenticated:
            return self._denied(
                tool_name, "Authentication context is required", "unauthorized"
            )
        if action.is_side_effect and not ctx.is_authenticated:
            return self._denied(
                tool_name, "Authentication context is required", "unauthorized"
            )
        if action.is_side_effect and not pol.allow_side_effects:
            return self._denied(
                tool_name,
                "Side-effect policy approval is required",
                "policy_denied",
            )
        if action.is_side_effect and not pol.idempotency_key:
            return self._denied(
                tool_name,
                "An idempotency key is required for side effects",
                "idempotency_required",
            )

        public_schema = _public_input_schema(action)
        validation_error = _argument_error(arguments, public_schema, "arguments")
        if validation_error:
            return self._denied(tool_name, validation_error, "invalid_args")
        try:
            reject_runtime_owned_fields(arguments, label="MCP arguments")
            validate_input(arguments, action)
        except (SchemaContractError, ValueError):
            return self._denied(
                tool_name,
                "Tool arguments did not match the declared input contract",
                "invalid_args",
            )

        public_arguments = dict(arguments)
        public_arguments.pop("user_id", None)
        if action.is_side_effect:
            return await self._call_idempotent(
                capability, action.name, tool_name, public_arguments, ctx, pol
            )
        return await self._execute(
            capability, action.name, tool_name, public_arguments, ctx, pol
        )

    @staticmethod
    @asynccontextmanager
    async def _dependency_scope(context: MCPContext):
        dependencies = dict(context.extra)
        if context.dependency_provider is None:
            yield dependencies
            return
        async with context.dependency_provider() as provided:
            dependencies.update(provided)
            yield dependencies

    def _prune_idempotency_cache(
        self,
        now: float,
        *,
        reserve_entries: int = 0,
    ) -> None:
        expired = [
            key
            for key, (_, _, completed_at) in self._completed_writes.items()
            if now - completed_at >= IDEMPOTENCY_CACHE_TTL_SECONDS
        ]
        for key in expired:
            self._completed_writes.pop(key, None)
        overflow = max(
            0,
            len(self._completed_writes)
            - IDEMPOTENCY_CACHE_MAX_ENTRIES
            + reserve_entries,
        )
        if overflow > 0:
            oldest = sorted(
                self._completed_writes,
                key=lambda key: self._completed_writes[key][2],
            )
            for key in oldest[:overflow]:
                self._completed_writes.pop(key, None)

    async def _execute(
        self,
        capability: BaseCapability,
        action_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        context: MCPContext,
        policy: Policy,
    ) -> dict[str, Any]:
        async with trace_span(
            TraceEventType.MCP_CALL,
            tool_name,
            {"argument_shape": safe_argument_shape(arguments)},
        ) as event:
            try:
                approval = (
                    Approval(
                        approval_id=f"mcp:{context.user_id}:{policy.idempotency_key}",
                        principal_id=context.user_id,
                        action=action_name,
                    )
                    if policy.allow_side_effects
                    else None
                )
                async with self._dependency_scope(context) as dependencies:
                    execution_context = ExecutionContext(
                        principal_id=context.user_id,
                        run_id=f"mcp:{tool_name}",
                        trace_id=f"mcp:{tool_name}",
                        capability_allowlist=frozenset(
                            {capability.name, action_name, tool_name}
                        ),
                    )
                    dispatcher = Dispatcher(
                        self._registry,
                        policy_engine=PolicyEngine(
                            allow_side_effects=policy.allow_side_effects
                        ),
                        approval=approval,
                        idempotency_store=self._adapter_idempotency_store,
                        adapter_factory=lambda target: CapabilityAdapter(
                            target,
                            policy_engine=PolicyEngine(
                                allow_side_effects=policy.allow_side_effects
                            ),
                            approval=approval,
                            idempotency_store=self._adapter_idempotency_store,
                            trusted_args=dependencies,
                        ),
                    )
                    decision_id = (
                        f"mcp:{tool_name}:{policy.idempotency_key or 'read'}"
                    )
                    decision = AgentDecision(
                        decision_id=decision_id,
                        run_id=execution_context.run_id,
                        action="invoke",
                        capability=next(
                            (
                                item.public_name or item.name
                                for item in capability.actions()
                                if item.name == action_name
                            ),
                            action_name,
                        ),
                        capability_version=next(
                            (
                                item.version
                                for item in capability.actions()
                                if item.name == action_name
                            ),
                            "v1",
                        ),
                        arguments=arguments,
                    )
                    invocation = await dispatcher.dispatch(
                        decision,
                        execution_context,
                        idempotency_key=policy.idempotency_key,
                    )
                    # MCP v1 keeps its structured ``data`` envelope as an
                    # explicit compatibility projection.  It is derived from
                    # the Dispatcher's normalized model projection and never
                    # exposes raw provider/capability output.
                    result = {
                        "success": invocation.status == "succeeded",
                        "data": invocation.model_output.get("safe_output", {}),
                    }
                    if invocation.error_code is not None:
                        result["error_type"] = str(invocation.error_code)
                        result["error"] = "Tool execution failed"
            except asyncio.TimeoutError:
                if event is not None:
                    event.status = "timeout"
                    event.data["error_category"] = "timeout"
                logger.warning("mcp_tool_timeout", extra={"tool_name": tool_name})
                return {
                    "success": False,
                    "error": "Tool execution timed out",
                    "error_type": "timeout",
                }
            except Exception as exc:
                if event is not None:
                    event.status = "failed"
                    event.data["error_category"] = type(exc).__name__
                logger.exception("mcp_tool_failed", extra={"tool_name": tool_name})
                return {
                    "success": False,
                    "error": f"Tool execution failed: {type(exc).__name__}",
                    "error_type": "internal",
                }
            if event is not None and result.get("success") is False:
                event.status = "failed"
                event.data["error_category"] = str(
                    result.get("error_type", "protocol_error")
                )
            return result

    async def _call_idempotent(
        self,
        capability: BaseCapability,
        action_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        context: MCPContext,
        policy: Policy,
    ) -> dict[str, Any]:
        key = (context.user_id, tool_name, policy.idempotency_key)
        fingerprint = json.dumps(
            arguments,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
        owner = False

        async with self._write_lock:
            self._prune_idempotency_cache(time.monotonic())
            completed = self._completed_writes.get(key)
            if completed is not None:
                stored_fingerprint, result, _ = completed
                if stored_fingerprint != fingerprint:
                    return self._denied(
                        tool_name,
                        "Idempotency key was reused with different arguments",
                        "idempotency_conflict",
                    )
                return deepcopy(result)

            inflight = self._inflight_writes.get(key)
            if inflight is None:
                future = asyncio.get_running_loop().create_future()
                self._inflight_writes[key] = (fingerprint, future)
                owner = True
            else:
                inflight_fingerprint, future = inflight
                if inflight_fingerprint != fingerprint:
                    return self._denied(
                        tool_name,
                        "Idempotency key was reused with different arguments",
                        "idempotency_conflict",
                    )

        if not owner:
            return deepcopy(await asyncio.shield(future))

        try:
            execution_arguments = {
                **arguments,
                "idempotency_key": policy.idempotency_key,
            }
            result = await self._execute(
                capability,
                action_name,
                tool_name,
                execution_arguments,
                context,
                policy,
            )
        except BaseException:
            async with self._write_lock:
                current = self._inflight_writes.get(key)
                if current is not None and current[1] is future:
                    self._inflight_writes.pop(key, None)
                if not future.done():
                    future.cancel()
            raise

        async with self._write_lock:
            if result.get("success") is True:
                now = time.monotonic()
                self._prune_idempotency_cache(now, reserve_entries=1)
                self._completed_writes[key] = (fingerprint, deepcopy(result), now)
            self._inflight_writes.pop(key, None)
            if not future.done():
                future.set_result(deepcopy(result))
        return result

    async def handle_request(
        self,
        request: Any,
        context: MCPContext | None = None,
        policy: Policy | None = None,
    ) -> dict[str, Any] | None:
        if not isinstance(request, dict):
            return _rpc_error(None, -32600, "Invalid Request")

        request_id = request.get("id")
        has_id = "id" in request
        if (
            request.get("jsonrpc") != RPC_VERSION
            or not isinstance(request.get("method"), str)
            or (has_id and (
                request_id is None
                or isinstance(request_id, bool)
                or not isinstance(request_id, (str, int))
            ))
        ):
            return _rpc_error(request_id if has_id else None, -32600, "Invalid Request")

        method = request["method"]
        is_notification = not has_id
        params = request.get("params", {})
        if not isinstance(params, dict):
            return None if is_notification else _rpc_error(
                request_id, -32602, "Invalid params"
            )

        if is_notification:
            return None

        if method == "initialize":
            return {
                "jsonrpc": RPC_VERSION,
                "id": request_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                },
            }

        if method == "tools/list":
            return {
                "jsonrpc": RPC_VERSION,
                "id": request_id,
                "result": {"tools": self.list_tools()},
            }

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(tool_name, str) or not isinstance(arguments, dict):
                return _rpc_error(request_id, -32602, "Invalid tool call params")

            resolved = self._resolve_tool(tool_name)
            if resolved is None or not self._exposure.is_exposed(
                resolved[1], resolved[2].name
            ):
                return _rpc_error(request_id, -32602, f"Unknown tool: {tool_name}")

            validation_error = _argument_error(
                arguments, _public_input_schema(resolved[2]), "arguments"
            )
            if validation_error:
                return _rpc_error(request_id, -32602, validation_error)

            result = await self.call_tool(tool_name, arguments, context, policy)
            text = json.dumps(result, ensure_ascii=False, allow_nan=False)
            if len(text.encode("utf-8")) > MAX_RESPONSE_SIZE:
                result = {
                    "success": False,
                    "error": "Tool response exceeded the configured size limit",
                    "error_type": "response_too_large",
                }
                text = json.dumps(result, ensure_ascii=False, allow_nan=False)
            return {
                "jsonrpc": RPC_VERSION,
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": text}],
                    "isError": result.get("success") is False,
                },
            }

        return _rpc_error(request_id, -32601, f"Method not found: {method}")

    def handle_response(
        self,
        request: dict[str, Any],
        context: MCPContext | None = None,
        policy: Policy | None = None,
    ) -> dict[str, Any] | None:
        return asyncio.get_event_loop().run_until_complete(
            self.handle_request(request, context, policy)
        )


def _read_stdio_frame() -> tuple[bytes | None, bool]:
    reader = getattr(sys.stdin, "buffer", sys.stdin)
    raw = reader.readline(MAX_REQUEST_SIZE + 2)
    if not raw:
        return None, False
    if isinstance(raw, str):
        raw = raw.encode("utf-8")

    oversized = len(raw) > MAX_REQUEST_SIZE
    while raw and not raw.endswith(b"\n"):
        chunk = reader.readline(MAX_REQUEST_SIZE + 2)
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        if not chunk:
            break
        oversized = oversized or len(chunk) > 0
        raw = chunk
    return (b"" if oversized else raw), oversized


class StdioServer:
    """Concurrent line-delimited JSON-RPC stdio transport."""

    def __init__(
        self,
        server: MCPServer,
        context: MCPContext | None = None,
        policy: Policy | None = None,
    ) -> None:
        self._server = server
        self._context = context or MCPContext()
        self._policy = policy or Policy()
        self._pending_requests: dict[str | int, asyncio.Task[None]] = {}
        self._write_lock = asyncio.Lock()

    def cancel_request(self, request_id: str | int) -> None:
        task = self._pending_requests.get(request_id)
        if task is not None and not task.done():
            task.cancel()

    def handle_cancellation(self, request: Any) -> bool:
        """Validate and apply an MCP cancellation notification."""
        if (
            not isinstance(request, dict)
            or request.get("jsonrpc") != RPC_VERSION
            or request.get("method") != "notifications/cancelled"
            or "id" in request
            or not isinstance(request.get("params"), dict)
        ):
            return False
        request_id = request["params"].get("requestId")
        if (
            isinstance(request_id, bool)
            or not isinstance(request_id, (str, int))
        ):
            return False
        self.cancel_request(request_id)
        return True

    async def _write_response(self, response: dict[str, Any]) -> None:
        payload = json.dumps(
            response, ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        if len(payload) > MAX_RESPONSE_SIZE:
            payload = json.dumps(
                _rpc_error(response.get("id"), -32603, "Response exceeds size limit"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        async with self._write_lock:
            sys.stdout.buffer.write(payload + b"\n")
            sys.stdout.buffer.flush()

    async def _dispatch(self, request: dict[str, Any]) -> None:
        request_id = request.get("id")
        try:
            response = await self._server.handle_request(
                request, self._context, self._policy
            )
            if response is not None:
                await self._write_response(response)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("mcp_request_failed")
            await self._write_response(
                _rpc_error(request_id, -32603, "Internal error")
            )
        finally:
            if request_id is not None:
                self._pending_requests.pop(request_id, None)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            while True:
                raw, oversized = await loop.run_in_executor(None, _read_stdio_frame)
                if raw is None:
                    break
                if oversized:
                    await self._write_response(
                        _rpc_error(None, -32600, "Request exceeds size limit")
                    )
                    continue
                if not raw.strip():
                    continue

                try:
                    request = json.loads(
                        raw.decode("utf-8"),
                        parse_constant=_reject_json_constant,
                    )
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    await self._write_response(_rpc_error(None, -32700, "Parse error"))
                    continue

                if self.handle_cancellation(request):
                    continue

                if not isinstance(request, dict) or "id" not in request:
                    response = await self._server.handle_request(
                        request, self._context, self._policy
                    )
                    if response is not None:
                        await self._write_response(response)
                    continue

                request_id = request.get("id")
                task = asyncio.create_task(self._dispatch(request))
                if isinstance(request_id, (str, int)) and not isinstance(
                    request_id, bool
                ):
                    self._pending_requests[request_id] = task
                await asyncio.sleep(0)
        finally:
            tasks = list(self._pending_requests.values())
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
