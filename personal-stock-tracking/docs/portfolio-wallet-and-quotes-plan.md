# Implementation plan: Vietnamese wallet, trades, and tracked quotes

## Status and gate

Detailed plan prepared on 2026-07-16. No application behavior or hosted Supabase state is changed by this plan. Begin Task 1 only after the user approves `docs/portfolio-wallet-and-quotes-spec.md` and this plan.

## Change boundary

```text
Vietnamese Web UI
       |
Portfolio provider/store
       |
Supabase owner ledger + atomic wallet RPCs
       |
Analysis run quote fields
       |
Signed Edge callback
       |
GitHub Actions quote extraction + retry
```

The work spans `personal-stock-tracking/` plus the repository's existing `.github/workflows/00-daily-analysis.yml` and `.github/scripts/callback_analysis_run.py`. It does not add broker integration, multi-currency support, or a separate market-data provider.

## Phase 1 — Vietnamese foundation

### Task 1: Localize the shell, authentication, metadata, and settings

- Files: `src/components/app-shell.tsx`, `src/app/layout.tsx`, `src/app/manifest.ts`, `src/app/login/page.tsx`, `src/features/auth/email-password-form.tsx`.
- Change: translate navigation, brand/supporting copy, authentication controls/messages, document metadata, PWA metadata, ARIA labels, and set `lang="vi"`.
- Acceptance: sign-in, registration, sidebar/mobile navigation, footer, metadata, and normal auth failures contain no user-visible English.
- Verification: update focused tests in the next task; run `npm run lint` and `npx tsc --noEmit`.
- Dependencies: approved plan.

### Task 2: Localize feature pages and error mapping

- Files: `src/features/dashboard/dashboard-page.tsx`, `src/features/portfolio/portfolio-page.tsx`, `src/features/watchlist/watchlist-page.tsx`, `src/features/activity/activity-page.tsx`, `src/features/portfolio/portfolio-provider.tsx`.
- Change: translate all existing page copy, states, forms, analysis statuses, ARIA labels, and user-safe provider errors. Introduce one small typed Vietnamese message/status mapper only if it removes repeated strings.
- Acceptance: dashboard, portfolio, watchlist, activity, and provider-generated errors are Vietnamese before financial behavior changes begin.
- Verification: update/assert Vietnamese copy in `dashboard.test.tsx`, `portfolio-page.test.tsx`, `watchlist-page.test.tsx`, and `portfolio-provider.test.tsx`; run those tests.
- Dependencies: Task 1.

### Checkpoint A

- `npm run test:run`, `npm run lint`, `npx tsc --noEmit`, and `npm run build` pass.
- Manual browser review confirms Vietnamese at 320px and 1440px, including login and error states.
- Capture temporary before/after screenshots for the eventual PR description; do not commit them.

## Phase 2 — Accounting domain and secure persistence

### Task 3: Add failing ledger and valuation domain tests

- Files: `src/lib/ledger.test.ts`, `src/lib/ledger.ts`, `src/lib/quotes.test.ts`, `src/lib/quotes.ts`.
- Change: define typed cash entries, buys/sells, wallet replay, weighted-average cost, realized sales, quote freshness, position valuation, incomplete totals, and deterministic event ordering.
- Acceptance: tests initially demonstrate the missing behaviors, then pure functions pass all cases in the specification without network or Supabase dependencies.
- Verification: `npm run test:run -- src/lib/ledger.test.ts src/lib/quotes.test.ts`.
- Dependencies: Checkpoint A.

### Task 4: Create the wallet/trade migration through Supabase CLI

- Files: one CLI-created file under `supabase/migrations/`, `supabase/config.toml` only if function exposure requires an existing-config adjustment, and a migration test/verification script if the current harness supports it.
- Change: add wallet/cash tables, transaction tax/update fields, quote/run observability fields, constraints, indexes, RLS, explicit grants, narrowly scoped RPCs, the private replay helper, and existing-data opening-balance backfill.
- Security: revoke default function execute; revoke direct authenticated financial-table mutations; grant owner reads and authenticated RPC execution only; qualify all objects and set an empty search path in definer functions.
- Acceptance: invalid, unauthorized, concurrent, overspending, overselling, and history-breaking mutations fail atomically; valid mutations return a consistent wallet/ledger snapshot.
- Verification: create the migration with `npx supabase migration new ...`; inspect generated SQL; run local Supabase database tests/advisors if Docker is available. Hosted migration requires separate approval.
- Dependencies: Task 3.

### Task 5: Extend the store contract and Supabase adapter

