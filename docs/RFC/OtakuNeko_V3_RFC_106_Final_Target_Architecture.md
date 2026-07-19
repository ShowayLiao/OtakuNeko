# OtakuNeko V3 RFC-106 Final Target Architecture

## Purpose

Define the final target architecture after migration.

------------------------------------------------------------------------

# 1. Vision

OtakuNeko becomes:

> Personal Anime Agent Operating System

Not only a chatbot.

------------------------------------------------------------------------

# 2. Final Architecture

                        User

                         |

                 Interaction Layer

                         |

                 Agent Harness OS


         Runtime

         Planner

         Memory

         Policy

         Evaluation

         Scheduler


                         |

                  Agent Intelligence


         Companion Agent

         Anime Agent

         Recommendation Agent

         Schedule Agent


                         |

                  Capability Layer


         Anime Capability

         Media Capability

         Calendar Capability

         Community Capability


                         |

                     MCP Layer


                         |

                  External Systems


                         |

                  Knowledge Platform


         PostgreSQL

         Vector Database

         Graph Database

------------------------------------------------------------------------

# 3. Core Components

## Harness Kernel

Responsible for:

-   execution
-   state
-   lifecycle
-   events

------------------------------------------------------------------------

## Agent Layer

Responsible for:

-   reasoning
-   planning
-   decisions

------------------------------------------------------------------------

## Memory Layer

Responsible for:

-   user understanding
-   preference evolution
-   historical knowledge

------------------------------------------------------------------------

## Capability Layer

Responsible for:

-   real world actions

------------------------------------------------------------------------

# 4. Long Term Evolution

Future capabilities:

    Season Analysis

    Automatic Watch Planning

    Community Intelligence

    Media Library Management

    Personal Anime Reports

------------------------------------------------------------------------

# 5. Architectural Principles

## Principle 1

LLM is replaceable.

Architecture should not depend on one model.

------------------------------------------------------------------------

## Principle 2

Memory is the long-term asset.

The user's evolving preference model is the core value.

------------------------------------------------------------------------

## Principle 3

Capabilities are modular.

New abilities should be added without modifying agents.

------------------------------------------------------------------------

## Principle 4

Everything should be observable.

Agent decisions must be traceable.

------------------------------------------------------------------------

# 6. Final Dependency Direction

    Frontend

    ↓

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

    Data

No reverse dependency.

------------------------------------------------------------------------

# 7. Success Criteria

OtakuNeko V3 is complete when:

-   multiple agents cooperate
-   memory improves over time
-   capabilities are modular
-   tasks can run proactively
-   system can evolve through AI-assisted development

------------------------------------------------------------------------

# Conclusion

The final goal is not an AI chatbot.

It is a continuously evolving personal intelligence system.
