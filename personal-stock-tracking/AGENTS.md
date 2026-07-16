# AGENTS.md

Guidance for AI agents working in this personal stock-tracking repository.

## Repository overview

This repository supports private investment tracking, portfolio analysis, and related automation. Treat supplied portfolio, account, and transaction data as confidential.

## Command environment

- Run shell commands with Windows Command Prompt (`cmd.exe`), not PowerShell.
- Use CMD-compatible syntax in scripts and documented commands.

## Skill-driven execution

This workspace uses a skill-driven workflow. Skills are stored in `.agents/skills/<skill-name>/SKILL.md`; agent personas are stored in `.agents/agents/<role>.md`.

### Core rules

- Before acting, determine whether a local skill applies to the request.
- If a skill applies, read its entire `SKILL.md` and follow it exactly.
- Do not partially apply a skill or bypass its required steps because a task appears small.
- A skill's instructions take precedence over ordinary repository guidance for that workflow.
- Use an agent persona when its perspective or output format fits the request; personas may use skills, but do not orchestrate other personas.

### Intent-to-skill mapping

- New feature or functionality: `spec-driven-development`, then `incremental-implementation` and `test-driven-development`.
- Planning or task breakdown: `planning-and-task-breakdown`.
- Bug, failure, or unexpected behavior: `debugging-and-error-recovery`.
- Code review: `code-review-and-quality`.
- Refactoring or simplification: `code-simplification`.
- API or interface design: `api-and-interface-design`.
- UI work: `frontend-ui-engineering`.
- Portfolio analysis or report creation: `portfolio-review`.

### Default lifecycle

When relevant, follow the lifecycle below. Apply only the available skills that match the request.

1. Define: `spec-driven-development`
2. Plan: `planning-and-task-breakdown`
3. Build: `incremental-implementation` and `test-driven-development`
4. Verify: `debugging-and-error-recovery`
5. Review: `code-review-and-quality`

## Data and safety

- Never commit API keys, broker credentials, or account exports.
- Keep private source data in `data/private/` and generated artifacts in `reports/`.
- Clearly identify sources, as-of dates, assumptions, and missing data in analysis.
- Provide research support and educational context only; do not execute trades or broker actions.

## Repository layout

- `.agents/skills/`: reusable workflows.
- `.agents/agents/`: reusable roles and output formats.
- `data/`: local input data.
- `scripts/`: repeatable automation.
- `reports/`: generated outputs.

## Creating or changing skills

- Search the existing skill catalog before adding a new skill.
- Prefer extending an existing skill over creating an overlapping one.
- Store each skill at `.agents/skills/<kebab-case-name>/SKILL.md`.
- Include a clear purpose, when-to-use guidance, process, safeguards, and verification criteria.
