# Maintaining Project Memory

## When to update

Update `.ai/` when:

- architecture changes
- a security invariant changes
- a database migration changes the domain model
- a public API contract changes
- a feature is completed
- a major bug is discovered
- a decision is accepted/rejected
- the roadmap changes

## Update procedure

1. Change the code/tests/migrations first.
2. Run relevant validation.
3. Update the appropriate `.ai` document.
4. If a decision changed, add a new decision entry rather than silently rewriting history.
5. Update `01_CURRENT_STATE.md`.
6. Add unresolved issues to `09_KNOWN_ISSUES.md`.
7. Keep statements factual and repository-grounded.

## Decision format

Use:

```text
D-XXX — Short decision title

Status: Accepted / Superseded / Rejected

Context:
Why the decision was needed.

Decision:
What was chosen.

Alternatives:
What was considered.

Consequences:
What this changes or constrains.
```

## AI handoff rule

When switching AI models, do not paste the entire project into the conversation.

Give the model repository access and instruct it to read `.ai/START_HERE.md`.

For models without repository access, provide:
- `.ai/`
- the relevant source files
- relevant tests
- relevant migrations
