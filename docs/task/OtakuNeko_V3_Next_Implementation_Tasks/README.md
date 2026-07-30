# OtakuNeko V3 Next Implementation Tasks

This directory translates RFC-101 and RFC-106 into independently executable
task packages.

## Status

| Task | Status | Depends on |
| --- | --- | --- |
| AGENT-001 | Complete | HARNESS-001 |
| CAPABILITY-001 | Complete | AGENT-001 |
| MEMORY-001 | Complete foundation | HARNESS-002 |
| TRACE-001 | Complete foundation | HARNESS-001 |
| MCP-001 | Complete Anime pilot | CAPABILITY-001 |
| MEMORY-002 | Complete | MEMORY-001 |
| TRACE-002 | Complete | TRACE-001 |
| CAPABILITY-002 | Complete | CAPABILITY-001 |
| CAPABILITY-003 | Post-V3 follow-up | CAPABILITY-002, MCP-002, TRACE-002 |
| MULTI-AGENT-001 | Complete | AGENT-001 |
| MULTI-AGENT-002 | Blocked by MULTI-AGENT-001 | MULTI-AGENT-001 |
| EVAL-001 | Complete | TRACE-002, MULTI-AGENT-001 |
| MCP-002 | Complete | CAPABILITY-002, TRACE-002 |
| PROACTIVE-001 | Complete | MEMORY-002, EVAL-001, TRACE-002 |
| FRONTEND-AI-001 | Post-V3 follow-up | MEMORY-002, TRACE-002, PROACTIVE-001 |
| V3-ACCEPTANCE-001 | Complete | MEMORY-002, TRACE-002, CAPABILITY-002, MULTI-AGENT-001, EVAL-001, MCP-002, PROACTIVE-001 |

## Recommended Execution Order

`MEMORY-002 -> TRACE-002 -> CAPABILITY-002 -> MULTI-AGENT-001 ->`
`MULTI-AGENT-002 -> EVAL-001 -> MCP-002 -> PROACTIVE-001 ->`
`V3-ACCEPTANCE-001`

Post-V3 follow-up order:

`CAPABILITY-003 -> FRONTEND-AI-001`

Each task must be implemented with tests first, validated with the commands in
its `tests.md`, and committed separately.