- Files: `src/features/portfolio/portfolio-store.ts`, `src/features/portfolio/portfolio-store.test.ts`, `src/features/portfolio/portfolio-provider.tsx`, `src/features/portfolio/portfolio-provider.test.tsx`.
- Change: load wallet/cash/trade/quote data; expose deposit, withdrawal, buy, sell, update, and delete mutations through RPC; map stable server codes to Vietnamese; derive positions, realized sales, and latest quotes.
- Acceptance: the client cannot use a direct financial-table write path, all mutations reload one coherent snapshot, and unknown database detail is not shown to users.
- Verification: adapter/provider tests cover successful and rejected mutations, stale edit conflicts, and reload failure; run focused Jest tests and TypeScript.
- Dependencies: Tasks 3–4.

### Task 6: Build wallet funding and buy/sell forms

- Files: `src/features/dashboard/dashboard-page.tsx`, `src/features/portfolio/wallet-form.tsx`, `src/features/portfolio/trade-form.tsx`, `src/features/dashboard/dashboard.test.tsx`, `src/styles/app.css`.
- Change: add wallet card, deposit/withdraw actions, buy/sell mode, cost/proceeds preview, fees/tax, execution time, wallet/share availability, and server-error presentation. New users are guided to deposit first; a holding's Sell action prefills symbol and available quantity.
- Acceptance: fund → buy → sell can be completed from phone or desktop; obvious insufficient-cash/share submissions are disabled but server validation remains authoritative.
- Verification: component tests for each mode, keyboard flow, 320/768/1440px browser checks.
- Dependencies: Task 5.

### Task 7: Add editable Activity ledger

- Files: `src/features/activity/activity-page.tsx`, `src/features/activity/ledger-entry-editor.tsx`, `src/features/activity/activity-page.test.tsx`, `src/styles/app.css`.
- Change: merge and chronologically display cash and trade events; show price, principal/proceeds, fee, tax, wallet effect, realized P/L, and `Đã chỉnh sửa`; add accessible edit/delete actions with consequence confirmations.
- Acceptance: every user-created entry can be corrected or removed; rejected corrections preserve the original row and show an actionable Vietnamese reason.
- Verification: tests cover editing/deleting all entry types, cancellation, stale edit conflict, and a later-ledger invariant failure; responsive browser review.
- Dependencies: Tasks 5–6.

### Checkpoint B

- Local tests, lint, TypeScript, and build pass.
- Local/staging database verification proves wallet balance and share invariants, direct-write denial, and two-user isolation.
- A migrated legacy account has the minimum labeled opening balance and unchanged holdings.
- Manual evidence covers deposit, buy, edit, partial sell, full sell, withdrawal, and rejection paths.

## Phase 3 — Reliable GitHub quote callback

### Task 8: Extend and test the callback schema

- Files: `src/lib/analysis/contract.ts`, `src/lib/analysis/contract.test.ts`, `supabase/functions/analysis-callback/index.ts`, `supabase/functions/analysis-callback/index.test.ts` if the function harness supports it.
- Change: require a valid quote on success, support safe quote/timeout error codes, persist quote fields, make identical terminal callbacks idempotent, reject conflicting terminal callbacks, and verify that exactly one expected run is addressed.
- Acceptance: invalid signature/payload/quote cannot change a run; a valid signed callback stores price, source, time, summary, and completion atomically.
- Verification: contract unit tests plus local Edge Function requests for valid, invalid, duplicate, and conflicting callbacks.
- Dependencies: Task 4.

### Task 9: Extract the current-run quote and retry delivery in GitHub Actions

- Files: `.github/scripts/callback_analysis_run.py`, one focused test file under `tests/`, `.github/workflows/00-daily-analysis.yml`.
- Change: pass requested symbol and workflow start time; read only the analysis-history record created for that symbol during the current run; validate and serialize price/source/time; retry callback delivery three times with sanitized diagnostics.
- Acceptance: a success without a valid current-run quote produces `QUOTE_UNAVAILABLE`; old/wrong-symbol rows are never returned; tests inject HTTP/time dependencies and do not sleep or use the network.
- Verification: focused Python tests, `python -m py_compile .github/scripts/callback_analysis_run.py`, workflow YAML review, and a dry fixture database test.
- Dependencies: Task 8.

### Task 10: Improve dispatch observability and timeout recovery

