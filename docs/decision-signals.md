# Decision Signals

Decision signals are structured records extracted from completed analysis reports and stored in SQLite for later measurement. They are part of the core analysis-history contract, not an HTTP API.

Core implementation:

- `src/services/decision_signal_extractor.py`: extract and persist signals from analysis results.
- `src/services/decision_signal_service.py`: query and lifecycle operations.
- `src/services/decision_signal_outcome_service.py`: evaluate later outcomes.
- `src/services/decision_signal_summary.py`: report-safe summaries.
- `src/repositories/decision_signal_repo.py` and `src/repositories/decision_signal_outcome_repo.py`: SQLite persistence.
- `src/schemas/decision_action.py` and `src/schemas/decision_scale.py`: normalized action and scale contracts.

Signals retain source report identity, stock code, market phase, action, reason, price levels, profile, timestamps, and status. Outcome metrics must report their numerator, denominator, sample count, availability, and version so empty or incomplete data is not presented as performance.

For the Vietnam profile, prices use actual VND and symbols use explicit `.VN` suffixes. A future Supabase migration must preserve source-report relationships, deduplication keys, feedback, outcomes, timestamps, and nullable legacy fields.

