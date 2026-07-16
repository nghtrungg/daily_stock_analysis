# Implementation plan: wallet-backed trades, corrections, and tracked valuation

## Status

Updated on 2026-07-16 after an end-to-end audit of the Web app, Supabase schema, Edge Functions, and GitHub Actions callback.

This document is a continuation plan. Vietnamese localization, pure ledger calculations, quote valuation helpers, and additive wallet/quote migrations already exist in the repository. They must be verified and integrated, not reimplemented.

This plan does not authorize changing the hosted Supabase project, deploying Edge Functions, changing GitHub secrets, committing, pushing, or deleting data. Those actions require separate approval at their deployment checkpoints.

Companion requirements: `docs/portfolio-wallet-and-quotes-spec.md`.

## Outcome

Deliver one coherent owner-only workflow:

```text
Deposit VND
    -> wallet balance increases
    -> buy a .VN security through an atomic database RPC
    -> wallet balance decreases by principal + fee
    -> edit or delete an incorrect ledger entry
    -> complete a GitHub Actions analysis
    -> persist its timestamped quote in analysis_runs
    -> recalculate market value, total assets, and profit/loss
    -> sell shares and credit net proceeds to the wallet
```

The app remains a record-keeping tool. Deposits, withdrawals, buys, and sells do not move real money or place broker orders.

## Audited baseline

| Area | Present now | Remaining work |
| --- | --- | --- |
| Vietnamese UI | Shell and current feature pages are localized. | Preserve terminology in all new forms, errors, confirmations, and accessibility labels. |
| Ledger domain | `src/lib/ledger.ts` and tests cover cash, buys, sells, replay, and cost basis. | Connect it to the Supabase snapshot and UI. |
| Quote domain | `src/lib/quotes.ts` and tests cover freshness and incomplete totals. | Load persisted quote fields and render valuation. |
| Database schema | Wallet, cash-entry, trade-correction, quote fields, RLS, grants, and RPC migration files exist. | Determine hosted deployment state, verify data migration, and correct only through an additive follow-up migration if necessary. |
| Web store | Loads trades, watchlist, and analysis status. | Load wallet/cash/quote data and replace direct trade inserts with RPC calls. |
| Wallet UI | None. | Add balance, deposit, and withdrawal flows. |
| Trade UI | Buy-only form writes directly to `portfolio_transactions`. | Add wallet-backed buy/sell through RPC, previews, and invariant errors. |
| Corrections | Database update/delete RPCs exist. | Add provider/store methods and Activity edit/delete UI. |
| GitHub callback | Signed callback updates analysis status and summary. | Include a validated current-run quote, retry delivery, and persist quote provenance. |
| Valuation UI | Cost basis is displayed; latest price and market value are placeholders. | Show quotes, market value, total assets, and realized/unrealized P/L. |

## Non-negotiable data-safety rules

1. Take a restorable Supabase backup before the first hosted schema change.
2. Never use `DROP TABLE`, `TRUNCATE`, destructive reset, or delete existing financial rows as part of this feature.
3. Record row counts and schema/function presence before and after deployment.
4. Treat both existing 20260716 migration files as immutable until the hosted migration/schema state is known.
5. If a migration has already been applied anywhere shared, correct it with a new additive forward migration; do not edit history in place.
6. If SQL Editor was used without migration history, inspect the actual schema and function definitions rather than assuming a file was or was not applied.
7. Preserve existing trades. For valid legacy histories, create only the minimum labeled opening balance needed by the approved specification.
8. Abort migration if legacy sales imply negative historical shares; do not invent shares or silently alter transactions.
9. All financial mutations must be atomic and owner-scoped. The browser must never write directly to wallet, cash-entry, or transaction tables.
10. Rollback must preserve saved data. Prefer disabling new UI/RPC access and shipping a forward fix over dropping columns or rows.

## Architecture and contracts

```text
Dashboard / Portfolio / Activity
              |
        PortfolioProvider
              |
        PortfolioStore
              |
     owner SELECT + RPC mutations
              |
 Supabase wallet/cash/trade/analysis tables
              ^
              |
 signed analysis-callback Edge Function
              ^
              |
 GitHub Actions current-run quote extractor
```

