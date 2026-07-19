# HARNESS-001 Step 03 Create AgentRuntime

## Objective

Create runtime execution wrapper.

## Runtime responsibilities

-   receive task
-   create state
-   invoke adapter
-   return result

## Non Goals

Do not implement new reasoning. Do not replace LangGraph.

## Acceptance

Runtime can execute a mocked agent.
