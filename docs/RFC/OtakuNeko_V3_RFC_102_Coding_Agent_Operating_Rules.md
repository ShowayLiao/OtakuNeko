# OtakuNeko V3 RFC-102 Coding Agent Operating Rules

## Purpose

This document defines the operating rules for AI Coding Agents modifying
the OtakuNeko codebase.

Target agents:

-   DeepSeek Coder
-   Claude Code
-   GPT-based coding agents
-   Other autonomous software agents

The purpose is to reduce unsafe modifications and ensure predictable
refactoring.

------------------------------------------------------------------------

# 1. Role Definition

The Coding Agent is not an architect.

The Coding Agent acts as:

    Senior Software Engineer

    under

    Architecture Constraints

The agent MUST:

-   follow RFC documents
-   minimize changes
-   preserve existing behavior
-   ask when requirements are unclear

The agent MUST NOT:

-   redesign the whole system
-   introduce unrelated improvements
-   replace frameworks without approval

------------------------------------------------------------------------

# 2. Mandatory Reading Order

Before modifying code, read:

    RFC-001 Agent OS Architecture

    RFC-002 Data Architecture

    RFC-003 Agent Runtime

    RFC-004 Capability Architecture

    RFC-005 Agent Intelligence

    RFC-100 Repository Analysis

    RFC-101 Migration Plan

    RFC-102 Coding Rules

The agent should understand both:

-   target architecture
-   current implementation

------------------------------------------------------------------------

# 3. Change Scope Rules

Every task has a defined scope.

Example:

    Task:

    Introduce AgentRuntime

    Allowed:

    backend/app/harness/*
    backend/app/api/v1/agent.py


    Forbidden:

    frontend/*
    database/*
    memory/*

The agent MUST NOT modify files outside scope unless required.

------------------------------------------------------------------------

# 4. Minimal Change Principle

Preferred:

    small change

    +

    existing compatibility

Avoid:

    large rewrite

    +

    new architecture

    +

    behavior changes

------------------------------------------------------------------------

# 5. Before Coding Procedure

Before writing code:

The agent MUST:

## Step 1

Inspect existing files.

## Step 2

Identify dependencies.

## Step 3

Explain planned changes.

## Step 4

Identify possible risks.

Example:

    Plan:

    1. Add runtime wrapper.
    2. Move execution entry point.
    3. Keep LangGraph unchanged.

    Risk:

    API streaming behavior may be affected.

------------------------------------------------------------------------

# 6. During Coding Rules

## Rule 1

Do not delete existing functionality.

------------------------------------------------------------------------

## Rule 2

Prefer adapters over rewrites.

Example:

Good:

    LegacyTool

    ↓

    CapabilityAdapter

    ↓

    New Runtime

Bad:

    Delete LegacyTool

    Rewrite everything

------------------------------------------------------------------------

## Rule 3

Do not duplicate business logic.

Bad:

    old recommendation logic

    +

    new recommendation logic

Good:

    new interface

    ↓

    existing service

------------------------------------------------------------------------

# 7. Dependency Rules

Target dependency direction:

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

    Database

    ↓

    Agent

    Capability

    ↓

    API

    Service

    ↓

    Frontend

------------------------------------------------------------------------

# 8. Agent Specific Rules

## LLM Code

Do not hardcode:

-   prompts
-   model names
-   API keys

Use configuration.

------------------------------------------------------------------------

## Memory Code

Memory changes require special care.

Do not:

-   overwrite user history
-   delete memories
-   change meaning of stored facts

without migration.

------------------------------------------------------------------------

## Database Code

Database changes require:

-   migration script
-   rollback plan
-   compatibility check

------------------------------------------------------------------------

# 9. Testing Requirements

Every code modification requires validation.

Minimum:

    pytest

If available:

    ruff

    mypy

    integration tests

------------------------------------------------------------------------

# 10. Output Report Requirement

After completing a task, the agent MUST provide:

## Changed Files

Example:

    Modified:

    backend/app/harness/runtime.py

    backend/app/api/v1/agent.py

------------------------------------------------------------------------

## Summary

Example:

    Added AgentRuntime wrapper.

    Existing LangGraph workflow unchanged.

------------------------------------------------------------------------

## Verification

Example:

    pytest: PASS

    API compatibility: PASS

------------------------------------------------------------------------

## Remaining Risks

Example:

    Memory migration not included.

------------------------------------------------------------------------

# 11. Handling Uncertainty

When requirements are unclear:

The agent MUST NOT guess major architecture decisions.

Instead:

    State assumption

    Explain impact

    Request confirmation

------------------------------------------------------------------------

# 12. Forbidden Behaviors

The Coding Agent MUST NOT:

-   rewrite the project from scratch
-   rename large module trees without migration
-   remove working features
-   introduce unnecessary dependencies
-   change API contracts casually
-   modify unrelated files

------------------------------------------------------------------------

# 13. Commit Rules

Recommended commit format:

    feat(harness): add AgentRuntime

    refactor(memory): extract MemoryService

    test(agent): add runtime tests

Each commit should represent one logical change.

------------------------------------------------------------------------

# 14. Definition of Done

A task is complete only when:

    Code changed

    +

    Tests passed

    +

    Documentation updated

    +

    No existing behavior broken

------------------------------------------------------------------------

# Conclusion

The Coding Agent is a controlled implementation worker.

Architecture decisions belong to RFCs.

The agent's responsibility is:

    Understand

    ↓

    Modify safely

    ↓

    Verify

    ↓

    Report

The goal is continuous evolution of OtakuNeko, not uncontrolled
rewriting.
