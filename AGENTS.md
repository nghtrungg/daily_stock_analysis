# AGENTS.md — Vietnam Core Build

This file is the repository workflow source of truth.

## Hard rules

- Keep runtime code within `main.py`, `src/`, `data_provider/`, and `bot/`.
- Keep scripts and GitHub automation within `scripts/` and `.github/workflows/`.
- This is a CLI-only repository. Do not reintroduce a Web frontend, HTTP API, Desktop application, Docker packaging, or cloud-deployment layer without an explicit requirement.
- Do not run `git commit`, `git tag`, or `git push` without explicit confirmation.
- Commit messages must be English and must not add `Co-Authored-By`.
- Do not hardcode secrets, accounts, paths, ports, model names, or environment-specific branches.
- Reuse existing configuration, services, repositories, provider adapters, scripts, and tests before adding parallel implementations.
- Prefer stability over unrelated cleanup.
- When adding or changing configuration, update `.env.example` and the relevant documentation.
- User-visible CLI, scheduler, notification, bot, report, or persistence changes must update the relevant docs and `docs/CHANGELOG.md`.
- The `[Unreleased]` changelog uses flat entries: `- [type] description`. Allowed types are `feature`, `improvement`, `fix`, `docs`, `test`, and `chore`.
- Keep `README.md` limited to positioning, capabilities, quick start, and main entry points. Put detailed behavior in `docs/`.

## Vietnam-local boundaries

- New analysis targets explicit Vietnam symbols ending in `.VN`.
- User-visible financial values use actual VND and Vietnamese formatting.
- Reports remain Vietnamese and schedules use `Asia/Ho_Chi_Minh`.
- Preserve `ENABLED_MARKETS=vn`, `DATABASE_PATH=./data/stock_analysis_vn.db`, the bundled index at `src/data/stocks.index.json`, and disabled upstream index refresh.
- Do not incidentally enable inherited multi-market routing or the legacy non-Vietnam market-review flow.
- The weekday scheduler does not model official exchange holidays.
- SQLite remains the source of truth. A future Supabase move must be a separate migration with backups, reconciliation, compatibility tests, and rollback; do not delete or rewrite the SQLite database in place.

## Repository map

- `main.py`: CLI analysis, backtest, diagnostics, and scheduler entry point.
- `src/core/`: analysis orchestration and guardrails.
- `src/services/`: business services.
- `src/repositories/`: database access.
- `src/schemas/`: report and analysis schemas.
- `src/storage.py`: SQLite models and database manager.
- `data_provider/`: provider adapters and fallback.
- `bot/`: bot commands and stream clients.
- `templates/`: report templates.
- `tests/`: deterministic and network-marked tests.
- `docs/`: durable behavior and operating documentation.

## Default workflow

1. Classify the task and read the implementation, tests, config, scripts, and docs in scope.
2. Identify high-risk contracts: provider fallback, report schema/language, scheduling, notifications, bot behavior, and persistence.
3. Make the smallest directly relevant change.
4. Preserve provider priority, normalization, timeout, cache, and graceful degradation.
5. Preserve SQLite compatibility unless a separately approved migration changes it.
6. Validate the closest deterministic path, then expand only when risk requires it.
7. Report what changed, why, validation, unverified items, risks, and rollback.

## Commands

Run repository commands through Command Prompt with the virtual environment and UTF-8:

```bat
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe main.py --dry-run --stocks VNM.VN --no-notify --no-market-review"
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe main.py --schedule --no-market-review"
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe -m pytest -m \"not network\""
```

Backend validation prefers `./scripts/ci_gate.sh`; the minimum for Python changes is `python -m py_compile <changed_files>` plus the closest deterministic tests.

For AI governance changes, run:

```bat
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe scripts\check_ai_assets.py"
```

## Stability guardrails

- A single provider or optional notification channel failure should not break the whole analysis unless fail-fast is explicitly required.
- Report, prompt, and notification changes must preserve Vietnamese output, schema/language validation, actual-VND normalization, and isolated history.
- Changes to `.env`, CLI flags, startup, or scheduling must assess local runs and GitHub Actions.
- Workflow changes must verify triggers, permissions, secrets, cache behavior, artifacts, and rollback.
- Automatic tags remain opt-in through commit titles containing `#patch`, `#minor`, or `#major`.
- Tests must cover real risk paths; do not mock away the layer that owns the business contract.

## AI collaboration assets

- `AGENTS.md` is canonical.
- `.github/copilot-instructions.md` and `.github/instructions/*.instructions.md` may summarize these rules but must not conflict.
- Repository collaboration skills live in `.claude/skills/` and selected agent-neutral skills live in `.agents/skills/`.
- Run `scripts/check_ai_assets.py` after governance changes.

## PR guidance

Prefer `<type>: <change summary>`, using `fix`, `feat`, `refactor`, `docs`, `chore`, `test`, or `ci`. Do not add tool or agent prefixes.

Before PR or issue work, inspect worktree status and fetch remote refs. Only fast-forward a clean branch; never force branch switches, stash, reset, or overwrite user changes.

Merge blockers include correctness or security issues, blocking CI failures, missing validation for real risk, PR-body drift, invalid persistence changes, and missing rollback for production-facing behavior.