### Source of truth

- `portfolio_cash_entries` and `portfolio_transactions` are the immutable-in-spirit event ledger. User corrections update/delete events only through guarded RPCs.
- `portfolio_wallets.available_cash_vnd` is the database-maintained ending cash balance, recomputed from the ledger after every mutation.
- Positions, weighted cost, and realized sales are derived from the ordered ledger.
- The latest successful `analysis_runs` record with all quote fields is the quote source for a symbol.
- Total assets are `available wallet cash + quoted market value of all holdings`.
- If any holding lacks a valid quote, market value and total assets are explicitly incomplete; missing prices are never treated as zero.

### Editing policy

Editing should be forgiving about human input mistakes but strict about accounting validity:

- Users may correct type, symbol, quantity, unit price, fee, tax, note, amount, and occurrence time where applicable.
- A correction may change historical and current wallet/position totals immediately.
- The server rejects only invalid scalar input, stale edit conflicts, cross-owner access, negative cash at any replay point, or negative shares at any replay point.
- A rejected correction keeps the original entry unchanged and returns a stable code mapped to an actionable Vietnamese message.
- `updated_at` optimistic concurrency prevents one tab from silently overwriting a newer edit.

## Implementation sequence

Work in the order below. Each task is intended to be one focused, independently verifiable slice.

## Phase 0 - protect data and establish the deployment baseline

### Task 0.1: Capture hosted backup and read-only inventory

**Description:** Before hosted SQL, create a Supabase backup and capture a non-sensitive inventory of the current schema and financial row counts.

**Acceptance criteria:**

- [ ] A backup exists with a recorded creation time and restore path/procedure.
- [ ] Counts are recorded for transactions, cash entries, wallets, watchlist rows, and analysis runs without exporting private row contents.
- [ ] Presence of required columns, constraints, indexes, RLS policies, grants, and RPC signatures is recorded.
- [ ] Current migration history is recorded when available; SQL Editor-only changes are noted explicitly.

**Verification:** Restore into a disposable project or local database when the Supabase plan/tooling permits. At minimum, verify that the backup is listed and downloadable before proceeding.

**Dependencies:** None.

**Files likely touched:** No repository files unless a sanitized deployment checklist is added to `docs/`.

**Estimated scope:** S.

### Task 0.2: Verify the convergence migration against preserved data

**Description:** Test the existing additive convergence migration against a copy/fixture representing empty accounts, buy-only legacy accounts, valid buy/sell histories, and impossible oversold histories.

**Acceptance criteria:**

- [ ] Re-running the convergence migration does not duplicate opening balances, wallets, policies, or indexes.
- [ ] Valid legacy trades remain byte-for-byte equivalent in their business fields.
- [ ] The minimum opening balance is created once and produces a non-negative replay.
- [ ] An impossible historical share balance fails with a clear diagnostic before partial changes persist.
- [ ] No destructive statement or broad authenticated financial-table mutation grant remains.

**Verification:** Run local Supabase migration/database tests and database advisors. Compare before/after row counts and representative checksums for existing trades.

**Dependencies:** Task 0.1 for hosted rollout; local verification can begin earlier.

**Files likely touched:**

- `supabase/migrations/20260716095943_ensure_complete_portfolio_schema.sql` only if proven not applied anywhere shared
- otherwise one new CLI-created additive migration
- an optional focused SQL verification file under `supabase/tests/`

**Estimated scope:** M.

### Checkpoint 0: Database safety gate

- [ ] Backup and inventory are complete.
- [ ] Local/staging migration verification passes.
- [ ] Existing transaction counts and business data are preserved.
- [ ] Two-user RLS and direct-write denial are proven.
- [ ] Obtain explicit approval immediately before hosted SQL execution.

## Phase 1 - make wallet funding work end to end

### Task 1.1: Extend the snapshot and store read model

