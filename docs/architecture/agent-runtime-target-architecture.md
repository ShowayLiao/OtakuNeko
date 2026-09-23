# AgentRuntime Target Architecture

> Status: closure verified for the enabled primary path; compatibility adapters and the declared single-worker deployment boundary remain explicit.
>
> Scope: the primary OtakuNeko chat path and the shared Agent Harness boundary.
>
> Related references: [standard-agent-harness-reference.md](standard-agent-harness-reference.md), [post-batch13 audit](../harness-audit/12-post-batch13-current-audit.md), and [post-audit execution plan](../harness-execution/POST-AUDIT-EXECUTION-PLAN.md).

## 1. Purpose and status vocabulary

This document persists the target topology for the unified Agent Harness. It is a design boundary and migration exit criterion. It MUST NOT be read as proof that every box already exists in production code.

Use the following status vocabulary when comparing the target with source:

- **Implemented**: verified by a source path and applicable tests.
- **Partial**: a compatible boundary exists, but the primary path still has a legacy owner or incomplete durability semantics.
- **Target**: required by this document but not yet proven by the current primary path.

The source of truth for current behavior remains the code and the audit documents. The primary `/chat` path is Runtime-owned and does not construct `ChatWorkflow`; `backend/app/agents/graph.py`, `langgraph_adapter.py`, and the singular `tools.py` shim have been removed. LangGraph remains only where the Memory migration boundary still requires it, not as a chat Run controller.

## 2. Target topology

```text
┌──────────────────────────────────────────────────────────────┐
│                         User / API                           │
│                                                              │
│  Authentication, tenant, role, resource scope and user_id   │
│  are trusted ingress data. They are injected by the API.    │
└───────────────────────────────┬──────────────────────────────┘
                                │ RunRequest
                                ▼
┌──────────────────────────────────────────────────────────────┐
│                       AgentRuntime                           │
│                 the only Run control plane                   │
│                                                              │
│  1. Create/load Run, Budget and Cancellation                  │
│  2. Read durable State                                         │
│  3. Build trusted ExecutionContext                             │
│  4. Call ModelGateway                                          │
│  5. Parse and validate Decision                                │
│  6. Dispatch Invocation                                       │
│  7. Normalize InvocationResult                                │
│  8. Persist Event / State / terminal RunResult                 │
│  9. Decide whether to continue or finish                       │
└───────────────┬───────────────────┬──────────────────────────┘
                │                   │
                │ trusted Context  │ state/event persistence
                ▼                   ▼
┌─────────────────────────┐  ┌────────────────────────────────┐
│     Context Manager      │  │ ResultNormalizer / EventBus    │
│                         │  │                                │
│ User messages           │  │ Run / Invocation / Event       │
│ Memory and provenance   │  │ Trace projection                │
│ Tool schemas            │  │ SSE projection                  │
│ Current Run state       │  │ Safe output and error contract  │
│ Never model-owned auth  │  │ Durable replay and recovery     │
└──────────────┬──────────┘  └────────────────────────────────┘
               │ model-safe context
               ▼
┌──────────────────────────────────────────────────────────────┐
│                       ModelGateway                            │
│                                                              │
│  Provider-neutral timeout / usage / cost / error handling    │
│  Provider credentials and trusted execution objects stay     │
│  outside the model-visible Decision payload.                 │
└───────────────────────────────┬──────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────┐
│                            LLM                               │
│                                                              │
│  May propose only a versioned, structured Decision.           │
│  It cannot directly execute Tool, Capability, MCP or         │
│  Subagent code.                                               │
└───────────────────────────────┬──────────────────────────────┘
                                │ Decision
                                ▼
┌──────────────────────────────────────────────────────────────┐
│                  Decision Parser / Validator                  │
│                                                              │
│  Schema, version, run identity, allowed action, argument      │
│  shape and model-owned identity field rejection.              │
└───────────────────────────────┬──────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────┐
│                 Policy / Authorization Layer                  │
│                                                              │
│  Resource ownership, scope, role, approval, side-effect       │
│  policy, budget and idempotency preconditions.                 │
└───────────────────────────────┬──────────────────────────────┘
                                │ allowed Invocation
                                ▼
┌──────────────────────────────────────────────────────────────┐
│                 Invocation / Dispatcher                       │
│                                                              │
│  The only path to Tool, Capability, Workflow, MCP or          │
│  Subagent execution. Injects trusted user/tenant/scope        │
│  context and owns invocation-level timeout/cancel behavior.   │
└───────────────────────────────┬──────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────┐
│                    Real business execution                    │
│                                                              │
│  Domain Service / Capability / MCP Server / External API      │
│                                                              │
│  Explicit side effect, authorization, retry, idempotency,     │
│  audit, compensation and unknown-outcome handling.             │
└───────────────────────────────┬──────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────┐
│                    Structured InvocationResult                │
│                                                              │
│  status: succeeded / failed / denied / cancelled / timeout    │
│  safe output, structured error, usage, cost, latency,         │
│  artifacts and audit references.                               │
└───────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │ AgentRuntime loop │
                       │ continue or end   │
                       └────────┬─────────┘
                                │ continue
                                └──────────────► ModelGateway

SSE / WebSocket is only a projection and subscription channel for
durable Run Events. It is not the Run state store.
```

## 3. Runtime-owned lifecycle

The target Run lifecycle is controlled by `AgentRuntime` as a single owner:

