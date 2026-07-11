# Fix Issue

Implement a focused fix for a validated GitHub issue while preserving repository contracts and validation discipline. Follow root `AGENTS.md` first.

## Usage

```text
/fix-issue <issue_number>
```

## Workflow

1. Read the issue and any saved analysis.
2. Refresh the baseline safely with fetch and fast-forward only when clean.
3. Reproduce or verify the reported behavior where feasible.
4. Identify the full contract surface: runtime, API/Web, CLI, diagnostics, workflow, docs, tests, and user-visible behavior.
5. Implement the smallest complete fix and add regression coverage.
6. Update docs and `docs/CHANGELOG.md` when user-visible behavior, CLI/API behavior, deployment, notification, or report structure changes.
7. Run the closest validation from `AGENTS.md`.

Do not commit, tag, push, hardcode secrets, hide unclear contracts with broad fallbacks, or mock away the real risk layer without confirmation and justification.