**Description:** Add wallet, cash entries, enriched trades, and quote-bearing analysis rows to the store contract, then derive positions and realized sales from one deterministic ledger snapshot.

**Acceptance criteria:**

- [ ] `PortfolioSnapshot` contains wallet, cash entries, trades, positions, realized sales, analysis runs, and latest quotes.
- [ ] Empty/new users receive a stable zero-VND wallet view without fabricated ledger entries.
- [ ] Database snake_case rows are normalized once at the adapter boundary.
- [ ] Missing or partial quote triples are excluded from `latestQuotes` and reported as incomplete.

**Verification:** Add failing adapter tests first, then run the focused store/provider tests and `npx tsc --noEmit`.

**Dependencies:** Checkpoint 0 schema contract, but tests may use fakes before hosted deployment.

**Files likely touched:**

- `src/features/portfolio/portfolio-store.ts`
- `src/features/portfolio/portfolio-store.test.ts`
- `src/features/portfolio/portfolio-provider.tsx`
- `src/features/portfolio/portfolio-provider.test.tsx`

**Estimated scope:** M.

### Task 1.2: Add deposit and withdrawal store mutations

**Description:** Expose cash-entry create operations through `record_cash_entry`; do not insert into `portfolio_cash_entries` directly.

**Acceptance criteria:**

- [ ] Deposit and withdrawal inputs are normalized and sent through RPC.
- [ ] A successful mutation reloads one coherent snapshot and shows the returned wallet balance.
- [ ] Insufficient cash, invalid amounts, unauthenticated access, and unknown server errors map to safe Vietnamese messages.
- [ ] Double submission is disabled while the RPC is pending.

**Verification:** Tests cover RPC arguments, success reload, insufficient funds, malformed input, and reload failure.

**Dependencies:** Task 1.1.

**Files likely touched:**

- `src/features/portfolio/portfolio-store.ts`
- `src/features/portfolio/portfolio-store.test.ts`
- `src/features/portfolio/portfolio-provider.tsx`
- `src/features/portfolio/portfolio-provider.test.tsx`

**Estimated scope:** M.

### Task 1.3: Build the wallet card and cash-entry form

**Description:** Show available cash prominently and let the user record a deposit or withdrawal with amount, date/time, and optional note.

**Acceptance criteria:**

- [ ] New users are guided to deposit before buying.
- [ ] Wallet balance and mutation result update without a page refresh.
- [ ] Amount input supports readable VND entry and prevents accidental decimals/negative values client-side while retaining server validation.
- [ ] Loading, success, validation, insufficient-cash, and retry states are accessible in Vietnamese.

**Verification:** Component tests plus keyboard/mobile browser review at 320, 768, and 1440px with a clean console.

**Dependencies:** Task 1.2.

**Files likely touched:**

- `src/features/portfolio/wallet-form.tsx`
- `src/features/dashboard/dashboard-page.tsx`
- `src/features/dashboard/dashboard.test.tsx`
- `src/styles/app.css`

**Estimated scope:** M.

### Checkpoint 1: Wallet vertical slice

- [ ] A clean account shows zero VND.
- [ ] Deposit increases cash and appears in Activity data.
- [ ] Withdrawal decreases cash; over-withdrawal is rejected atomically.
- [ ] Refreshing the page preserves the same wallet and entries.

## Phase 2 - replace direct buys with wallet-backed buy and sell

### Task 2.1: Replace direct trade inserts with RPC mutations

**Description:** Remove the current direct `portfolio_transactions.insert` path and expose buy/sell creation through `record_portfolio_trade`.

**Acceptance criteria:**

- [ ] No browser code directly inserts, updates, or deletes financial rows.
- [ ] Buy passes type, canonical `.VN` symbol, quantity, unit price, fee, tax, and occurrence time to the RPC.
- [ ] Sell uses the same contract and reloads wallet, holdings, and realized sales after success.
- [ ] Insufficient cash and insufficient shares preserve the original snapshot and show stable Vietnamese errors.

**Verification:** Store/provider tests assert RPC use and explicitly fail if the old direct-insert path is called.

