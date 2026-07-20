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
| MEMORY-002 | Ready | MEMORY-001 |
| TRACE-002 | Ready | TRACE-001 |
| CAPABILITY-002 | Ready | CAPABILITY-001 |
| MULTI-AGENT-001 | Blocked by MEMORY-002 and CAPABILITY-002 | AGENT-001 |
| MULTI-AGENT-002 | Blocked by MULTI-AGENT-001 | MULTI-AGENT-001 |
| EVAL-001 | Blocked by MULTI-AGENT-001 | TRACE-002 |
| MCP-002 | Blocked by CAPABILITY-002 | MCP-001 |
| PROACTIVE-001 | Blocked by MEMORY-002 and EVAL-001 | HARNESS-002 |
| V3-ACCEPTANCE-001 | Final gate | All tasks above |

## Recommended Execution Order

`MEMORY-002 -> TRACE-002 -> CAPABILITY-002 -> MULTI-AGENT-001 ->`
`MULTI-AGENT-002 -> EVAL-001 -> MCP-002 -> PROACTIVE-001 ->`
`V3-ACCEPTANCE-001`

Each task must be implemented with tests first, validated with the commands in
its `tests.md`, and committed separately.
