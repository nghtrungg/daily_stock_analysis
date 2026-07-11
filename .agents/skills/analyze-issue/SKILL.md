# Analyze Issue

Analyze a GitHub issue to determine validity, priority, repository ownership, and recommended action. Follow root `AGENTS.md` first.

## Usage

```text
/analyze-issue <issue_number>
```

## Workflow

1. Run `git status --short`, `git fetch --all --prune`, and only run `git pull --ff-only` when the worktree is clean and the branch can fast-forward.
2. Fetch issue details and comments with `gh issue view`.
3. Check whether the version baseline is clear, the problem is real, the repository owns it, and it is worth handling now.
4. Read related code, config, tests, scripts, workflows, and docs.
5. Save the analysis to `.Codex/reviews/issues/issue-<number>.md`.

Ask before labels, comments, closing the issue, or starting a fix.
