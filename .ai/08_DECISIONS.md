# Decisions

## D-001 — Backend is feature-oriented

Backend domain code lives under `backend/app/modules/<feature>`.

## D-002 — Security-sensitive business logic stays out of routers

Routers are transport/API adapters. Domain rules belong in services/repositories/security modules.

## D-003 — Evidence is treated as forensic data

Evidence has cryptographic hashes, encryption, manifest data, signing, verification, and controlled storage.

## D-004 — Custody records are append-only

Database triggers prevent mutation of historical custody records.

## D-005 — Custody uses deterministic canonical hashing

Custody integrity uses versioned canonical JSON and SHA-256.

## D-006 — Custody lifecycle needs idempotency

The current database migration adds custody lifecycle idempotency scope/key and uniqueness constraints.

## D-007 — Public AI contracts should remain stable

The production detector must adapt to the existing detector/schema/registry/processor/API contracts rather than forcing a redesign of those interfaces.

## D-008 — Production model loading must be controlled

Phase 5.2 documentation requires model loading during application lifecycle, not module import, and tests must not depend on production model weights.

## D-009 — Repository evidence beats stale planning documents

Several project documents still describe earlier phases. Current source, tests, and migrations are more authoritative.

## D-010 — Do not silently solve security gaps by weakening guarantees

If an implementation is difficult because of integrity, authorization, audit, or concurrency requirements, preserve the requirement and redesign the implementation safely.