**Dependencies:** Task 1.1 and verified RPC schema.

**Files likely touched:**

- `src/features/portfolio/portfolio-store.ts`
- `src/features/portfolio/portfolio-store.test.ts`
- `src/features/portfolio/portfolio-provider.tsx`
- `src/features/portfolio/portfolio-provider.test.tsx`

**Estimated scope:** M.

### Task 2.2: Build the buy/sell form with accounting previews

**Description:** Replace the buy-only form with a focused buy/sell component that makes wallet and share consequences clear before submission.

**Acceptance criteria:**

- [ ] Buy preview shows `quantity x price + fee` and projected remaining cash.
- [ ] Sell preview shows gross proceeds, fee, tax, net wallet credit, and available shares.
- [ ] A holding's Sell action prefills its symbol and maximum available quantity.
- [ ] Users can freely correct form values before submission; server invariants remain authoritative.
- [ ] Buttons and messages remain usable on mobile and by keyboard.

**Verification:** Component tests cover buy, partial sell, full sell, decimal quantity, fee/tax, insufficient cash/shares, and double submit; run browser checks at target widths.

**Dependencies:** Task 2.1.

**Files likely touched:**

- `src/features/portfolio/trade-form.tsx`
- `src/features/dashboard/dashboard-page.tsx`
- `src/features/dashboard/dashboard.test.tsx`
- `src/styles/app.css`

**Estimated scope:** M.

### Checkpoint 2: Wallet-backed trade slice

- [ ] Deposit -> buy deducts the exact principal plus fee.
- [ ] Buy without enough cash fails without creating a transaction.
- [ ] Partial/full sell cannot exceed holdings and credits exact net proceeds.
- [ ] Concurrent attempts from two tabs cannot overspend or oversell.
- [ ] Refresh preserves wallet, trades, holdings, and realized P/L.

## Phase 3 - let users correct or remove mistakes safely

### Task 3.1: Add update/delete methods to the store and provider

**Description:** Wire cash and trade correction methods to the four existing update/delete RPCs with `updated_at` optimistic concurrency.

**Acceptance criteria:**

- [ ] Cash entries and trades can be updated or deleted through RPC only.
- [ ] The expected `updated_at` value is always sent for concurrency checking.
- [ ] A stale edit asks the user to reload instead of overwriting.
- [ ] A correction that invalidates any later event is rejected with the original ledger unchanged.

**Verification:** Tests cover every update/delete RPC, stale conflicts, later-event cash failures, later-event oversells, and coherent reload.

**Dependencies:** Tasks 1.1 and 2.1.

**Files likely touched:**

- `src/features/portfolio/portfolio-store.ts`
- `src/features/portfolio/portfolio-store.test.ts`
- `src/features/portfolio/portfolio-provider.tsx`
- `src/features/portfolio/portfolio-provider.test.tsx`

**Estimated scope:** M.

### Task 3.2: Build the unified Activity ledger

**Description:** Merge cash and trade events into deterministic chronological presentation with clear financial consequences.

**Acceptance criteria:**

- [ ] Activity shows deposits, withdrawals, buys, sells, fees, tax, wallet effect, and realized P/L.
- [ ] Corrected rows show `Đã chỉnh sửa`.
- [ ] The ordering matches `occurred_at`, `created_at`, then `id`.
- [ ] Opening-balance migration rows are visible and labeled but cannot be edited or deleted.

**Verification:** Component tests cover mixed event ordering, empty/loading/error states, and opening-balance restrictions.

**Dependencies:** Task 1.1.

**Files likely touched:**

- `src/features/activity/activity-page.tsx`
- `src/features/activity/activity-page.test.tsx`
- `src/features/activity/ledger-entry-row.tsx`
- `src/styles/app.css`

**Estimated scope:** M.

### Task 3.3: Add edit/delete interaction and consequence confirmations

**Description:** Add an accessible editor for user-created ledger events and make the recalculation consequence explicit before destructive corrections.

**Acceptance criteria:**

