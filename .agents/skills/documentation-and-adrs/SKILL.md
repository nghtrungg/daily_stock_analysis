---
name: documentation-and-adrs
description: Update durable docs, governance files, and decision records when behavior, contracts, or workflows change.
---

# Documentation And ADRs

Use this skill for docs, governance, public behavior, or architectural decisions.

Process:

1. Identify the audience and the right document.
2. Keep `README.md` homepage-level.
3. Put detailed behavior, configuration, troubleshooting, and contracts in `docs/*.md`.
4. Update `docs/CHANGELOG.md` for user-visible behavior, CLI/API behavior, deployment, notification, or report structure changes.
5. Preserve the flat `[Unreleased]` changelog format: `- [type] description`.
6. For bilingual doc pairs, update both or explain why one side was not synchronized.
7. For AI governance changes, run `python scripts/check_ai_assets.py`.

Docs only handoff:

- Say `Docs only, tests not run`.
- Still state whether commands, file names, workflow names, and config keys were checked.
