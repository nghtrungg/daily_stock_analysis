# Run Diagnostics P2

P2 extends diagnostics to provider and notification degradation. It should show configured provider order, recent degradation reasons, fallback paths, and stable structured error codes for Web/API consumers.

Diagnostics must never return API keys, webhook URLs, authorization headers, cookies, email passwords, bot secrets, or private environment values. Use deterministic tests for redaction and fallback summaries.
