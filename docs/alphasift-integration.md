# AlphaSift Stock Screening Integration

AlphaSift is an independent stock-screening engine integrated through `alphasift.dsa_adapter`. DSA does not copy AlphaSift strategy logic and keeps the feature disabled by default.

Default configuration is `ALPHASIFT_ENABLED=false`. Enable through Web settings, the stock-screening page, or `.env`. Runtime dependency is installed from `requirements.txt` at a trusted AlphaSift commit. `ALPHASIFT_INSTALL_SPEC` is only a repair-install source for explicit `/api/v1/alphasift/install` calls.

AlphaSift owns strategy catalogs, parameters, market snapshots, first-pass screening, factor scoring, and LLM reranking. DSA owns the feature switch, API shell, provider context, display behavior, and user-facing errors.

Fast rollback: set `ALPHASIFT_ENABLED=false` and restart. Adapter rollback requires reverting `requirements.txt`, `src/config.py`, and `.env.example`, reinstalling dependencies, and rebuilding backend/Desktop artifacts.

If `alphasift.dsa_adapter` is missing, `status` returns `available=false`; `strategies` and `screen` return `424` with a user-readable message. Business requests must not auto-run `pip install`.

Main API routes: `/api/v1/alphasift/status`, `/strategies`, `/screen`, `/screen/tasks/{task_id}`, `/hotspots`, and `/hotspots/{topic}`. Errors should be stable: disabled `403`, untrusted install source `403`, missing adapter `424`, rejected market/strategy `400/422`, and screening failure `424`.

Typical validation: `python -m pytest tests/test_alphasift_api.py -q`, Python compile checks for AlphaSift modules, Web tests for AlphaSift pages, `npm run lint`, and `npm run build`.
