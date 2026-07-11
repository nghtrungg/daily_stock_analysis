---
name: ci-cd-and-automation
description: Modify or review GitHub Actions, scripts, Docker, release automation, and scheduled jobs.
---

# CI/CD And Automation

Use this skill for `.github/**`, `scripts/**`, `docker/**`, release, daily analysis, and packaging changes.

Process:

1. Identify the affected pipeline, trigger, permissions, artifacts, secrets, and rollback path.
2. Prefer executable scripts over duplicated YAML logic.
3. Keep automatic tags opt-in through `#patch`, `#minor`, or `#major` unless the requirement explicitly changes that policy.
4. Avoid widening permissions or exposing secrets.
5. Run the closest local validation.
6. Explain any GitHub Actions or Docker validation that could not be run locally.

Check:

- Trigger conditions.
- Artifact paths.
- Cache behavior.
- Environment variables and secret names.
- Release and rollback behavior.
- Interaction with Web/Desktop builds.
