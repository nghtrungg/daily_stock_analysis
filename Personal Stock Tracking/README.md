# Personal Stock Tracking

Local workspace for tracking investments and experimenting with Codex agents. The product uses Next.js with the App Router.

## Layout

- `.agents/agents/` — reusable agent role prompts.
- `.agents/skills/` — reusable task workflows; each skill lives in its own folder with a `SKILL.md`.
- `data/` — local input data (not committed if it contains private information).
- `scripts/` — repeatable automation scripts.
- `reports/` — generated research and portfolio reports.

Start by tailoring the prompts in `.agents/agents/` and `.agents/skills/` to your workflow.
