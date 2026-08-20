# Integrating the AI-Agnostic Memory

Copy the `.ai/` directory into the root of the surveillance repository:

```text
secure-surveillance-platform/
├── .ai/
├── backend/
├── ai-engine/
├── database/
├── documentation/
└── ...
```

Commit `.ai/` to Git.

Do NOT copy `.env`, `.secrets`, private keys, virtual environments, caches, or model weights into `.ai/`.

## First-use prompt

Give the AI access to the repository and send:

> Read `.ai/START_HERE.md` and the complete `.ai/` project memory. Then inspect the repository and reconcile the memory with the current implementation. Do not modify code yet. Report your understanding of the architecture, current state, security invariants, custody status, known documentation drift, and the next safest implementation step.

## Ongoing use

At the end of a substantial task, ask the AI:

> Update the `.ai/` project memory to reflect only verified changes from this task. Do not invent information.

This makes the repository portable between AI vendors.
