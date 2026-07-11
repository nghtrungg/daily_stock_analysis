# AGENTS.md

This file defines the default development workflow for this repository. Its goal is to reduce repeated communication and rework, and to keep changes aligned with the current project structure.

If this file conflicts with executable scripts, workflows, or the current code, trust the executable behavior first and update the documentation as part of the related change so the rules do not drift.

## 1. Hard Rules

- Respect existing directory boundaries:
  - Backend logic belongs in `src/`, `data_provider/`, `api/`, or `bot/`.
  - Web frontend changes belong in `apps/dsa-web/`.
  - Desktop changes belong in `apps/dsa-desktop/`.
  - Deployment and pipeline changes belong in `scripts/`, `.github/workflows/`, or `docker/`.
- Do not run `git commit`, `git tag`, or `git push` without explicit confirmation.
- Commit messages must be in English and must not add `Co-Authored-By`.
- Do not hardcode secrets, accounts, paths, model names, ports, or environment-specific branching logic.
- Reuse existing modules, configuration entry points, scripts, and tests before adding parallel implementations.
- Prefer stability over opportunistic cleanup. Avoid unrelated refactors, abstractions, or infrastructure migrations.
- When adding configuration, update `.env.example` and the relevant documentation.
- User-visible behavior, CLI/API behavior, deployment behavior, notification behavior, or report structure changes must update the relevant docs and `docs/CHANGELOG.md`.
- Report format, report rendering, or Web UI changes require affected report/page screenshots in the PR description. Prefer before/after screenshots when behavior changed; if screenshots are impossible, explain why and provide alternative visual evidence.
- Temporary screenshots and one-off validation images must not be committed. Put them in the PR description, PR comments, GitHub attachments, Actions artifacts, or external evidence links. Long-lived product documentation images are allowed only when their filenames and meaning are independent of a specific issue or PR number.
- The `[Unreleased]` section in `docs/CHANGELOG.md` uses a flat format: one line per entry, formatted as `- [type] description`. Allowed types are `feature`, `improvement`, `fix`, `docs`, `test`, and `chore`. Do not add `### category headings` inside `[Unreleased]`; maintainers will reorganize released sections.
- `README.md` is only for project positioning, high-level capabilities, quick start, main entry points, and sponsorship/cooperation information. Avoid updating it unless the change is homepage-level.
- Put detailed module behavior, page interactions, topic configuration, troubleshooting, field contracts, implementation semantics, and edge cases in the appropriate `docs/*.md` file instead of `README.md`.
- When changing one side of a bilingual document pair, evaluate whether the other side must be synchronized. If not synchronized, explain why in the handoff.
- Comments, docstrings, and logs should be clear and accurate. They do not have to be English, but they should match the surrounding file context.

## 1.1 PR Title Guidance

- Prefer `<type>: <change summary>`, for example `fix: preserve market review history`.
- Use `fix`, `feat`, `refactor`, `docs`, `chore`, `test`, or `ci` where possible.
- Do not add `[codex]`, `codex`, `autocode`, `copilot`, or another tool/agent source prefix.
- This is readability guidance and should not be used as a standalone review blocker.

## 1.2 Contribution Quality Baseline

- This repository does not accept PRs that substitute large diffs, patch stacking, or review-comment whack-a-mole for real design convergence.
- Quality is judged by whether the PR solves a clear problem, minimizes impact, preserves existing contracts, and covers real risk paths. It is not judged by line count, file count, feature marketing, or looking complete.
- Do not treat this repository as a low-cost experiment, resume showcase, or contribution-farming target. Every PR must show that the author understands the current system contract and has done basic self-review, integration, and validation.
- AI-assisted development is acceptable; unreviewed, unverified, unconverged AI output is not.
- After review feedback, do not only patch the exact line that was mentioned. Re-check all runtime, API/Web, CLI, diagnostics, workflow, docs, tests, and user-visible paths that share the same business semantics.
- If repeated review rounds show the same contract drift, duplicate fallback, mocked-away risk layer, or PR-body mismatch, maintainers may ask to close and redo the PR instead of continuing point-by-point review.

## 2. AI Collaboration Asset Governance

