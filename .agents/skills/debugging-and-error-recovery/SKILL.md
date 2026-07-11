---
name: debugging-and-error-recovery
description: Systematic root-cause debugging. Use when tests fail, builds break, reports are wrong, providers fail, or runtime behavior is unexpected.
---

# Debugging And Error Recovery

Process:

1. Reproduce or collect the exact failure evidence.
2. Localize the failing contract: runtime, API, Web, Desktop, provider, report, notification, workflow, or docs.
3. Compare expected behavior with executable code, not stale documentation.
4. Fix the root cause with the smallest complete change.
5. Add or update a regression guard when feasible.
6. Re-run the closest validation.

For this repo, always check shared semantics across:

- Runtime entry points: `main.py`, `server.py`, `webui.py`.
- Provider fallback and data normalization in `data_provider/`.
- API schemas and client expectations.
- Report rendering, prompts, extraction, and notifications.
- GitHub Actions, Docker, and desktop packaging when release behavior is involved.

Do not hide unclear contracts behind broad fallback, silent `None`, empty lists, or swallowed exceptions unless that is already the explicit local contract.