- [ ] Users can correct all editable fields, including an accidentally wrong quantity or amount.
- [ ] Delete confirmation identifies the event and warns that later wallet/position values will be recalculated.
- [ ] Cancellation makes no mutation.
- [ ] Rejected updates/deletes retain the original row and entered correction so the user can adjust it.

**Verification:** Tests cover edit success, delete success, cancel, stale conflict, invariant rejection, keyboard focus restoration, and mobile layout.

**Dependencies:** Tasks 3.1-3.2.

**Files likely touched:**

- `src/features/activity/ledger-entry-editor.tsx`
- `src/features/activity/activity-page.tsx`
- `src/features/activity/activity-page.test.tsx`
- `src/styles/app.css`

**Estimated scope:** M.

### Checkpoint 3: Correction slice

- [ ] A mistaken buy quantity can be corrected and all later totals change consistently.
- [ ] An edit that would overspend or oversell is rejected without partial writes.
- [ ] Delete recalculates wallet, positions, cost basis, and realized P/L.
- [ ] A stale second-tab edit cannot overwrite a newer value.

## Phase 4 - make GitHub Actions return a usable tracked quote

### Task 4.1: Extend the shared callback contract

**Description:** Change a successful callback from status/summary-only to status/summary plus a required validated quote triple.

**Acceptance criteria:**

- [ ] Success requires positive integer `currentPriceVnd`, valid `asOf`, and bounded non-empty `source`.
- [ ] Failure supports `QUOTE_UNAVAILABLE` and preserves existing safe error codes.
- [ ] Unknown fields or invalid quote combinations are rejected before database mutation.
- [ ] Existing failure callbacks remain compatible.

**Verification:** Write failing contract tests for valid success, missing quote, invalid price/time/source, and existing failures before implementation.

**Dependencies:** Verified `analysis_runs` quote columns.

**Files likely touched:**

- `src/lib/analysis/contract.ts`
- `src/lib/analysis/contract.test.ts`
- `supabase/functions/analysis-callback/index.ts`
- a focused Edge Function test file if supported by the local harness

**Estimated scope:** M.

### Task 4.2: Persist quote and make terminal callbacks idempotent

**Description:** Store status, summary, quote price/time/source, and completion timestamps atomically for the addressed run.

**Acceptance criteria:**

- [ ] A valid signed callback updates exactly one owner-associated non-terminal run.
- [ ] Repeating the identical terminal callback succeeds without changing meaning.
- [ ] A conflicting terminal callback returns conflict and cannot replace the stored quote/status.
- [ ] Invalid HMAC, malformed JSON, wrong run, or invalid quote changes nothing.

**Verification:** Local Edge Function tests/requests cover valid, invalid signature, duplicate, conflict, missing run, and concurrent terminal updates.

**Dependencies:** Task 4.1.

**Files likely touched:**

- `supabase/functions/analysis-callback/index.ts`
- its focused test fixture/file
- `src/lib/analysis/contract.ts`
- `src/lib/analysis/contract.test.ts`

**Estimated scope:** M.

### Task 4.3: Extract only the current workflow's requested-symbol quote

**Description:** Teach the Python callback helper to read the SQLite analysis record produced for the requested symbol during the current workflow and serialize a VND quote.

**Acceptance criteria:**

- [ ] Selection requires the requested canonical symbol and a record created after the captured workflow start time.
- [ ] The helper rejects an old row, wrong symbol, missing/zero/non-finite price, or ambiguous current-run result.
- [ ] Price normalization to integer VND follows the repository's actual-VND contract.
- [ ] Nominal analysis success without a valid quote sends `QUOTE_UNAVAILABLE` rather than false success.
- [ ] Logs contain only run ID, attempt, and safe error category—not report content or secrets.

**Verification:** Python tests use a temporary SQLite fixture and injected clock/HTTP behavior; no network and no real sleep.

**Dependencies:** Task 4.1 and confirmation of the persisted `analysis_history` field contract.

**Files likely touched:**

- `.github/scripts/callback_analysis_run.py`
- `tests/test_analysis_callback.py`
- one small callback fixture/helper only if needed

**Estimated scope:** M.

