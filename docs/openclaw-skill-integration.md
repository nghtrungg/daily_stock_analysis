# OpenClaw Skill Integration

This product-facing document describes skill integration. It is not the source of repository collaboration rules; use `AGENTS.md` for that.

Skills should define when to use them, inputs, safe actions, and actions requiring confirmation. They must not commit, tag, push, close issues, post reviews, or mutate remote state without explicit user confirmation.

When skill files mirror repository governance, run `python scripts/check_ai_assets.py`.
