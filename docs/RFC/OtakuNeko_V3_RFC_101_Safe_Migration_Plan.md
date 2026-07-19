# OtakuNeko V3 RFC-101 Safe Migration Plan

## Purpose

This document defines the migration strategy from the current OtakuNeko
V2 architecture into the V3 Harness Agent architecture.

This RFC is written for AI Coding Agents.

The primary goal:

> Add the new architecture without breaking existing product behavior.

------------------------------------------------------------------------

# 1. Migration Philosophy

The migration MUST follow:

    Add abstraction

    ↓

    Migrate behavior

    ↓

    Verify compatibility

    ↓

    Remove legacy code later

The migration MUST NOT follow:

    Delete old system

    ↓

    Rewrite everything

    ↓

    Hope it works

------------------------------------------------------------------------

# 2. Core Rules For Coding Agents

Before every task:

1.  Read RFC-100.
2.  Understand affected modules.
3.  Modify only declared scope.
4.  Preserve existing behavior.
5.  Run tests after changes.

------------------------------------------------------------------------

# 3. Migration Stages Overview

    Phase 0

    Repository stabilization


    Phase 1

    Introduce Harness Runtime


    Phase 2

    Introduce Agent Interfaces


    Phase 3

    Introduce Capability Layer


    Phase 4

    Upgrade Memory Architecture


    Phase 5

    Multi-Agent Migration


    Phase 6

    MCP Extraction

------------------------------------------------------------------------

# Phase 0: Repository Stabilization

## Objective

Prepare the codebase for safe migration.

## Actions

Create:

    docs/rfc/

    tests/agent/

Ensure:

-   existing tests pass
-   current APIs documented
-   current behavior recorded

------------------------------------------------------------------------

## Forbidden

Do not:

-   change business logic
-   rename large modules
-   modify database schema

------------------------------------------------------------------------

# Phase 1: Introduce Harness Runtime

## Objective

Create an execution abstraction around the existing Agent.

Current:

    API

    ↓

    ChatWorkflow

    ↓

    LangGraph

Target:

    API

    ↓

    AgentRuntime

    ↓

    ChatWorkflow Adapter

    ↓

    LangGraph

------------------------------------------------------------------------

# New Files

Create:

    backend/app/harness/

    ├── runtime.py

    ├── state.py

    └── task.py

------------------------------------------------------------------------

# AgentRuntime Responsibility

AgentRuntime should:

-   receive tasks
-   maintain execution state
-   invoke existing agents
-   return results

It should NOT:

-   implement anime logic
-   replace LangGraph
-   access database directly

------------------------------------------------------------------------

# Phase 1 Acceptance Criteria

PASS:

    Existing chat API works.

    Streaming response unchanged.

    Existing tools continue working.

------------------------------------------------------------------------

# Phase 2: Introduce Agent Interface

## Objective

Separate Agent abstraction from implementation.

Create:

    backend/app/agents/base.py

Example interface:

``` python
class BaseAgent:

    async def execute(task):
        pass
```

------------------------------------------------------------------------

# Rules

Existing:

    ChatWorkflow

becomes:

    LangGraphAgentAdapter

Do not immediately rewrite graph logic.

------------------------------------------------------------------------

# Phase 3: Introduce Capability Layer

## Objective

Move from Tool-oriented design to Capability-oriented design.

Current:

    Agent

    ↓

    Tool

    ↓

    Service

Target:

    Agent

    ↓

    Capability

    ↓

    Service

------------------------------------------------------------------------

# New Structure

    capabilities/

    ├── anime.py

    ├── recommendation.py

    └── schedule.py

------------------------------------------------------------------------

# Migration Example

Before:

``` python
get_anime_info()
```

After:

``` python
AnimeCapability.get_info()
```

Internal implementation can still call existing services.

------------------------------------------------------------------------

# Phase 4: Memory Architecture Upgrade

## Objective

Separate memory concerns.

Current:

    MemoryManager

Target:

    MemoryService

    +

    MemoryRepository

    +

    MemoryExtractor

------------------------------------------------------------------------

# New Memory Types

## Short Term Memory

Current conversation state.

## Episodic Memory

User events.

Example:

    User watched anime X

## Semantic Memory

Extracted preferences.

Example:

    User likes psychological anime

## Profile Memory

Stable user model.

------------------------------------------------------------------------

# Phase 5: Multi-Agent Migration

## Objective

Split responsibilities.

Current:

    ChatWorkflow

Target:

    AgentRouter

    |

    + AnimeAgent

    + RecommendationAgent

    + CompanionAgent

------------------------------------------------------------------------

# Migration Rule

Do not split all agents at once.

Order:

1.  Recommendation Agent
2.  Anime Knowledge Agent
3.  Companion Agent

------------------------------------------------------------------------

# Phase 6: MCP Extraction

## Objective

Externalize capabilities.

Target:

    Capability

    ↓

    MCP Server

    ↓

    External System

------------------------------------------------------------------------

# Initial MCP Candidates

Priority:

1.  Anime data
2.  Calendar
3.  Media management

------------------------------------------------------------------------

# Database Migration Policy

During migration:

Allowed:

    Add new tables

    agent_task

    agent_trace

    agent_memory

Forbidden:

    Modify existing user/anime tables

    without migration plan

------------------------------------------------------------------------

# Testing Strategy

Every migration phase requires:

## Regression Test

Existing features work.

## Unit Test

New module behavior works.

## Integration Test

New architecture connects correctly.

------------------------------------------------------------------------

# Commit Strategy

Each migration should be a small independent commit.

Recommended format:

    feat(harness): introduce AgentRuntime

    feat(memory): add semantic memory service

    refactor(agent): add agent interface

------------------------------------------------------------------------

# Rollback Strategy

Every migration step must be reversible.

If a migration breaks behavior:

Rollback to previous stable commit.

------------------------------------------------------------------------

# Final Migration Target

After completion:

    API

    ↓

    Harness Runtime

    ↓

    Agent Router

    ↓

    Specialized Agents

    ↓

    Capabilities

    ↓

    Services/MCP

    ↓

    Data Layer

------------------------------------------------------------------------

# Conclusion

The V3 migration is not a rewrite.

It is an evolutionary architecture upgrade.

The Coding Agent should behave like an engineer performing controlled
refactoring, not like an architect replacing the entire system.
