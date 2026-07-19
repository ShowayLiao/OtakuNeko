# OtakuNeko V3 RFC-104 Test Strategy

## Purpose

This document defines the testing strategy for OtakuNeko V3 refactoring.

The objective:

> Ensure architecture evolution without breaking existing behavior.

This document is written for AI Coding Agents.

------------------------------------------------------------------------

# 1. Testing Philosophy

Refactoring success is not:

    new architecture exists

It is:

    new architecture exists

    +

    old behavior preserved

------------------------------------------------------------------------

# 2. Testing Layers

The test system contains:

                    End-to-End Tests

                           |

                  Integration Tests

                           |

                     Unit Tests

                           |

                 Static Validation

------------------------------------------------------------------------

# 3. Unit Tests

Purpose:

Verify individual modules.

Examples:

    HarnessRuntime

    AgentState

    MemoryService

    CapabilityAdapter

Requirements:

-   deterministic
-   fast
-   isolated

------------------------------------------------------------------------

# 4. Integration Tests

Verify module communication.

Examples:

    API

    ↓

    Harness Runtime

    ↓

    Agent

    ↓

    Capability

Important scenarios:

-   chat request flow
-   streaming response
-   memory retrieval
-   tool execution

------------------------------------------------------------------------

# 5. Regression Tests

Existing features MUST continue working.

Required coverage:

    User authentication

    Anime query

    Collection management

    Schedule management

    AI chat

    Memory retrieval

------------------------------------------------------------------------

# 6. Agent Evaluation Tests

Traditional tests are insufficient for LLM systems.

Add:

    evaluation/

    datasets/

    judges/

    metrics/

------------------------------------------------------------------------

Metrics:

## Recommendation Agent

-   relevance
-   personalization
-   diversity

## Companion Agent

-   consistency
-   memory usage
-   response quality

------------------------------------------------------------------------

# 7. Golden Test Cases

Create fixed scenarios.

Example:

    User:

    I like EVA and Steins;Gate


    Expected:

    Recommendation contains psychological sci-fi works

    Reasoning references user preference

------------------------------------------------------------------------

# 8. Migration Testing Rule

Every migration phase requires:

Before:

    existing tests pass

After:

    existing tests pass

    +

    new tests pass

------------------------------------------------------------------------

# 9. AI Agent Verification Requirement

After coding, the agent MUST report:

    Tests executed:

    Result:

    Failures:

    Risk:

------------------------------------------------------------------------

# 10. Definition of Success

A migration is complete when:

    Functionality preserved

    Architecture improved

    Tests green

    Documentation updated
