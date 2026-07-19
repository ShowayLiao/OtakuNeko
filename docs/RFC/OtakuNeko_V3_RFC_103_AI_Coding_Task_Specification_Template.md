# OtakuNeko V3 RFC-103 AI Coding Task Specification Template

## Purpose

This document defines the standard task format used by AI Coding Agents
during OtakuNeko V3 refactoring.

The purpose:

> Convert architecture decisions into controlled implementation tasks.

This document is the bridge between:

    Architecture RFC

            |

    Migration Plan

            |

    Coding Task

            |

    AI Agent Implementation

------------------------------------------------------------------------

# 1. Task Philosophy

An AI Coding Task MUST be:

-   specific
-   bounded
-   testable
-   reversible

A task is NOT:

    Rewrite Agent System

A task SHOULD be:

    Create AgentRuntime abstraction without changing existing Agent behavior.

------------------------------------------------------------------------

# 2. Task File Template

Recommended location:

    docs/tasks/

Example:

    TASK-HARNESS-001.md

------------------------------------------------------------------------

# 3. Task Metadata

Template:

``` yaml
Task ID:

Title:

Related RFC:

Priority:

Risk Level:

Owner:

Status:
```

Example:

``` yaml
Task ID:
HARNESS-001

Title:
Introduce AgentRuntime wrapper

Related RFC:
RFC-101

Risk Level:
Low
```

------------------------------------------------------------------------

# 4. Objective

Describe exactly what should be achieved.

Example:

    Create a Harness Runtime abstraction layer around the existing LangGraph workflow.

    The existing chat behavior must remain unchanged.

------------------------------------------------------------------------

# 5. Background Context

Explain why this task exists.

Example:

    Current system:

    API directly initializes ChatWorkflow.

    Problem:

    Agent execution lifecycle is coupled to API layer.

    Goal:

    Introduce runtime abstraction.

------------------------------------------------------------------------

# 6. Scope Definition

## Allowed Changes

List files or modules.

Example:

    Allowed:

    backend/app/harness/*

    backend/app/api/v1/agent.py

------------------------------------------------------------------------

## Forbidden Changes

Example:

    Forbidden:

    frontend/*

    database schema

    memory module

    existing tools

------------------------------------------------------------------------

# 7. Implementation Requirements

Describe required behavior.

Example:

    AgentRuntime MUST:

    - accept AgentTask
    - maintain execution state
    - call existing workflow
    - return compatible response

------------------------------------------------------------------------

# 8. Non Goals

This section is mandatory.

Example:

    This task does NOT:

    - replace LangGraph
    - create multi-agent system
    - modify database
    - redesign prompts

Purpose:

Prevent AI over-engineering.

------------------------------------------------------------------------

# 9. Implementation Guidance

Provide preferred approach.

Example:

    Preferred:

    Create adapter around existing ChatWorkflow.

    Avoid:

    Moving all logic into Runtime.

------------------------------------------------------------------------

# 10. Acceptance Criteria

A task is complete only when:

    [ ] Code implemented

    [ ] Existing behavior preserved

    [ ] Tests pass

    [ ] Documentation updated

------------------------------------------------------------------------

# 11. Testing Requirements

Every task must define verification.

Example:

    Required:

    pytest

    Agent API integration test

    Streaming response test

------------------------------------------------------------------------

# 12. Risk Assessment

Example:

    Risk:

    Changing API execution path may affect streaming.


    Mitigation:

    Keep old workflow implementation.
    Use adapter pattern.

------------------------------------------------------------------------

# 13. Rollback Plan

Every task needs rollback instructions.

Example:

    Rollback:

    Remove AgentRuntime adapter.

    Restore API direct workflow call.

------------------------------------------------------------------------

# 14. AI Agent Execution Protocol

Before coding:

Agent MUST:

    Read related RFCs

    Inspect current implementation

    Explain plan

    Identify risks

------------------------------------------------------------------------

During coding:

Agent MUST:

    Modify only scoped files

    Prefer minimal changes

    Preserve compatibility

------------------------------------------------------------------------

After coding:

Agent MUST report:

    Changed files:

    Implementation summary:

    Tests executed:

    Remaining risks:

------------------------------------------------------------------------

# 15. Example Completed Task

## TASK-HARNESS-001

Goal:

Add AgentRuntime layer.

------------------------------------------------------------------------

Scope:

    backend/app/harness/

    backend/app/api/v1/agent.py

------------------------------------------------------------------------

Implementation:

    Create runtime abstraction.

    Wrap existing ChatWorkflow.

    Keep LangGraph unchanged.

------------------------------------------------------------------------

Acceptance:

    Chat API works.

    Streaming unchanged.

    Tests pass.

------------------------------------------------------------------------

# 16. Task Naming Convention

Recommended:

    HARNESS-xxx

    MEMORY-xxx

    AGENT-xxx

    CAPABILITY-xxx

    MCP-xxx

    TEST-xxx

Examples:

    HARNESS-001

    MEMORY-001

    CAPABILITY-001

------------------------------------------------------------------------

# Conclusion

This template ensures that AI Coding Agents execute architecture changes
as controlled engineering tasks.

The agent should always follow:

    Understand

    ↓

    Plan

    ↓

    Implement

    ↓

    Verify

    ↓

    Report

The objective is not maximum code generation.

The objective is safe evolution of OtakuNeko.
