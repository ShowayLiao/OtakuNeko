@AGENTS.md

## Claude Code platform adapter

- Shared repository policies are maintained in `AGENTS.md`; do not duplicate them here.
- Invoke personal skills by their unprefixed names with the Skill tool, such as `brainstorming` or `requesting-code-review`. These are local skills, not a `superpowers` plugin.
- Load `using-superpowers` at the beginning of a session. User instructions and existing authorization take precedence over skill approval rituals.
- The `chinese-*` reference skills are explicit-invocation only, as their descriptions specify.
- The Codex-only `model-router-luna` skill and `.codex/agents/luna_worker.toml` do not configure Claude subagents. Do not try to invoke Luna from Claude Code.
- The project-management skill is available at `.claude/skills/ticktick-project-system/SKILL.md`. Discover actual MCP schemas before external writes; never infer connectivity from a permissions allowlist.
- Claude lifecycle hooks are in `.claude/settings.local.json` and `.claude/hooks/`. They record Claude turns separately from Codex. Never infer successful validation from tool output when an exit code is absent.
