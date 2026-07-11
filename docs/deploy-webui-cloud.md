# Deploy WebUI To Cloud

Cloud deployment requires Python dependencies from `requirements.txt`, environment variables for at least one LLM provider, optional notification and data-provider secrets, and persistent storage for `data/` if history, alerts, portfolios, or caches must survive restarts.

Typical Web service command:

```bash
python main.py --serve-only
```

Combined Web and scheduler mode:

```bash
python main.py --serve --schedule
```

Do not expose secrets in logs or screenshots. Verify service startup, Web pages, API routes, provider configuration, and notification delivery or clean degradation.