### Task 4.4: Pass workflow context and retry callback delivery

**Description:** Provide the helper with the requested symbol and workflow start time, then retry bounded callback delivery without rerunning the analysis.

**Acceptance criteria:**

- [ ] The workflow passes run ID, requested symbol, start time, callback URL, and secret through appropriate contexts.
- [ ] Callback delivery makes at most three attempts with bounded exponential backoff.
- [ ] Analysis failure still produces a signed failure callback.
- [ ] Retry logs are sanitized and the secret/signature never appear.

**Verification:** Focused Python tests cover transient success, permanent failure, and retry count; review workflow expressions and run `py_compile`.

**Dependencies:** Task 4.3.

**Files likely touched:**

- `.github/workflows/00-daily-analysis.yml`
- `.github/scripts/callback_analysis_run.py`
- `tests/test_analysis_callback.py`

**Estimated scope:** M.

### Task 4.5: Recover analysis runs that never receive a callback

**Description:** Before dispatching a new analysis, mark matching active runs older than 45 minutes as `CALLBACK_TIMEOUT` so polling cannot block forever.

**Acceptance criteria:**

- [ ] Only the authenticated user's matching-symbol stale runs are recovered.
- [ ] Fresh queued/dispatched/running requests still prevent duplicate dispatch.
- [ ] A timed-out request becomes safely retryable.
- [ ] If GitHub dispatch returns run metadata, bounded ID/URL fields are persisted; legacy empty responses still work.

**Verification:** Request-function and dispatch-contract tests cover fresh/stale runs, current/legacy GitHub responses, missing configuration, and sanitized failures.

**Dependencies:** Tasks 4.1-4.2.

**Files likely touched:**

- `supabase/functions/request-analysis/index.ts`
- `src/lib/analysis/github-dispatch.ts`
- `src/lib/analysis/github-dispatch.test.ts`
- one focused request-function test file if supported

**Estimated scope:** M.

### Checkpoint 4: Quote callback slice

- [ ] A staged `.VN` request reaches a terminal state.
- [ ] The matching `analysis_runs` row stores price, source, and quote time.
- [ ] Old/wrong-symbol SQLite records cannot be returned.
- [ ] Invalid signature and conflicting duplicate callbacks cannot change a run.
- [ ] Missing callbacks become retryable after 45 minutes.

## Phase 5 - render quote-driven portfolio value

### Task 5.1: Derive latest quotes and valuation in the provider

**Description:** Feed newest valid per-symbol quotes and the wallet-backed positions into `valuePortfolio`.

**Acceptance criteria:**

- [ ] Latest quote selection is deterministic by quote time, then run completion/request order.
- [ ] Each holding receives average cost, latest price, quote metadata, market value, and unrealized P/L.
- [ ] Total assets equal wallet cash plus complete quoted market value.
- [ ] Missing symbols are listed and totals remain explicitly incomplete instead of using zero.
- [ ] Quote staleness uses one tested 30-minute constant.

**Verification:** Provider tests cover positive, negative, zero, stale, missing, and mixed portfolios.

**Dependencies:** Tasks 1.1 and 4.2.

**Files likely touched:**

- `src/features/portfolio/portfolio-provider.tsx`
- `src/features/portfolio/portfolio-provider.test.tsx`
- `src/lib/quotes.ts` only if an audited gap is found
- `src/lib/quotes.test.ts` for any changed behavior

**Estimated scope:** M.

### Task 5.2: Render wallet, holdings, market value, and total assets

**Description:** Replace current price/value placeholders on Dashboard and Portfolio with honest quote-backed values.

**Acceptance criteria:**

- [ ] Summary cards show available cash, holdings cost, quoted market value, and total assets.
- [ ] Holdings show average cost, latest price, source/time, market value, and unrealized amount/percent.
- [ ] Positive/negative/neutral states use icon and text as well as color.
- [ ] Stale quotes say `Đã cũ` and prompt re-analysis.
- [ ] Incomplete totals identify missing symbols.

