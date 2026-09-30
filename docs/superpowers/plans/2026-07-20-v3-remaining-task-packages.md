# V3 Remaining Task Packages Implementation Plan

> **For AI implementation agents:** Execute one task directory at a time. Use
> test-driven development, run the task's `tests.md` gates, and commit each task
> separately. Do not combine independent task packages into one implementation.

**Goal:** Complete RFC-106 through nine bounded, dependency-ordered tasks.

**Architecture:** Continue the migration direction API -> Harness -> Agents ->
Capabilities -> Services -> Data. Finish durable memory and observability before
splitting specialists, then add evaluation, MCP expansion, proactive execution,
and a final evidence-based acceptance gate.

**Technology:** FastAPI, LangGraph, SQLModel/SQLAlchemy, Alembic, pytest, Ruff,
MCP JSON-RPC.

---

## Execution Checklist

- [ ] Execute `MEMORY-002` and verify durable typed memory.
- [ ] Execute `TRACE-002` and verify privacy-safe decision traces.
- [ ] Execute `CAPABILITY-002` and verify modular domain actions.
- [ ] Execute `MULTI-AGENT-001` and verify router/recommendation rollout.
- [ ] Execute `MULTI-AGENT-002` and verify three-agent cooperation.
- [ ] Execute `EVAL-001` and establish regression thresholds.
- [ ] Execute `MCP-002` and verify capability-driven MCP discovery.
- [ ] Execute `PROACTIVE-001` and verify exactly-once scheduled slots.
- [ ] Execute `V3-ACCEPTANCE-001` and publish the RFC completion report.

Each checkbox is governed by the exact files, acceptance criteria, rollback
boundary, tests, and verification commands inside the corresponding task folder.
