---
name: incremental-implementation
description: Build multi-file changes in small, verifiable slices. Use when implementing features, fixes, or refactors that touch more than one file.
---

# Incremental Implementation

Use this skill when a change has enough surface area that one large edit would hide risk.

Process:

1. Define the smallest behavior slice that delivers value.
2. Read existing code, tests, docs, and configuration for that slice.
3. Make the smallest relevant edit.
4. Run the closest cheap validation before expanding.
5. Repeat only for directly required follow-up slices.
6. Stop when the requested behavior is complete; avoid unrelated cleanup.

Daily stock repo checks:

- Preserve data provider priority, fallback, normalization, timeout, and cache behavior.
- Preserve API/Web/Desktop compatibility when changing schemas or report payloads.
- Update docs and `docs/CHANGELOG.md` only for user-visible, CLI/API, deployment, notification, or report structure changes.

Verification:

- Use the validation matrix in `AGENTS.md`.
- State unverified paths and why they were not covered.
