---
name: frontend-ui-engineering
description: Build or modify production-quality Web UI under apps/dsa-web while preserving repo design and API contracts.
---

# Frontend UI Engineering

Use this skill for `apps/dsa-web/` changes.

Process:

1. Read existing components, state patterns, routing, styles, and API usage.
2. Preserve current design language unless the task explicitly asks for redesign.
3. Keep screens task-focused and usable, not decorative.
4. Handle loading, empty, error, stale, and permission states.
5. Ensure text fits on mobile and desktop.
6. Verify API coupling and schema compatibility.

For report rendering changes:

- Check Markdown/chart/table behavior.
- Provide visual evidence for affected pages or explain why screenshots are unavailable.
- Do not commit temporary screenshots.

Validation:

- Run `cd apps/dsa-web && npm ci && npm run lint && npm run build` when feasible.
- Use browser verification for rendering, console, and network issues.
