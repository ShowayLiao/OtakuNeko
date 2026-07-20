# CAPABILITY-002 Domain Capability Expansion

## Goal

Complete the modular action layer needed by specialized agents by adding
recommendation, schedule, and media capabilities without moving reasoning into
capabilities.

## Dependencies

- CAPABILITY-001
- Existing recommendation/profile and schedule services

## Scope

- RecommendationCapability for candidate retrieval and ranking inputs.
- ScheduleCapability for user schedule reads and writes.
- MediaCapability as a stable boundary for future library integrations.
- Explicit action descriptors so agents and MCP do not hard-code action lists.
- Migration of matching tools away from direct service dependencies.

## Non-Goals

- Agent routing or conversation prompts.
- New recommendation algorithms.
- New external media providers.
- Removing the Tool compatibility facade before all callers migrate.

## Execution Order

1. Add capability action metadata and discovery.
2. Implement RecommendationCapability.
3. Implement ScheduleCapability.
4. Define the minimal MediaCapability boundary.
5. Migrate tools and add contract tests.

## Definition of Done

- Agents and MCP can discover actions from capability metadata.
- No migrated tool imports its domain service directly.
- Authenticated actions require explicit user context.
- Capability failures use a shared, typed result contract.

## Rollback

Disable new capability registrations and route covered tools through the
CAPABILITY-001 compatibility facade; remove only additive schema or registry
changes proven unused by the migration tests.

## Related RFC

RFC-101 Phase 3, RFC-106 Capability Layer and Principle 3.
