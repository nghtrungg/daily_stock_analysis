# Analyze PR

Review a GitHub pull request for necessity, relevance, validation evidence, implementation correctness, and merge readiness. Follow root `AGENTS.md` first.

## Usage

```text
/analyze-pr <pr_number>
```

## Workflow

1. Run `git status --short`, `git fetch --all --prune`, and only run `git pull --ff-only` when clean and fast-forwardable.
2. Read PR metadata, diff, description, CI checks, and relevant workflow logs.
3. Review in this order: necessity, relevance, title suggestion, template completeness, validation evidence, implementation correctness, merge decision.
4. Treat correctness/security issues, blocking CI, PR-body mismatch, missing rollback plan, contract drift, patch stacking, or invalid validation evidence as blockers.
5. Save the review to `.Codex/reviews/prs/pr-<number>.md`.

Do not post comments, approve, request changes, push, or modify the PR without user confirmation.
