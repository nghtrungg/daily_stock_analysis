# Run Diagnostics P1

P1 adds the first runtime diagnostics implementation slice. It reports whether required providers, model routes, notification routes, and storage paths are configured, while keeping output user-readable and secret-free.

Do not validate provider credentials by default unless the action is explicitly a smoke test. Diagnostics should not block normal analysis when unavailable.

Validate changed Python files with targeted tests and `python -m py_compile`.