```text
queued
  │
  ▼
running ──► waiting / paused ──► running
  │
  ├─► completed
  ├─► failed
  ├─► cancelled
  ├─► timed_out
  ├─► budget_exceeded
  └─► abandoned / attention_required
```

For every iteration, the Runtime performs the following sequence:

```text
state = StateStore.load(run_id)
context = ContextManager.build(state, trusted_ingress)
model_result = ModelGateway.infer(context)
decision = DecisionParser.parse(model_result)

if decision is terminal:
    result = RunResult.completed(decision)
else:
    invocation = Dispatcher.dispatch(decision, context)
    result = ResultNormalizer.normalize(invocation)

EventStore.append(run_id, result)
StateStore.save(run_id, state, result)

if result requests continuation:
    repeat
else:
    persist terminal RunResult
```

The model, Tool, MCP Server and Subagent MUST NOT independently decide to start a second Run loop, mutate terminal state, or bypass the Dispatcher.

## 4. Contract boundaries

The target contracts are versioned and safe to persist:

| Contract | Responsibility | Must not contain |
|---|---|---|
| `RunRequest` | User goal, trusted context reference, budget and compatibility input | Model-provided authority |
| `ExecutionContext` | Runtime-injected principal, tenant, scope, run/trace IDs and allowlist | Raw provider response or arbitrary model fields |
| `AgentDecision` | Versioned terminal response or capability invocation proposal | Database session, token, user identity override, file handle |
| `InvocationRequest` | Invocation/run association, capability version, policy/idempotency data | Unvalidated model payload |
| `InvocationResult` | Safe status, output, error, usage, latency and audit references | Raw secret, raw provider payload, unredacted exception |
| `RunEvent` | Ordered, owner-scoped lifecycle projection | Prompt/CoT/secret or untrusted instructions as system policy |
| `RunResult` | The single terminal result and recovery semantics | A second competing terminal state |

## 5. Ownership rules

| Concern | Target owner | Current source boundary |
|---|---|---|
| Run lifecycle | `AgentRuntime` | `AgentRuntime` owns the primary loop; there is no legacy chat rollback controller |
| Model call | `ModelGateway` | Primary inference goes through `ModelGateway`; provider-specific objects remain behind the gateway |
| Decision validation | `DecisionParser` | Implemented for Dispatcher proposals and structured Runtime path |
| Invocation authorization/execution | `Dispatcher` | Implemented through `CapabilityRegistry` and `CapabilityAdapter` |
| Trusted identity/scope | API/Runtime/Domain Service | Enabled primary `ExecutionContext` and ContextManager inject identity, scope and model-safe context; compatibility services remain request-scoped |
| Run/Event persistence | Run/Event stores and Runtime | Enabled primary durable runs write canonical Run/Event facts before SSE projection |
| SSE | API projection | SSE, history and reasoning are projections of canonical Runtime EventStore facts |
| Multi-worker recovery | Durable shared adapter | Not complete; current SQLite deployment is explicitly single-worker |

## 6. Current implementation gap

The following facts are intentionally recorded so this target cannot be mistaken for current behavior:

1. `backend/app/api/v1/agent.py` enters `AgentRuntime.stream_decision()` for the primary chat path.
2. The deleted `graph.py`, `langgraph_adapter.py`, and singular `tools.py` files are no longer importable runtime entrypoints; the remaining `agents/tools/` package contains domain-level tool implementations only.
3. `backend/app/harness/runtime.py::AgentRuntime.stream_decision()` owns `ModelGateway -> DecisionParser -> Dispatcher -> Result`, canonical Run/Event persistence, continuation, cancellation, timeout and terminal state for the enabled primary path.
4. The primary model call is provider-neutral through `ModelGateway`; provider-specific construction remains isolated behind the gateway.
5. `Dispatcher` and `ResultNormalizer` provide the canonical invocation/result boundary used by primary capability execution and the MCP adapter; SSE/history/replay use the canonical primary stores.
6. Shared multi-worker coordination is not claimed; deployment validation explicitly requires the configured SQLite single-worker adapter.

## 7. Migration exit criteria

The target architecture is considered reached only when all of the following are true:

- The enabled primary chat API enters `AgentRuntime` and does not create a second model/tool loop in LangGraph.
- The primary model call goes through `ModelGateway` and produces a versioned `AgentDecision`.
- `DecisionParser` and `Dispatcher` are the only path from model output to execution.
- AgentRuntime, not LangGraph, decides continuation, retry, cancellation, timeout and terminal state.
- Every invocation has one canonical `invocation_id` associated with its Run and ordered Events.
- Side effects have verified authorization, approval, timeout, cancellation, retry, idempotency, audit and compensation/unknown-outcome semantics.
- State, Run, Event, Invocation and terminal Result survive SSE disconnect and worker restart according to the declared deployment adapter.
- Acceptance tests exercise the real primary API or Runtime entrypoint and prove the invariants above.
- No enabled legacy direct specialist, ToolNode or MCP path can bypass Dispatcher; specialist execution is bound to Runtime-provided capability invocation, and approval pause/resume is owned by Runtime through the persisted pending Decision contract.

The enabled primary path satisfies these criteria for the declared single-worker deployment adapter. Documentation must continue to identify the single-worker boundary; multi-worker recovery remains unavailable, while approval continuation is covered by the Runtime checkpoint and canonical Run/Event path.
