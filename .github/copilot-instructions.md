# Repository Instructions

Canonical source: [`AGENTS.md`](../AGENTS.md). If this file conflicts with `AGENTS.md`, follow `AGENTS.md`.

- Runtime code belongs in `main.py`, `src/`, `data_provider/`, and `bot/`.
- This repository is CLI-only; do not reintroduce Web, HTTP API, Desktop, Docker, or cloud-deployment surfaces without an explicit requirement.
- Preserve Vietnam-only symbols, actual VND, Vietnamese reports, `Asia/Ho_Chi_Minh`, and SQLite compatibility.
- Reuse existing modules and preserve provider priority, normalization, timeout, cache, and fallback behavior.
- Sync `.env.example`, relevant docs, and `docs/CHANGELOG.md` when behavior or configuration changes.
- Do not commit, tag, or push without explicit confirmation.
- Validate changed Python plus the closest deterministic tests; prefer `scripts/ci_gate.sh` for the full core gate.
- AI governance assets and skills under `.claude/skills/` must remain aligned with `AGENTS.md`.