**Verification:** Component tests plus browser review at 320, 375, 768, 1024, and 1440px; capture temporary PR screenshots outside Git.

**Dependencies:** Task 5.1.

**Files likely touched:**

- `src/features/portfolio/position-card.tsx`
- `src/features/portfolio/portfolio-page.tsx`
- `src/features/portfolio/portfolio-page.test.tsx`
- `src/styles/app.css`

**Estimated scope:** M.

### Task 5.3: Add the dashboard valuation summary

**Description:** Use the same provider-derived valuation on the dashboard without duplicating accounting or quote-selection logic.

**Acceptance criteria:**

- [ ] Dashboard and Portfolio show identical totals for the same snapshot.
- [ ] Analysis completion polling causes the new quote and values to appear without manual reload.
- [ ] A failed analysis keeps the previous valid quote, identifies the failed run, and does not turn values into zero.

**Verification:** Dashboard tests cover quote arrival after polling, failed refresh with previous quote, and incomplete totals.

**Dependencies:** Tasks 5.1-5.2.

**Files likely touched:**

- `src/features/dashboard/dashboard-page.tsx`
- `src/features/dashboard/dashboard.test.tsx`
- `src/features/portfolio/portfolio-provider.test.tsx`
- `src/styles/app.css`

**Estimated scope:** M.

### Checkpoint 5: Valuation slice

- [ ] Deposit -> buy -> successful analysis updates wallet, holding value, total assets, and unrealized P/L.
- [ ] Editing the buy quantity immediately recalculates cost basis and valuation.
- [ ] Sell updates wallet and realized P/L while preserving history.
- [ ] Missing/stale/failed quotes remain honest and visible.

## Phase 6 - integration, documentation, and controlled rollout

### Task 6.1: Run deterministic full validation

**Acceptance criteria:**

- [ ] All Web tests, lint, TypeScript, and production build pass.
- [ ] Root callback tests and Python compilation pass.
- [ ] Migration/RPC tests prove atomicity, concurrency protection, direct-write denial, and two-user isolation.
- [ ] No test is skipped to make the suite pass.

**Verification commands:**

```cmd
cmd.exe /d /c "cd personal-stock-tracking && npm run test:run && npm run lint && npx tsc --noEmit && npm run build"
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe -m pytest tests\test_analysis_callback.py -q"
cmd.exe /d /c "chcp 65001>nul & set \"PYTHONUTF8=1\"& .venv\Scripts\python.exe -m py_compile .github\scripts\callback_analysis_run.py"
```

Run local Supabase database tests and advisors using the installed CLI's `--help` output rather than assumed flags.

**Dependencies:** Checkpoints 1-5.

**Estimated scope:** S.

### Task 6.2: Run staged end-to-end and responsive verification

**Acceptance criteria:**

- [ ] Two isolated users complete deposit, buy, edit, analyze, value, sell, and withdraw flows without cross-account visibility.
- [ ] Network inspection shows financial mutations use RPC, not direct table writes.
- [ ] The callback request contains the quote contract and no secret/private report content.
- [ ] Console has no errors or warnings attributable to the feature.
- [ ] Keyboard, focus, touch targets, and no-horizontal-overflow checks pass at all target widths.

**Dependencies:** Task 6.1 and explicit approval for staging external-state changes.

**Estimated scope:** M.

### Task 6.3: Reconcile operational documentation and changelog

**Acceptance criteria:**

- [ ] `docs/supabase-worker-spec.md` documents quote payload, secrets, timeout, and diagnostics.
- [ ] Migration, backup, hosted SQL, Edge deployment, GitHub configuration, verification, and rollback instructions match executable behavior.
- [ ] Parent `docs/CHANGELOG.md` uses flat `[Unreleased]` entries.
- [ ] No documentation claims that wallet input, editing, or quote valuation works before its implementation checkpoint passes.

**Dependencies:** Tasks 6.1-6.2.

**Files likely touched:**

- `docs/supabase-worker-spec.md`
- `docs/implementation-plan.md` only if its project-wide status must change
- `docs/portfolio-wallet-and-quotes-spec.md` if an approved contract changed
- parent `docs/CHANGELOG.md`