- `AGENTS.md` is the single source of truth for repository AI collaboration rules.
- `.github/copilot-instructions.md` and `.github/instructions/*.instructions.md` mirror or supplement these rules for GitHub Copilot / Coding Agent. If they conflict, follow `AGENTS.md`.
- Repository collaboration skills live in `.claude/skills/`; analysis artifacts live in `.claude/reviews/`. Skills may be committed, while reviews are local by default.
- Root `SKILL.md` and `docs/openclaw-skill-integration.md` are product/external integration docs, not the source of repository collaboration rules.
- `.agents/` contains selected agent-neutral skills and personas adapted from the imported `agent-skills` catalog. `AGENTS.md` remains the rule source; do not hand-maintain conflicting instructions across `.claude/skills/`, `.agents/`, `.github`, and this file.
- Do not commit broad imported skill catalogs such as `agent-skills/` into this repository. Extract only repo-relevant guidance into `AGENTS.md` or the small repository skills, then remove the import directory.
- When changing AI governance assets, run:

```bash
python scripts/check_ai_assets.py
```

## 2.1 Skill And Persona Selection

Use skills as focused workflows, not as a mandatory chain. Pick the smallest set that directly applies to the current request; do not run every available skill just because the imported catalog contains one.

Selected agent-neutral assets live in `.agents/`:

- Skills: `.agents/skills/<skill-name>/SKILL.md`
- Personas: `.agents/personas/<persona-name>.md`

For this daily stock analysis repository, prefer these mappings:

| Task intent | Primary skill/workflow | Optional support |
| --- | --- | --- |
| Analyze a GitHub issue | `.claude/skills/analyze-issue/SKILL.md` or `.agents/skills/analyze-issue/SKILL.md` | `.agents/personas/test-engineer.md` for coverage gaps |
| Review a PR | `.claude/skills/analyze-pr/SKILL.md` or `.agents/skills/analyze-pr/SKILL.md` | `.agents/personas/code-reviewer.md`, plus `.agents/personas/security-auditor.md` for auth, secrets, network, LLM, or provider changes |
| Fix a validated issue | `.claude/skills/fix-issue/SKILL.md` or `.agents/skills/fix-issue/SKILL.md` | `.agents/skills/test-driven-development/SKILL.md`, `.agents/skills/debugging-and-error-recovery/SKILL.md`, and `.agents/skills/documentation-and-adrs/SKILL.md` as needed |
| Backend/data-provider/report change | `.agents/skills/incremental-implementation/SKILL.md`, `.agents/skills/debugging-and-error-recovery/SKILL.md`, or `.agents/skills/test-driven-development/SKILL.md` | `.agents/skills/security-and-hardening/SKILL.md` when touching untrusted input, secrets, tokens, webhooks, or LLM/tool output |
| API/schema/auth change | `.agents/skills/api-and-interface-design/SKILL.md` | `.agents/personas/code-reviewer.md`, `.agents/personas/security-auditor.md`, client build validation |
| Web UI/report rendering change | `.agents/skills/frontend-ui-engineering/SKILL.md` | `.agents/skills/browser-testing-with-devtools/SKILL.md` and `.agents/personas/web-performance-auditor.md` only when performance is part of the task |
| Workflow, Docker, release, or CI change | `.agents/skills/ci-cd-and-automation/SKILL.md` | `.agents/skills/shipping-and-launch/SKILL.md` |
| Documentation or governance change | `.agents/skills/documentation-and-adrs/SKILL.md` | `.agents/personas/code-reviewer.md` for rule consistency |
| External API/library behavior change | `.agents/skills/source-driven-development/SKILL.md` | Official docs or primary source verification |

Persona guidance:

- `code-reviewer`: use for merge readiness, contract drift, maintainability, and PR-quality feedback.
- `security-auditor`: use for auth, authorization, secrets, tokens, CORS, webhook, dependency, prompt/LLM, SSRF, command execution, and untrusted-input paths.
- `test-engineer`: use for regression strategy, coverage gaps, issue reproduction, and choosing the right test level.
- `web-performance-auditor`: use only for `apps/dsa-web/` performance or live web audit work; do not include it in backend-only review fan-out.

Personas do not invoke other personas. If multiple perspectives are useful, run them as independent review passes and merge the findings in the main handoff.

## 3. Repository Overview

- Purpose: an AI stock analysis system covering A-shares, Hong Kong stocks, US stocks, and related markets.
- Main flow: fetch data -> technical analysis/news retrieval -> LLM analysis -> report generation -> notification delivery.
- Key entry points:
  - `main.py`: analysis task entry point.
  - `server.py`: FastAPI service entry point.
  - `apps/dsa-web/`: Web frontend.
  - `apps/dsa-desktop/`: Electron desktop app.
  - `.github/workflows/`: CI, release, and daily jobs.
