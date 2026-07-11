# Run Diagnostics P0

P0 establishes the diagnostics contract without changing runtime behavior. It records current execution paths for local runs, Docker, GitHub Actions, API, Web, Desktop, notifications, and provider fallback.

Diagnostics must be additive, stable, and redacted. They must not expose tokens, webhook URLs, cookies, passwords, bot secrets, or private environment values. P0 does not add a background service, database migration, provider priority change, or failover behavior change.
