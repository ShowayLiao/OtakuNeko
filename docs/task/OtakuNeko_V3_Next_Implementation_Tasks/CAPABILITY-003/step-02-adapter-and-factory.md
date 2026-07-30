# CAPABILITY-003 Step 02 LangChain Adapter and Shared Factory

## Files

- Modify `backend/app/capabilities/types.py`.
- Modify `backend/app/capabilities/registry.py`.
- Create `backend/app/capabilities/langchain_adapter.py`.
- Create `backend/app/capabilities/factory.py`.
- Modify `backend/app/capabilities/__init__.py`.
- Test under `backend/tests/capabilities/`.

## Requirements

Extend `CapabilityRegistry` with deterministic action lookup that returns the
owning capability plus descriptor. Preserve fail-fast duplicate checks and
stable registration order.

Implement a LangChain adapter that creates runtime tools from action
descriptors and delegates execution to `BaseCapability.execute`. It must:

- preserve the explicit public tool name, description, and JSON schema;
- validate inputs before invoking the capability;
- inject trusted runtime dependencies and authenticated user context outside
  model-controlled arguments;
- preserve typed capability failures instead of converting them to success;
- rely on the existing capability trace instrumentation exactly once.

Add one `build_capability_registry()` factory that registers every production
capability. Both chat and MCP must consume this factory in later steps instead
of maintaining separate registration lists.

## Acceptance

- Registry lookup, ordering, duplicate public names, schema validation,
  context injection, success, typed failure, and exception behavior have
  focused tests.
- Adapter output passes LangChain tool schema validation.
- Capability calls create one capability trace span, not nested duplicates.
- The factory has one test asserting the complete capability/action inventory.