**Estimated scope:** M.

### Task 6.4: Deploy in reversible order

**Deployment order:**

1. Reconfirm backup and pre-deployment counts.
2. Apply the verified additive database migration in Supabase SQL Editor or the approved migration workflow.
3. Run post-migration schema, count, RLS, and RPC smoke checks before deploying Web code.
4. Deploy the compatible callback Edge Function.
5. Update GitHub/Supabase secrets or variables only when required and approved.
6. Deploy the Web app with RPC-backed mutations and wallet UI.
7. Run one staged `.VN` analysis and confirm quote persistence and valuation.
8. Monitor callback failures, RPC errors, and timeout recovery before declaring completion.

**Rollback:**

- Web: restore the previous deployment; additive database objects remain.
- Callback: restore the prior status-only function/script only if the Web deployment still tolerates missing quotes.
- Database: revoke execution on new mutation RPCs if necessary, but do not drop wallet/cash/trade data. Correct defects with a reviewed forward migration.
- Secrets: restore prior values through the platform secret manager; never place them in Git or logs.

**Dependencies:** Tasks 6.1-6.3 and explicit deployment approval.

**Estimated scope:** M.

## Definition of done

The feature is complete only when all statements are true:

- [ ] Existing saved transactions, watchlists, and analysis runs survive migration.
- [ ] A clean account cannot buy before depositing enough VND.
- [ ] Every financial write uses an authenticated owner-only RPC.
- [ ] Cash and share balances cannot become negative under normal, corrected, deleted, or concurrent histories.
- [ ] Users can correct or delete mistaken deposits, withdrawals, buys, and sells without silently losing newer edits.
- [ ] GitHub Actions returns a quote from the requested symbol's current run, not an older database row.
- [ ] The signed callback stores quote price, source, and time on the matching analysis run.
- [ ] Analysis polling updates the displayed quote and portfolio valuation without a manual reload.
- [ ] Wallet cash, market value, total assets, realized P/L, and unrealized P/L follow the approved formulas.
- [ ] Missing/stale/failed quotes are labeled and never converted to zero.
- [ ] Vietnamese UI, accessibility, responsive checks, tests, lint, type-check, build, migration checks, and staged two-user verification pass.
- [ ] Backup, rollout, monitoring, and rollback evidence is recorded.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Hosted schema differs from migration files | High | Read-only inventory first; use additive convergence based on actual state. |
| Existing portfolio appears unfunded | High | One deterministic minimum opening balance for valid legacy histories. |
| Historical correction corrupts later state | High | Wallet-row lock, complete chronological replay, and transaction rollback. |
| Current direct buy breaks after grants are tightened | High | Ship RPC-backed store before or in the same compatible rollout as write revocation. |
| Concurrent tabs overspend/oversell | High | Serialize financial mutation with wallet lock and database-side invariant validation. |
| Old analysis row becomes the displayed quote | High | Bind extraction to requested symbol and workflow start time; reject ambiguity. |
| Callback succeeds but price is absent | High | Success contract requires quote; otherwise send `QUOTE_UNAVAILABLE`. |
| Callback is lost | High | Three delivery attempts, sanitized observability, and 45-minute recovery. |
| Quote is mistaken for live exchange data | Medium | Label `Giá gần nhất` with source, timestamp, and stale state. |
| Partial quote coverage understates assets | High | Incomplete totals with missing-symbol list; never substitute zero. |
| UI correction feels overly restrictive | Medium | Permit all reasonable field corrections; reject only invalid accounting histories and stale conflicts. |
| Rollback deletes new user data | High | Roll back application access, not rows; use forward-only schema correction. |

## Approval gates

The following approvals are separate:

1. Approve this plan and companion specification for local implementation.
2. Approve hosted Supabase backup/schema execution after Checkpoint 0 evidence.
3. Approve Edge Function and Web deployment after deterministic validation.
4. Approve GitHub/Supabase secret or variable changes immediately before they are made.
5. Approve commit, push, or PR creation if desired.
