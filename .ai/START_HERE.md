# START HERE — AI Handoff Protocol

You are continuing an existing production-oriented secure surveillance platform.

This is NOT a greenfield project.

Before modifying anything:

1. Read `.ai/00_CONTEXT.md`.
2. Read `.ai/01_CURRENT_STATE.md`.
3. Read `.ai/02_ARCHITECTURE.md`.
4. Read `.ai/03_SECURITY_MODEL.md`.
5. Read `.ai/04_DATA_MODEL.md`.
6. Read `.ai/05_API_CONTRACT.md`.
7. Read `.ai/06_CUSTODY_INTEGRITY.md`.
8. Read `.ai/07_AI_ENGINE.md`.
9. Read `.ai/08_DECISIONS.md`.
10. Read `.ai/09_KNOWN_ISSUES.md`.
11. Read `.ai/10_ROADMAP.md`.
12. Inspect the actual source files relevant to the requested task.
13. Inspect tests and migrations before changing security-sensitive code.

## Behaviour rules

- Do not assume missing requirements.
- Do not invent files, endpoints, fields, permissions, models, or architectural layers.
- Treat source code, tests, migrations, and current configuration as higher authority than this memory.
- Do not redesign the architecture unless the task requires it and the reason is explained.
- Keep API routers thin.
- Preserve authentication, authorization, audit, evidence integrity, and custody invariants.
- Do not weaken a security control simply to make tests pass.
- Prefer small, reviewable changes.
- Run relevant tests and static checks after changes.
- Distinguish verified repository facts from assumptions.
- When context is ambiguous, state the ambiguity and inspect the repository rather than guessing.

## Before coding

First report:

1. Your understanding of the current architecture.
2. The exact files you inspected.
3. The current state of the requested feature.
4. Relevant security/data invariants.
5. Any contradictions between documentation and implementation.
6. The smallest safe implementation plan.

Only then modify code unless the user explicitly asks for immediate implementation.