- Core responsibilities:
  - `src/core/`: main flow orchestration.
  - `src/services/`: business services.
  - `src/repositories/`: data access.
  - `src/reports/`: report generation.
  - `src/schemas/`: schemas and data structures.
  - `data_provider/`: provider adapters and fallback.
  - `api/`: FastAPI API.
  - `bot/`: bot integrations.
  - `scripts/`: local scripts.
  - `.github/scripts/`: GitHub automation scripts.
  - `tests/`: pytest tests.
  - `docs/`: documentation.

## 4. Common Commands

### Run The App

> This workstation has PowerShell locked. Run all repository commands through
> Command Prompt (`cmd.exe`). Use the repository virtual environment explicitly,
> with UTF-8 enabled, for example `cmd.exe /d /c "chcp 65001>nul & set
> \"PYTHONUTF8=1\"& .venv\Scripts\python.exe main.py --dry-run"`.
> Do not rely on PowerShell-specific syntax in commands or validation notes.

```bash
python main.py
python main.py --debug
python main.py --dry-run
python main.py --stocks 600519,hk00700,AAPL
python main.py --market-review
python main.py --schedule
python main.py --serve
python main.py --serve-only
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

### Backend Validation

```bash
pip install -r requirements.txt
pip install flake8 pytest
./scripts/ci_gate.sh
python -m pytest -m "not network"
python -m py_compile <changed_python_files>
```

### Web / Desktop

```bash
cd apps/dsa-web
npm ci
npm run lint
npm run build

cd ../dsa-desktop
npm install
npm run build
```

### PR / CI Evidence

```bash
gh pr view <pr_number>
gh pr checks <pr_number>
gh run view <run_id> --log-failed
```

## 5. Default Workflow

1. Classify the task: `fix / feat / refactor / docs / chore / test / review`.
2. Read existing implementation, configuration, tests, scripts, workflows, and docs before editing.
3. Identify the change boundary: backend, API, Web, Desktop, Workflow, Docs, or AI collaboration assets.
4. Check whether the change touches high-risk areas: configuration semantics, API/schema, provider fallback, report structure, auth, scheduling, release flow, or desktop startup.
5. Make the smallest directly relevant change. Do not include unrelated refactors.
6. If docs, scripts, or workflows disagree, trust executable code/workflows first, then decide whether to fix docs as part of the change.
7. Validate according to the matrix below.
8. Final handoff should explain what changed, why, validation, unverified items, risks, and rollback.

## 6. Validation Matrix

### CI Coverage Principles

| Check | Source | Description | Blocking |
| --- | --- | --- | --- |
| `ai-governance` | `.github/workflows/ci.yml` | Validates `AGENTS.md`, `CLAUDE.md`, `.github` instructions, and `.claude/skills` relationships | Yes |
| `backend-gate` | `.github/workflows/ci.yml` | Runs `./scripts/ci_gate.sh` | Yes |
| `docker-build` | `.github/workflows/ci.yml` | Docker build and key module import smoke | Yes |
| `web-gate` | `.github/workflows/ci.yml` | Runs `npm run lint` and `npm run build` when frontend changes trigger it | Yes when triggered |
| `network-smoke` | `.github/workflows/network-smoke.yml` | `pytest -m network` plus `scripts/test.sh quick` | No, observational |
| `pr-review` | `.github/workflows/pr-review.yml` | Static PR checks, AI review, and automatic labels | No, supporting |

If the PR already has relevant CI results, cite them. If CI does not cover the change surface, or local and CI environments differ materially, explain local validation and gaps.

### By Change Surface

- Python backend changes: prefer `./scripts/ci_gate.sh`; minimum is `python -m py_compile <changed_python_files>`. If API, orchestration, reports, notifications, provider fallback, auth, or scheduling are affected, state whether those paths were covered.
- Web frontend changes: run `cd apps/dsa-web && npm ci && npm run lint && npm run build`. If API integration, routing, state, Markdown/chart rendering, or auth state is affected, describe coupling and untested risk.
- Desktop changes: build Web first, then desktop. If platform limits prevent full validation, state whether Web artifacts, Electron build, and release workflow impact were checked.
- API/schema/auth changes: cover backend validation and affected client builds. For login, cookies, sessions, polling state, fields, or enum changes, state compatibility impact.
- Docs and governance changes: code tests are not required. Confirm commands, config names, filenames, and workflow names against the repo. For AI governance changes, run `python scripts/check_ai_assets.py`.
- Workflow/script/Docker changes: run the closest local validation and state affected pipelines, release paths, or deployment paths. If Docker or GitHub Actions validation was not run, explain why and the risk.
- Network or third-party dependency changes: run offline/deterministic checks first and confirm timeout, retry, fallback, error text, and degradation paths. If online checks were not run, explain why.

## 7. Stability Guardrails

- Configuration and runtime entry points: changing `.env` semantics, defaults, CLI args, service startup, or scheduling requires impact assessment for local runs, Docker, GitHub Actions, API, Web, and Desktop. Prefer optional enhancements that work without configuration.
- Data sources and fallback: changes under `data_provider/` must preserve provider priority, degradation, field normalization, cache, and timeout behavior. A single provider failure should not break the whole analysis flow unless fail-fast is explicitly required.
- API/Web/Desktop compatibility: check backend and clients when changing API, schemas, auth, or report payloads. Prefer additive fields, retained old fields, or compatibility layers.
- Reports, prompts, and notifications: check upstream inputs and downstream consumers when changing report structure, prompts, extractors, notification templates, or bot flows. A single notification channel failure should not break the main analysis flow unless fail-fast is required. If changing `EXTRACT_PROMPT` in `src/services/image_stock_extractor.py`, include the full latest prompt in the PR description.
- Workflows, release, and packaging: changing automatic tags, releases, Docker publishing, daily analysis, or desktop packaging requires trigger, artifact path, permission, and rollback assessment. Automatic tags remain opt-in: only commit titles containing `#patch`, `#minor`, or `#major` trigger version updates unless a requirement explicitly changes that policy.

