# Repo Guide

Read order:
- `memory.md`
- `docs/tasks/current.md`
- `docs/context/project.md`
- `docs/rules/output.md`
- `docs/rules/workflow.md`

Then use:
- `docs/context/architecture.md`
- `docs/context/decisions.md`
- `docs/features/*`
- `docs/tasks/backlog.md`

Rules:
- Keep responses under 300 words
- Do not modify `docs/scratch/*`
- Follow existing structure
- Always dispatch project subagents; do not skip them because a task looks small. See `docs/rules/workflow.md`
- After every completed development task, commit on a topic branch, push, and open a GitHub pull request. Do not wait to be asked. See `docs/rules/workflow.md`
- In this repo, `/routine` means run the full persisted routine workflow, then verify SQLite persistence and `git status --short`
- Cursor project skills in `.cursor/skills/` are the operator path for `/routine`, `/run`, and refresh-data; Codex plugin copies are unused fallback
- GitHub issues are the requirement tickets; update or create them when work starts, ships, or the spec changes
- Do not use Codex-style structure: no `codex/` branches, no Superpowers spec/plan files unless asked
- Use `memory.md` for durable repo memory: decisions, gotchas, workflows, and other expensive-to-rediscover context
- After every development change, update relevant Markdown in `docs/features/`, `docs/context/`, `docs/tasks/`, or `memory.md`
- Use `DOCS_NOT_NEEDED: <reason>` in `docs/tasks/current.md` or the final response only when documentation is deliberately unnecessary
