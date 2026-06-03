# Repo Guide

Read order:
- `memory.md`
- `docs/tasks/current.md`
- `docs/context/project.md`
- `docs/rules/output.md`

Then use:
- `docs/context/architecture.md`
- `docs/context/decisions.md`
- `docs/features/*`
- `docs/tasks/backlog.md`

Rules:
- Keep responses under 300 words
- Do not modify `docs/scratch/*`
- Follow existing structure
- Use `memory.md` for durable repo memory: decisions, gotchas, workflows, and other expensive-to-rediscover context
- After every development change, update relevant Markdown in `docs/features/`, `docs/context/`, `docs/tasks/`, or `memory.md`
- Use `DOCS_NOT_NEEDED: <reason>` in `docs/tasks/current.md` or the final response only when documentation is deliberately unnecessary
