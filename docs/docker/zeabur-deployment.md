# Zeabur Deployment

Deploy this project on Zeabur or similar container platforms with a Docker image, model-provider environment variables, stock-list configuration, optional notification secrets, and a persistent `data/` volume when history, alerts, portfolios, or caches must survive redeploys.

For Web service deployments, ensure the platform command matches the intended mode:

```bash
python main.py --serve-only
```

or:

```bash
python main.py --serve --schedule
```

Check container logs, Web health, API routes, provider configuration, and notification delivery. Do not paste secrets into deployment evidence.
