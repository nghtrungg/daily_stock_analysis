---
name: source-driven-development
description: Ground implementation in official documentation or primary sources for external APIs, libraries, models, and workflow behavior.
---

# Source Driven Development

Use this skill when correctness depends on external or changing behavior.

Process:

1. Identify which facts must come from primary sources.
2. Prefer official docs, release notes, source code, API schemas, or repository workflows.
3. Record the relevant version or date when behavior may change.
4. Implement against the verified contract.
5. Avoid hardcoding environment-specific paths, ports, model names, or assumptions.
6. Add tests or guardrails around the contract where feasible.

Use for:

- OpenAI-compatible APIs and model behavior.
- Data provider APIs.
- FastAPI, frontend framework, Electron, Docker, GitHub Actions, and package manager behavior.
- Third-party dependency changes.

If primary sources cannot be reached, state the gap and choose the safest compatible implementation.
