# CAPABILITY-002 Step 04 Media Boundary and Tool Migration

## Files

- Create `backend/app/capabilities/media.py`.
- Modify `backend/app/capabilities/__init__.py`.
- Modify matching modules under `backend/app/agents/tools/`.
- Test direct-dependency rules.

## Requirements

Define a provider-neutral media interface for library lookup, status, and
metadata refresh. Initially unsupported actions must return an explicit
`not_configured` error, not pretend success.

Migrate all covered tools to capability calls and add an architecture test that
prevents those tools from importing services directly.

## Acceptance

- Capability registration is modular.
- Tool public names and schemas remain backward compatible.
- Direct service dependencies remain only inside capabilities.
