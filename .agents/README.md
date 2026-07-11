# Agent Assets

This directory contains selected agent-skills-derived workflows and personas adapted for this repository.

`AGENTS.md` is still the source of truth. These files are reusable role/workflow prompts for harnesses that can discover `.agents/`.

Use only the skill or persona that matches the current task. Do not chain every skill by default.

## Selected Skills

- `api-and-interface-design`: API, schema, module boundary, and client contract changes.
- `browser-testing-with-devtools`: Web UI and report rendering verification in a real browser.
- `ci-cd-and-automation`: GitHub Actions, Docker, release, and automation work.
- `code-review-and-quality`: General review before merge or handoff.
- `debugging-and-error-recovery`: Reproduce, isolate, fix, and guard regressions.
- `documentation-and-adrs`: Documentation, governance, and durable decision records.
- `frontend-ui-engineering`: Web UI changes under `apps/dsa-web/`.
- `incremental-implementation`: Multi-file changes built in small verified slices.
- `security-and-hardening`: Auth, secrets, untrusted input, LLM/tool output, webhooks, and network risk.
- `shipping-and-launch`: Release readiness, rollback, and production impact checks.
- `source-driven-development`: Official-doc-backed implementation for external APIs and frameworks.
- `test-driven-development`: Regression coverage and behavior verification.

## Selected Personas

- `code-reviewer`: merge readiness and maintainability review.
- `security-auditor`: vulnerability and threat review.
- `test-engineer`: test strategy and coverage review.
- `web-performance-auditor`: web performance review for `apps/dsa-web/`.
