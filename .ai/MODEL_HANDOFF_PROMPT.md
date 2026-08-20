# Portable Model Handoff Prompt

Use this with ChatGPT, DeepSeek, Qwen, Claude, Gemini, Amazon Q, or another coding AI.

You are joining an existing Secure Surveillance Platform repository.

The project has an AI-agnostic project memory system under `.ai/`.

Before doing any work:

1. Read `.ai/START_HERE.md`.
2. Read the `.ai` documents in the order specified there.
3. Inspect the actual repository files relevant to the task.
4. Inspect tests and migrations for the relevant subsystem.

Do not treat this as a greenfield project.

The repository is the source of truth. The `.ai` files provide project intent, history, invariants, and current-state guidance, but must be reconciled with the current implementation.

Do not invent missing requirements.

For security-sensitive code, preserve:
- authentication
- authorization
- auditability
- evidence integrity
- evidence confidentiality
- cryptographic verification
- custody immutability
- idempotency
- transaction/concurrency guarantees

Before changing code, report:
- what you understand
- what files you inspected
- what is currently implemented
- what is missing
- any contradictions
- your proposed minimal change

Then implement only the requested/approved change.

After implementation:
- run relevant tests
- report failures honestly
- update `.ai/01_CURRENT_STATE.md`
- update `.ai/09_KNOWN_ISSUES.md` if necessary
- record architectural/security decisions in `.ai/08_DECISIONS.md`
