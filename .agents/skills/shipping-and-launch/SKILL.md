---
name: shipping-and-launch
description: Prepare risky or production-facing changes for release with validation, monitoring, compatibility, and rollback.
---

# Shipping And Launch

Use this skill for release, deployment, packaging, daily automation, notification, report format, or broad user-visible changes.

Pre-launch check:

1. Define what changes for users or operators.
2. Confirm validation for each affected surface: backend, API, Web, Desktop, workflow, docs.
3. Confirm compatibility and migration behavior.
4. Confirm observability or diagnostic evidence.
5. Confirm rollback path, usually revert plus config restoration.
6. Note any staged rollout or manual verification required.

For this repo, pay special attention to:

- Daily scheduled analysis.
- Notification delivery.
- Data provider degradation.
- Desktop packaging.
- Docker and cloud deployment paths.
- Report format and prompt changes.

Do not tag, push, release, or create PRs without explicit confirmation.
