# OtakuNeko V3 RFC-105 CI/CD Agent Workflow

## Purpose

Define how AI Coding Agents participate in the software development
workflow.

------------------------------------------------------------------------

# 1. Development Model

The workflow:

    Requirement

    ↓

    RFC Task

    ↓

    AI Agent Implementation

    ↓

    Validation

    ↓

    Human Review

    ↓

    Merge

------------------------------------------------------------------------

# 2. Task Lifecycle

Every change begins with a task document.

Example:

    TASK-HARNESS-001

    Goal:
    Introduce AgentRuntime

    Scope:
    backend/app/harness

    Acceptance:
    Existing API unchanged

------------------------------------------------------------------------

# 3. AI Agent Workflow

## Step 1: Understand

Agent reads:

    RFC documents

    Current code

    Task definition

------------------------------------------------------------------------

## Step 2: Plan

Agent provides:

-   files to modify
-   implementation approach
-   risks

------------------------------------------------------------------------

## Step 3: Implement

Rules:

-   minimal changes
-   follow architecture
-   avoid unrelated refactor

------------------------------------------------------------------------

## Step 4: Validate

Run:

    pytest

    lint

    type check

    integration tests

------------------------------------------------------------------------

## Step 5: Report

Output:

    Changed files:

    Implementation summary:

    Tests:

    Known risks:

------------------------------------------------------------------------

# 4. Pull Request Requirements

Every PR should include:

    Related RFC

    Task ID

    Architecture impact

    Testing result

------------------------------------------------------------------------

# 5. Automated Checks

CI should verify:

    Unit tests

    Integration tests

    Lint

    Type checking

    Migration safety

------------------------------------------------------------------------

# 6. AI Safety Rules

CI should reject:

-   unexpected file changes
-   missing tests
-   database changes without migration
-   API breaking changes

------------------------------------------------------------------------

# 7. Continuous Improvement

Evaluation results should feed back into:

    RFC updates

    Agent prompts

    Test datasets

------------------------------------------------------------------------

# Conclusion

The AI Agent becomes part of the engineering workflow, but remains
constrained by:

    RFC

    Tests

    Review
