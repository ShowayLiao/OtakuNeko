# V3-ACCEPTANCE-001 Step 01 Architecture Audit

## Files

- Create architecture tests under `backend/tests/architecture/`.
- Update architecture documentation to match production wiring.

## Requirements

Statically verify import direction and inspect runtime construction. API may
construct/inject Harness components but may not call agents, capabilities, or
repositories as an alternate execution path. Agents may depend on capability
and memory interfaces, not concrete services or database models.

Inventory compatibility facades and give each one an owner, reason, and removal
condition. Remove only those proven unused by repository search and tests.

## Acceptance

- Prohibited dependency fixtures fail the architecture test.
- Production chat and proactive paths both enter AgentRuntime.
- Documentation diagrams match actual imports and object construction.
