---
name: code-review-and-quality
description: Review changes across correctness, maintainability, tests, security, performance, docs, and release risk.
---

# Code Review And Quality

Use this skill before handoff or when reviewing a PR/diff.

Review order:

1. Necessity and scope: does the change solve a clear problem without unrelated work?
2. Contract correctness: runtime, API/Web/Desktop, CLI, reports, notifications, workflows, and docs.
3. Tests and validation evidence.
4. Security and privacy risk.
5. Performance and reliability risk.
6. Rollback clarity.

Findings come first, ordered by severity and grounded in file/line references where possible.

Merge blockers include:

- Correctness or security issues.
- Blocking CI failure.
- PR description mismatch.
- Missing rollback plan for risky changes.
- Patch stacking without semantic convergence.
- Invalid or irrelevant validation evidence.

If no issues are found, state that clearly and mention any residual test gaps.
