---
name: test-driven-development
description: Add or update behavior tests before or alongside implementation. Use for bug fixes, logic changes, API/schema changes, and report or provider behavior.
---

# Test Driven Development

Use tests to prove the behavior that matters.

Process:

1. Identify the behavior contract and risk path.
2. Find the nearest existing test pattern.
3. For bugs, add a regression test that demonstrates the failure when feasible.
4. Implement the smallest fix.
5. Run the targeted test, then the broader validation required by `AGENTS.md`.

Test at the right level:

- Pure logic: unit test.
- Provider, repository, API, notification, or report integration: integration-style test with boundary mocks only.
- Web rendering or browser behavior: browser or build validation.
- Workflow/release behavior: script or workflow dry-run where feasible.

Avoid:

- Mocking away the layer where the bug lives.
- Snapshot updates without review.
- Tests that only assert implementation details.
