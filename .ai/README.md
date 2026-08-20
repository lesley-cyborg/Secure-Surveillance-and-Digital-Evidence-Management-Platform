# Secure Surveillance Platform — AI-Agnostic Project Memory

This directory is the project's portable knowledge base for AI coding assistants.

It is intentionally model/vendor neutral. It is not "ChatGPT memory"; it is project documentation stored with the repository.

## Read order

A new AI should read:

1. `00_CONTEXT.md`
2. `01_CURRENT_STATE.md`
3. `02_ARCHITECTURE.md`
4. `03_SECURITY_MODEL.md`
5. `04_DATA_MODEL.md`
6. `05_API_CONTRACT.md`
7. `06_CUSTODY_INTEGRITY.md`
8. `07_AI_ENGINE.md`
9. `08_DECISIONS.md`
10. `09_KNOWN_ISSUES.md`
11. `10_ROADMAP.md`
12. `11_SOURCE_MAP.md`
13. `START_HERE.md`

## Authority rule

The actual repository is authoritative.

If these documents disagree with code, tests, migrations, or configuration, inspect the repository and update the memory rather than blindly following stale documentation.

## Security rule

Do not copy `.env`, `.secrets`, private keys, tokens, passwords, model weights, caches, virtual environments, or generated artifacts into `.ai/`.

## Maintenance

After a significant architectural or security decision:
- update `08_DECISIONS.md`
- update `01_CURRENT_STATE.md`
- update the relevant domain document

After a meaningful feature/fix:
- update `01_CURRENT_STATE.md`
- add unresolved items to `09_KNOWN_ISSUES.md` if applicable

After changing the roadmap:
- update `10_ROADMAP.md`
