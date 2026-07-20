# CAPABILITY-002 Step 01 Action Contract

## Files

- Modify `backend/app/capabilities/base.py`.
- Modify `backend/app/capabilities/registry.py`.
- Create `backend/app/capabilities/types.py`.
- Test in `backend/tests/capabilities/test_action_contract.py`.

## Requirements

Define immutable action descriptors with name, description, JSON input schema,
authentication requirement, and side-effect flag. Add a typed success/error
result without breaking AnimeCapability callers during migration.

Registry discovery must derive available actions from each capability rather
than a hard-coded list in MCPServer.

## Acceptance

- Duplicate capability and action names fail fast.
- Schemas are JSON serializable.
- Side-effecting actions are distinguishable before execution.