- Files: `supabase/functions/request-analysis/index.ts`, `src/lib/analysis/github-dispatch.ts`, their focused tests, and `docs/supabase-worker-spec.md`.
- Change: support GitHub's current dispatch response when it includes run metadata while retaining legacy empty responses; persist safe external run details; fail active requests older than 45 minutes with `CALLBACK_TIMEOUT` before allowing retry; document exact secret/variable placement and diagnostics.
- Acceptance: a missing callback cannot block a symbol forever, and configuration failures distinguish dispatch, callback timeout, and quote extraction without leaking secrets.
- Verification: function/contract tests for current and legacy responses, stale-run recovery, missing configuration, and sanitized errors.
- Dependencies: Tasks 8–9.

### Checkpoint C

- One staged `.VN` request is dispatched from the signed-in app.
- The workflow produces a new analysis record, posts a valid HMAC callback, and the matching `analysis_runs` row stores quote provenance.
- Invalid signatures and stale records fail; a deliberately missing callback becomes retryable after timeout.
- No secret or private report content appears in browser payloads or logs.

## Phase 4 — Valuation UI and final integration

### Task 11: Render holdings, total assets, and profit/loss

- Files: `src/features/dashboard/dashboard-page.tsx`, `src/features/portfolio/portfolio-page.tsx`, `src/features/portfolio/position-card.tsx`, their focused tests, and `src/styles/app.css`.
- Change: show wallet cash, quoted portfolio value, total assets, cost basis, average cost, latest price/source/time, unrealized amount/percent, and incomplete/stale states. Add accessible positive, negative, and neutral visual treatments.
- Acceptance: buy-price versus latest-price difference is correct per position and in totals; missing quotes never become zero; stale data is visibly labeled.
- Verification: component tests with positive, negative, zero, stale, and mixed missing-quote fixtures; browser review at all target widths.
- Dependencies: Checkpoints B–C.

### Task 12: Final integration, documentation, and visual evidence

- Files: affected tests, `docs/supabase-worker-spec.md`, `docs/implementation-plan.md`, parent `docs/CHANGELOG.md`, and only directly relevant operational docs.
- Change: reconcile final contracts, Vietnamese terminology, configuration, migration/rollback instructions, and `[Unreleased]` changelog entries. Do not add temporary screenshots to Git.
- Acceptance: docs match executable behavior; no stale claim says quotes are unavailable or UI is English; bilingual docs are synchronized where required or the handoff explains why not.
- Verification: full Web gate, focused root Python tests, migration checks, manual responsive/accessibility pass, and staged end-to-end run.
- Dependencies: Task 11.

## Final validation commands

Run through Command Prompt as required by the repository:

```cmd
cmd.exe /d /c "cd personal-stock-tracking && npm run test:run && npm run lint && npx tsc --noEmit && npm run build"
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe -m pytest <focused-callback-tests>"
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe -m py_compile .github\scripts\callback_analysis_run.py"
```

When local Supabase is available, also run migration/database tests and database advisors. Applying a migration, deploying Edge Functions, or changing GitHub/Supabase secrets is an external-state change and requires explicit approval immediately before execution.

## Rollback strategy

1. UI/store rollback: revert the Web slice while leaving additive wallet/quote columns in place.
2. Callback rollback: restore the prior callback payload; new quote columns are nullable and do not break old readers.
3. Database rollback: do not drop migrated cash or trade data. Disable new mutation RPC grants, restore the previous app version, and use a reviewed forward migration to correct schema behavior.
4. Opening balances are migration records, not disposable seed data. Never delete them during rollback without first proving the resulting wallet history remains valid.

## Key risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Historical edit corrupts later state | High | Serialized RPC plus full chronological replay and rollback-on-error. |
| Existing portfolios become unfunded | High | Deterministic minimum opening-balance migration. |
| Concurrent tabs overspend | High | Lock one wallet row for every financial mutation. |
| Quote is mistaken for live data | High | `Giá gần nhất`, provenance, timestamp, and 30-minute stale label. |
| GitHub callback is lost | High | Retry, run observability, 45-minute timeout, and safe retry path. |
| Security-definer RPC is overprivileged | High | One-purpose functions, empty search path, qualified names, owner checks, explicit execute grants, and RLS. |
| Green/red is inaccessible | Medium | Icons and text labels in addition to color. |
| Large UI diff regresses mobile | Medium | Small slices, component tests, and five-width browser verification. |

## Approval checkpoint

Replying with approval authorizes local implementation of Tasks 1–12 and local validation. It does not authorize applying hosted Supabase migrations, deploying functions, changing GitHub/Supabase secrets, committing, pushing, or opening a PR; those actions will be requested separately when reached.
