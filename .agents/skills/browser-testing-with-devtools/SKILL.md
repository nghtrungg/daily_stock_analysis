---
name: browser-testing-with-devtools
description: Verify browser-rendered UI, console errors, network behavior, and visual regressions.
---

# Browser Testing With DevTools

Use this skill for Web UI, report rendering, routing, auth state, or visual verification.

Process:

1. Start or identify the local dev server.
2. Open the relevant route in a real browser.
3. Check console errors and failed network requests.
4. Exercise the user flow, including loading and error states where feasible.
5. Capture screenshots or visual evidence for PR descriptions when required by `AGENTS.md`.
6. Keep temporary screenshots out of the repository.

Use browser evidence for:

- Markdown/report rendering.
- Chart/table layout.
- API integration behavior.
- Responsive layout.
- Client-side routing and state.

If browser tooling is unavailable, run build/lint and state the visual verification gap.
