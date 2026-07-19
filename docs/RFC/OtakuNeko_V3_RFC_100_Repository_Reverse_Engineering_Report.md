# OtakuNeko V3 RFC-100 Repository Reverse Engineering Report

## Purpose

This document describes the current OtakuNeko codebase before
refactoring.

This RFC is intended for AI Coding Agents.

The agent MUST read this document before modifying code.

The purpose is not to redesign the system, but to understand:

-   current modules
-   existing behavior
-   migration boundaries
-   dangerous areas

------------------------------------------------------------------------

# 1. Repository Overview

Repository:

OtakuNeko

Current architecture:

    Frontend

        |

    FastAPI Backend

        |

    Service Layer

        |

    LangGraph Agent

        |

    Tools

        |

    Database / External APIs

The project is already an AI application, but the Agent layer is
currently embedded inside the application layer.

------------------------------------------------------------------------

# 2. Current Technology Stack

## Backend

Language:

    Python

Framework:

    FastAPI

Database:

    SQLAlchemy
    Alembic
    SQLite/PostgreSQL compatible

------------------------------------------------------------------------

## Agent System

Current:

    LangGraph

    +

    LangChain Tools

    +

    OpenAI Compatible Chat Model

Main files:

    backend/app/agents/

    graph.py

    tools.py

    nodes/

------------------------------------------------------------------------

# 3. Current Backend Structure

Important directories:

    backend/app/

    ├── agents/
    │   ├── graph.py
    │   ├── tools.py
    │   └── nodes/

    ├── memory/

    ├── api/

    ├── services/

    ├── repositories/

    ├── models/

    ├── schemas/

    ├── clients/

    └── worker/

------------------------------------------------------------------------

# 4. Current Agent Architecture

Current execution flow:

    HTTP Request

    ↓

    api/v1/agent.py

    ↓

    ChatWorkflow

    ↓

    LangGraph StateGraph

    ↓

    Agent Node

    ↓

    Tool Node

    ↓

    Services

    ↓

    Database/API

    ↓

    Streaming Response

------------------------------------------------------------------------

# 5. Current Agent Implementation

Main class:

    ChatWorkflow

Location:

    backend/app/agents/graph.py

Responsibilities:

-   create LangGraph workflow
-   initialize LLM
-   bind tools
-   execute streaming chat

Current graph:

    START

    ↓

    agent node

    ↓

    tools node (conditional)

    ↓

    agent node

------------------------------------------------------------------------

# 6. Current Tools

Location:

    backend/app/agents/tools.py

Current tools include:

-   get_anime_info
-   fetch_audience_reviews
-   get_anime_staff
-   get_anime_cast
-   search_anime_advanced
-   get_current_time
-   generate_user_profile_tool

Important:

Tools currently directly represent external abilities.

Future migration:

    Tool

    ↓

    Capability Adapter

    ↓

    Capability Runtime

------------------------------------------------------------------------

# 7. Current Memory System

Location:

    backend/app/memory/

Current components:

    memory/

    ├── manager.py

    ├── short_term.py

    ├── long_term.py

    └── retrievers/

Current model:

    Conversation

    ↓

    Short Term Memory

    ↓

    Fact Extraction

    ↓

    Long Term Memory

This is already close to future Harness Memory.

DO NOT delete.

Refactor incrementally.

------------------------------------------------------------------------

# 8. Current API Layer

Main Agent API:

    backend/app/api/v1/agent.py

Responsibilities:

-   receive chat request
-   load memory manager
-   initialize workflow
-   stream response

Important compatibility:

Existing frontend depends on this API.

DO NOT break endpoint contracts during early migration.

------------------------------------------------------------------------

# 9. Current Service Layer

Location:

    backend/app/services/

Responsibilities:

-   Bangumi operations
-   user operations
-   collection operations
-   schedule operations
-   external integrations

This layer should become the foundation of future Capability Layer.

Migration direction:

    services

    ↓

    capabilities

    ↓

    MCP

------------------------------------------------------------------------

# 10. Existing Stable Features

Coding Agents MUST preserve:

-   user authentication
-   Bangumi synchronization
-   anime information query
-   collection management
-   schedule management
-   AI chat streaming
-   user profile generation
-   memory retrieval

------------------------------------------------------------------------

# 11. Refactoring Rules

## Allowed

Adding:

    harness/

    agents/base/

    capabilities/

    agent_runtime/

    trace/

Creating adapters around existing code.

------------------------------------------------------------------------

## Forbidden in early phases

DO NOT:

-   rewrite FastAPI
-   replace database layer
-   remove LangGraph immediately
-   rewrite frontend APIs
-   delete existing memory implementation
-   change existing user data models without migration

------------------------------------------------------------------------

# 12. Target Migration Direction

Current:

    API

    ↓

    ChatWorkflow

    ↓

    Tools

    ↓

    Services

Target:

    API

    ↓

    Harness Runtime

    ↓

    Agent Router

    ↓

    Agents

    ↓

    Capabilities

    ↓

    Services/MCP

------------------------------------------------------------------------

# 13. First Refactoring Principle

The first version of V3 should be an additive refactor.

Meaning:

Old system:

    continue working

New system:

    wrap old behavior with new abstractions

Only after migration is complete should old structures be removed.

------------------------------------------------------------------------

# 14. Coding Agent Instruction

Before modifying code:

1.  Read this RFC.
2.  Inspect existing implementation.
3.  Make the smallest possible change.
4.  Do not redesign unrelated modules.
5.  Run existing tests.

The goal is controlled migration, not rewriting.
