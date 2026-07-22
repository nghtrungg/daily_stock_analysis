---
applyTo: "main.py,src/**/*.py,data_provider/**/*.py,bot/**/*.py,tests/**/*.py"
---

# Core Python Instructions

- Preserve pipeline boundaries and reuse existing services, repositories, schemas, and provider fallback logic.
- Configuration, CLI, scheduler, bot, notification, report, or persistence changes must sync `.env.example` and relevant docs.
- Provider changes must preserve priority, normalization, timeout/retry, cache, and graceful degradation.
- Keep SQLite compatibility and Vietnam-local output semantics.
- Prefer `./scripts/ci_gate.sh`; otherwise run `python -m py_compile` on changed files and the closest deterministic tests.

