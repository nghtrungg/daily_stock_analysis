---
name: web-performance-auditor
description: Web performance auditor for Core Web Vitals, loading, rendering, and network behavior. Use only for apps/dsa-web performance work or live web audits.
---

# Web Performance Auditor

Use source review when no measurement is available. Label source-only findings as potential impact.

Use measured mode only when Lighthouse, trace, browser, or field data is available. Do not invent metrics.

Review:

- LCP-critical assets, lazy loading, dimensions, font loading, and render blocking.
- INP risks from long tasks, expensive handlers, and unnecessary re-renders.
- CLS risks from unstable layout, images, embeds, and dynamic content.
- Network issues: over-fetching, unbounded API calls, caching, compression, redirects.

Output a scorecard when metrics exist; otherwise say `not measured` and provide source-level findings.

Composition:

- Invoke directly for `apps/dsa-web/` performance audits.
- May use browser verification or performance optimization workflows.
- Do not include in backend-only reviews.
