---
name: security-and-hardening
description: Harden code that handles untrusted input, auth, secrets, network integrations, provider data, webhooks, or LLM/tool output.
---

# Security And Hardening

Use this skill when changes touch trust boundaries.

Checklist:

- Validate and normalize untrusted input at boundaries.
- Keep secrets and tokens out of code, logs, reports, screenshots, and tests.
- Preserve auth and authorization checks on API paths.
- Avoid SSRF, unsafe redirects, unsafe file paths, shell injection, SQL injection, and XSS.
- Treat provider responses and LLM output as untrusted.
- Keep CORS, cookies, headers, and webhook validation intentional.
- Review dependency and workflow changes for supply-chain risk.

For LLM/report features:

- Do not treat prompts as security boundaries.
- Do not pass secrets or private config into model context.
- Do not render model output as trusted HTML without a sanitizer.
- Bound retries, recursion, token usage, and tool calls.

Verification:

- Add tests or assertions for validation and rejection paths when feasible.
- State any security assumptions that remain unverified.