## 8. Issue / PR / Skill Workflow

- Existing repository skills may be reused. `.claude/skills/` is the validated committed surface; `.agents/skills/` may mirror the same skills for agent-neutral harnesses:
  - `.claude/skills/analyze-issue/SKILL.md`
  - `.claude/skills/analyze-pr/SKILL.md`
  - `.claude/skills/fix-issue/SKILL.md`
- For issue analysis, PR review, or issue fixes, prefer the corresponding skill and save artifacts under `.claude/reviews/`.
- Skill commands, templates, validation order, and handoff structure must stay aligned with `AGENTS.md`.
- Before creating/updating PRs, reviewing PRs, or analyzing issues, first check worktree status and run `git fetch --all --prune`. If the worktree is clean and the current branch can fast-forward, run `git pull --ff-only`. If local changes, conflicts, risky untracked files, or non-fast-forward history exist, do not force branch switches, stash, reset, or overwrite local state. Analyze fetched remote refs instead and record the baseline gap.
- Skills should read CI/workflow evidence first, then decide whether local validation is needed.
- Except for the safe fast-forward sync above, skills must not default to `git pull`, `git push`, `git tag`, or `gh pr create`; those require user confirmation.
- PR review order: necessity, relevance, title suggestion, PR template completeness, validation evidence, implementation correctness, and merge decision.
- For `fix` PRs, explain original problem, root cause, fix, and regression risk.
- Merge blockers: correctness/security issues, blocking CI failure, material mismatch between PR description and diff, missing rollback plan, repeated unconverged contract drift, patch stacking, or invalid validation evidence.

## 8.1 Handling Review Feedback And Avoiding Patch Stacking

When handling review feedback, do not only patch the exact mentioned line and claim everything is fixed. First understand the business contract behind the feedback, then inspect all runtime, API/Web, CLI, diagnostics, workflow, docs, tests, and user-visible paths that share the same semantics.

Required order:

1. List each original reviewer concern.
2. Explain the root cause, not just the changed lines.
3. Identify all affected paths for the same semantics.
4. Fix the complete contract, not only the failing test or comment line.
5. Add regression coverage for the reviewer counterexample, final entry validation, or explain why validation is not possible.
6. Update the PR body so scope, validation, compatibility, risks, and rollback match the current head.

If this cannot be completed, do not keep stacking patches or mark the PR ready. Explain whether the PR should be split, closed and redone, or narrowed with maintainer confirmation.

Low-quality patterns include broad fallbacks, silent degradation, `return False/None/[]` that hides unclear contracts, tests that mock away the real risk layer, claiming CI closes a reviewer counterexample without coverage, PR-body drift, scattered review patches, and inconsistent runtime/Web/API/docs/workflow/test semantics.

CI passing only means automated checks passed; it does not replace semantic convergence.

## 9. Handoff And Release

Default handoff structure:

- What changed
- Why
- Validation
- Unverified items
- Risks
- Rollback

For docs-only work, write `Docs only, tests not run`, but still state whether commands and filenames were checked.

Automatic tags are disabled by default unless the commit title contains `#patch`, `#minor`, or `#major`. Manual tags must be annotated. User-visible changes should preferably be merged through PRs with labels and validation notes.
