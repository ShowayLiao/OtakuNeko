# CAPABILITY-003 Step 01 Registry Parity Contract

## Files

- Create `backend/tests/capabilities/test_tool_parity.py`.
- Extend `backend/tests/capabilities/test_registry.py`.
- Read current exports from `backend/app/agents/tools/__init__.py`.
- Read current action descriptors under `backend/app/capabilities/`.

## Requirements

Capture a migration matrix for every tool currently registered through
`ALL_TOOLS`. For each public tool name, identify exactly one owning capability
and action, then assert the externally visible description, JSON input schema,
side-effect metadata, authentication needs, and normalized result semantics.

Add missing capability actions for uncovered behavior rather than retaining an
unowned tool forever. The current-time helper may use a focused system
capability; profile generation must map to the existing recommendation
capability when contracts are equivalent.

The mapping from internal `capability.action` to a legacy public tool name must
be explicit metadata, not naming heuristics. Reject duplicate public names at
registration.

## Acceptance

- The parity test enumerates every old `ALL_TOOLS` entry and fails for missing,
  duplicated, or schema-incompatible mappings.
- Read/write and authenticated action metadata remain explicit.
- The test proves the migration baseline before `ChatWorkflow` changes.
