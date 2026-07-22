# Analysis Context Pack

The analysis context pack is the internal, schema-validated evidence bundle assembled before LLM generation. It keeps quote, technical, fundamental, news, portfolio, flow, event, and market-context data auditable without coupling the analyzer to a presentation client.

Core implementation:

- `src/schemas/analysis_context_pack.py`: schema and safe serialization.
- `src/services/analysis_context_builder.py`: pack construction and data-quality states.
- `src/analysis_context_pack_prompt.py`: bounded prompt projection.
- `src/analysis_context_pack_overview.py`: compact diagnostic summary.
- `src/core/pipeline.py`: orchestration and optional SQLite persistence.

The pack distinguishes available, unavailable, degraded, unsupported, and error states. Sensitive keys and diagnostic payloads must be sanitized before persistence. Large raw provider payloads should not be copied into prompts when a bounded summary is sufficient.

When `SAVE_CONTEXT_SNAPSHOT=true`, the sanitized snapshot is stored with analysis history in SQLite. Future database migrations must preserve pack version, timestamps, subject identity, block status, diagnostics, and JSON compatibility.

