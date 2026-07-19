# OtakuNeko V3 RFC-107 AI Agent Execution Playbook

## Purpose

This document defines the standard operating procedure for AI Coding
Agents working on the OtakuNeko V3 migration.

The goal:

> Make AI agents execute software engineering tasks safely, predictably,
> and incrementally.

This document should be treated as the execution manual for:

-   DeepSeek Coding Agent
-   Claude Code
-   GPT-based coding agents
-   Cursor Agent
-   Other autonomous coding systems

------------------------------------------------------------------------

# 1. Agent Role Definition

The AI Coding Agent is:

    Implementation Engineer

It is NOT:

    Architecture Owner

Architecture decisions come from:

    RFC Documents

The agent responsibility:

    Understand

    ↓

    Implement

    ↓

    Verify

    ↓

    Report

------------------------------------------------------------------------

# 2. Required Context Loading

Before any code modification, the agent MUST read:

## Architecture and Implementation Rules

    RFC-100
    RFC-101
    RFC-102
    RFC-103
    RFC-104
    RFC-105
    RFC-106

These RFCs are the numbered architecture and implementation references
currently present in this repository.

## Current Task

    TASK-xxx.md

------------------------------------------------------------------------

# 3. Execution Lifecycle

Every task follows:

    Task Received

    ↓

    Context Analysis

    ↓

    Implementation Plan

    ↓

    Human Approval

    ↓

    Code Modification

    ↓

    Testing

    ↓

    Review Report

    ↓

    Commit

------------------------------------------------------------------------

# 4. Phase 1: Context Analysis

Before writing code:

The agent MUST inspect:

-   related files
-   dependency relationships
-   existing tests
-   current behavior

The agent MUST answer:

    What exists now?

    What changes are required?

    What must not change?

------------------------------------------------------------------------

# 5. Phase 2: Planning

Before implementation, generate:

## Change Plan

Example:

    Files to modify:

    backend/app/harness/runtime.py

    backend/app/api/v1/agent.py


    Reason:

    Add runtime abstraction.


    Risk:

    Streaming response compatibility.

------------------------------------------------------------------------

## Dependency Analysis

Example:

    Current:

    API -> ChatWorkflow


    After:

    API -> Runtime -> Adapter -> ChatWorkflow

------------------------------------------------------------------------

# 6. Approval Gate

For important changes:

The agent MUST wait after planning.

User response:

    Proceed

allows implementation.

This prevents uncontrolled refactoring.

------------------------------------------------------------------------

# 7. Implementation Rules

## Rule 1: Minimal Diff

Prefer:

    Adapter

    Wrapper

    Interface

over:

    Rewrite

------------------------------------------------------------------------

## Rule 2: Preserve Behavior

Existing behavior has priority.

Never break:

-   API contracts
-   frontend communication
-   database compatibility
-   existing user data

------------------------------------------------------------------------

## Rule 3: Respect Architecture Boundaries

Allowed dependency:

    API

    ↓

    Harness

    ↓

    Agents

    ↓

    Capabilities

    ↓

    Services

    ↓

    Repositories

    ↓

    Database

Forbidden:

    Agent -> Database

    Capability -> API

    Database -> Agent

------------------------------------------------------------------------

# 8. Testing Procedure

After modification:

Run:

    Unit Tests

    Integration Tests

    Regression Tests

Minimum:

    pytest

If available:

    ruff

    mypy

------------------------------------------------------------------------

# 9. Completion Report Format

After finishing, the agent MUST output:

## Changed Files

Example:

    Added:

    backend/app/harness/runtime.py

    Modified:

    backend/app/api/v1/agent.py

------------------------------------------------------------------------

## Implementation Summary

Example:

    Added runtime wrapper.

    Existing LangGraph workflow unchanged.

------------------------------------------------------------------------

## Tests

Example:

    pytest:

    PASS

------------------------------------------------------------------------

## Risks

Example:

    Future checkpoint persistence not implemented.

------------------------------------------------------------------------

# 10. Failure Handling

If the agent discovers:

-   unclear architecture
-   conflicting requirements
-   missing dependencies
-   dangerous migration

It MUST stop and report.

Do NOT guess.

------------------------------------------------------------------------

# 11. Rollback Rules

Every change should be reversible.

Preferred:

    Small commits

    Clear commit messages

    Independent migration steps

------------------------------------------------------------------------

# 12. Commit Convention

Use:

    feat(module): change

    refactor(module): change

    test(module): change

    docs(module): change

Examples:

    feat(harness): add AgentRuntime

    refactor(memory): extract MemoryService

------------------------------------------------------------------------

# 13. Long Running Migration Rules

During V3 migration:

The system must remain runnable.

Never create a state where:

    Old system removed

    New system incomplete

Always prefer:

    Old system

    +

    New abstraction

    +

    Gradual migration

------------------------------------------------------------------------

# 14. AI Agent Quality Checklist

Before completing any task:

    [ ] Read RFC

    [ ] Read task definition

    [ ] Inspected existing code

    [ ] Created implementation plan

    [ ] Modified only required files

    [ ] Added tests

    [ ] Ran validation

    [ ] Generated report

------------------------------------------------------------------------

# Conclusion

The AI Coding Agent is a controlled engineering executor.

The success pattern:

    Good Architecture

    +

    Small Tasks

    +

    Strict Validation

    +

    Continuous Review

The objective is not fast code generation.

The objective is safe evolution of OtakuNeko.
