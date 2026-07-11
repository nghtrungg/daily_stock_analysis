---
name: api-and-interface-design
description: Design stable APIs, schemas, module boundaries, and frontend/backend contracts.
---

# API And Interface Design

Use this skill when changing public or semi-public contracts.

Process:

1. Identify consumers: Python callers, FastAPI routes, Web, Desktop, tests, workflows, docs, or external users.
2. Prefer additive compatible changes.
3. Keep existing fields, enum values, and response shapes unless a breaking change is explicit.
4. Validate inputs at the boundary and normalize internally.
5. Document field contracts and migration behavior in the appropriate `docs/*.md`.
6. Update `.env.example` when configuration semantics change.

Daily stock contract surfaces:

- FastAPI routes under `api/` and `server.py`.
- Schemas under `src/schemas/`.
- Report payloads under `src/reports/`.
- Web and desktop client expectations.
- Provider adapters under `data_provider/`.

Verification:

- Run backend validation and affected client builds for API/schema/auth changes.
- State compatibility impact in the handoff.
