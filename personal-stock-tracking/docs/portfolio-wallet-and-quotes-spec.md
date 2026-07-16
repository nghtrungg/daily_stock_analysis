# Specification: Vietnamese wallet, trade lifecycle, and tracked quotes

## Status

Proposed on 2026-07-16. Application implementation must not start until the user approves this specification and the companion implementation plan.

## Objective

Turn Personal Stock Tracking into a Vietnamese, wallet-backed portfolio ledger for Vietnam securities. A signed-in owner must fund a VND wallet before buying, may record buys and sells, may correct or remove an incorrect entry, and sees cash returned to the wallet after a sale. A completed GitHub Actions analysis must return a timestamped price so the app can show position value and profit or loss without presenting stale analysis-time data as a live market feed.

## User outcomes

1. Every user-facing page, control, status, validation message, metadata field, and accessibility label is Vietnamese.
2. A new user sees an empty VND wallet and must record a deposit before recording a buy.
3. A buy is rejected if its principal plus fees exceeds the wallet balance at that time.
4. A sell is rejected if its quantity exceeds the shares held at that time.
5. A successful sell credits net proceeds back to the wallet.
6. Deposits, withdrawals, buys, and sells can be edited or deleted. A correction is rejected if it would make cash or shares negative anywhere later in the ledger.
7. Holdings show average cost, latest analyzed price, quote time/source, market value, and unrealized profit or loss. Sales show realized profit or loss.
8. Profit and loss uses both color and an icon/text label, so meaning does not depend on color alone.
9. A missing, failed, delayed, or stale quote is explicit and never displayed as zero or as live data.

## Approved product boundaries

- Vietnam securities only, using canonical `.VN` symbols.
- VND only. Amounts are stored as integer VND; share quantities retain up to four decimal places for imported or adjusted holdings.
- This is a personal record-keeping tool, not a broker integration. It never places an order or moves real money.
- The GitHub Actions workflow provides an analysis-time quote on demand. It is not a streaming or exchange-certified quote feed.
- The UI is Vietnamese; internal identifiers and developer documentation may remain English.
- Owner-only Supabase authentication and RLS boundaries remain intact.

## Accounting rules

### Wallet

The wallet has one authoritative `available_cash_vnd` balance per user. All mutations run in a database transaction and lock that wallet row before validating or changing the ledger.

| Entry | Wallet effect |
| --- | ---: |
| Deposit | `+ amount_vnd` |
| Withdrawal | `- amount_vnd` |
| Buy | `- round(quantity × unit_price_vnd) - fee_vnd` |
| Sell | `+ round(quantity × unit_price_vnd) - fee_vnd - tax_vnd` |

Wallet cash may never be negative. A withdrawal, buy, or correction that would make it negative is rejected server-side with a stable error code and a Vietnamese UI message.

### Positions and cost basis

- Buys use moving weighted-average cost, matching the existing `derivePositions` behavior.
- Buy fees are added to cost basis.
- A sale removes `quantity × average_cost_before_sale` from the position cost basis.
- Sell fees and sell tax reduce net proceeds.
- Realized P/L for a sell is `net sale proceeds - removed cost basis`.
- Unrealized P/L is `market value at latest analyzed price - remaining cost basis`.
- Unrealized P/L percentage is calculated only when remaining cost basis is positive.
- Closing the entire position removes it from current holdings but keeps its trade history and realized P/L in Activity.

### Chronology and corrections

Ledger events are replayed by `occurred_at`, then `created_at`, then `id` for deterministic ties. Create, update, and delete operations are accepted only if the complete replay leaves non-negative wallet cash and non-negative shares after every event.

Edits use optimistic concurrency through `updated_at`. If the entry changed after the form opened, the update is rejected and the user is asked to reload instead of silently overwriting newer data.

### Existing data migration

Existing buy/sell rows were created before wallet enforcement. For each user with trades and no wallet history, the migration will:

1. Replay existing trades chronologically.
2. Calculate the maximum historical cash deficit.
3. Create a read-only `opening_balance` cash entry immediately before the first trade for exactly the amount required to keep cash non-negative.
4. Label it `Số dư đầu kỳ được tạo khi chuyển đổi dữ liệu`.
5. Create the wallet with the replayed ending cash balance.

The migration must fail with a clear diagnostic if existing sales produce a negative share balance. It must not silently invent shares.

## Data model

### `portfolio_wallets`

| Field | Contract |
| --- | --- |
| `user_id` | Primary key and owner; defaults to `auth.uid()` only in controlled mutations. |
| `currency` | Fixed to `VND`. |
| `available_cash_vnd` | Non-negative bigint; changed only by database mutation functions. |
| `created_at`, `updated_at` | Audit timestamps. |

### `portfolio_cash_entries`

| Field | Contract |
| --- | --- |
| `id`, `user_id` | UUID primary key and owner. |
| `entry_type` | `deposit`, `withdrawal`, or migration-only `opening_balance`. |
| `amount_vnd` | Positive bigint. |
| `note` | Optional bounded plain text. |
| `occurred_at`, `created_at`, `updated_at` | Event, creation, and correction timestamps. |

### `portfolio_transactions` additions

- Add `tax_vnd bigint not null default 0` with a non-negative constraint.
- Add `updated_at timestamptz not null default now()` for edit conflict detection.
- Preserve `buy` and `sell`, `.VN` validation, quantity, unit price, fee, and owner RLS.

### `analysis_runs` additions

- `current_price_vnd bigint` with a positive constraint.
- `quote_as_of timestamptz`.
- `quote_source text` with a bounded length.
- `external_run_id text` and `external_run_url text` for safe GitHub observability when returned by the dispatch API.
- `error_code` supports `QUOTE_UNAVAILABLE`, `CALLBACK_TIMEOUT`, and existing safe failure codes.

A successful run used as a quote requires all three quote fields. The app uses the newest successful run for each symbol.

## Database mutation boundary

Direct authenticated `INSERT`, `UPDATE`, and `DELETE` grants on wallet, cash-entry, and transaction tables are revoked. The browser reads owner-scoped rows and calls explicit RPC functions:

- `record_cash_entry`
- `update_cash_entry`
- `delete_cash_entry`
- `record_portfolio_trade`
- `update_portfolio_trade`
- `delete_portfolio_trade`

Each mutation function:

1. Requires `auth.uid()` and accepts no caller-supplied `user_id`.
2. Locks the user's wallet row.
3. Validates bounded scalar input and `.VN` symbols.
4. Applies the proposed mutation.
5. Replays wallet and share history.
6. Rejects the transaction if any invariant fails.
7. Stores the derived ending wallet balance and returns a refreshed snapshot.

Because these RPCs require privileges that are intentionally unavailable to direct Data API writes, they are narrowly scoped `security definer` functions with `search_path = ''`, fully qualified object names, an explicit owner check, and execution revoked from `public` and `anon`. Only `authenticated` receives execute permission. The replay helper remains in the private schema and is not callable from the API.

All exposed tables keep RLS enabled. Owner `SELECT` policies use `(select auth.uid()) = user_id`, and `user_id` is indexed.

## Application contracts

```ts
type CashEntryInput = {
  type: 'deposit' | 'withdrawal';
  amountVnd: number;
  occurredAt: string;
  note?: string;
};

type TradeInput = {
  type: 'buy' | 'sell';
  symbol: string;
  quantity: number;
  unitPriceVnd: number;
  feeVnd: number;
  taxVnd: number;
  occurredAt: string;
};

type Quote = {
  currentPriceVnd: number;
  asOf: string;
  source: string;
};
```

The portfolio snapshot contains wallet, cash entries, trades, positions, realized sales, watchlist symbols, analysis runs, and the latest valid quote per symbol. Raw Supabase or PostgreSQL messages are never shown to users; stable codes map to Vietnamese messages.

## GitHub dispatch and callback contract

### Success callback

```json
{
  "runId": "uuid",
  "status": "succeeded",
  "summary": "Phân tích đã hoàn tất.",
  "quote": {
    "currentPriceVnd": 68400,
    "asOf": "2026-07-16T15:10:00+07:00",
    "source": "configured-market-provider"
  }
}
```

### Failure callback

```json
{
  "runId": "uuid",
  "status": "failed",
  "errorCode": "QUOTE_UNAVAILABLE"
}
```

The existing raw-body HMAC-SHA256 signature in `x-analysis-signature` remains mandatory. A callback may update only the addressed non-terminal run. Repeating an identical terminal callback is idempotent; a conflicting terminal callback returns a conflict response.

The GitHub helper extracts the requested symbol's `current_price`, analysis creation time, and source from the analysis record created during the current workflow. It rejects a non-positive, non-finite, wrong-symbol, or pre-workflow value. A nominally successful analysis without a valid quote sends `QUOTE_UNAVAILABLE` rather than a false success.

Callback delivery retries three times with bounded exponential backoff. Logs include the run ID, attempt number, and sanitized error category, but never the callback secret, signature, full response body, or portfolio data.

The request function marks active runs older than 45 minutes as failed with `CALLBACK_TIMEOUT` before allowing a retry. If GitHub returns a workflow run ID/URL from dispatch, those values are stored; empty legacy responses remain supported.

## Quote presentation rules

- Label the value `Giá gần nhất`, not `Giá trực tiếp`.
- Display source and exact `Asia/Ho_Chi_Minh` time.
- Mark the quote `Đã cũ` after 30 minutes; the stale threshold is a tested application constant.
- A stale quote may still be used for an explicitly labeled estimate, but the user is prompted to analyze again.
- If one holding has no quote, do not treat it as zero. Portfolio market value and total assets must say they are incomplete and identify missing symbols.
- Positive values use green plus an upward icon and `Lãi`; negative values use red plus a downward icon and `Lỗ`; zero is neutral.

## Vietnamese information architecture

| Current | Vietnamese |
| --- | --- |
| Home | Trang chủ |
| Portfolio | Danh mục |
| Watchlist | Theo dõi |
| Activity | Lịch sử |
| Settings | Cài đặt |
| Add transaction | Ghi giao dịch |
| Deposit / Withdrawal | Nạp tiền / Rút tiền |
| Buy / Sell | Mua / Bán |
| Average cost | Giá vốn bình quân |
| Current price | Giá gần nhất |
| Unrealized P/L | Lãi/lỗ chưa thực hiện |
| Realized P/L | Lãi/lỗ đã thực hiện |

`<html lang="vi">`, `vi-VN` date/number formatting, VND display, PWA metadata, authentication copy, validation, analysis statuses, empty/loading/error states, and ARIA labels are all in scope.

## Responsive UX

- Mobile (320–767px): wallet and total-assets cards stack; primary actions remain visible; trade forms use a full-screen sheet; holdings and activity are cards, not clipped tables.
- Tablet/laptop (768–1279px): two-column summaries and compact cards.
- Desktop (1280px+): sidebar navigation, summary grid, and a dense but readable activity layout.
- Edit and delete remain keyboard accessible, have 44px touch targets, and require a confirmation that states the wallet/position consequence.
- The sell form can be opened from a holding with symbol and maximum quantity prefilled.

## Threat model

| Asset / boundary | Failure or abuse | Control |
| --- | --- | --- |
| Wallet balance | Concurrent buys overspend | Row lock plus atomic RPC and non-negative constraint. |
| Historical ledger | Edit creates an earlier negative balance or oversell | Full chronological replay inside the same transaction. |
| Owner data | User reads or changes another account | RLS, no caller-supplied owner ID, explicit grants. |
| Mutation RPC | Privileged function is abused | Narrow functions, empty search path, qualified names, owner checks, revoked default execute. |
| Callback | Attacker fabricates quote/status | Raw-body HMAC, strict schema, terminal-state checks. |
| Quote integrity | Old or wrong-symbol record is returned | Symbol/time/positive-value validation and explicit freshness. |
| Secrets/logs | GitHub or callback credentials leak | Server-only configuration and sanitized diagnostics. |

## Testing strategy

- Domain unit tests: deposits, withdrawals, one/multiple buys, weighted-average cost, partial/full sells, realized/unrealized P/L, fees, tax, rounding, overspend, oversell, stale quotes, and missing-quote totals.
- Correction tests: update/delete each entry type; reject a correction that invalidates a later event; reject stale `updated_at` values.
- Migration tests: existing buys receive the minimum opening balance; valid existing sells replay; impossible historical share balances fail.
- RLS/RPC tests: cross-user reads and mutations fail; direct writes fail; authenticated RPC succeeds only for the caller; concurrent buys cannot overspend.
- Callback tests: signed success with quote, invalid signature, wrong symbol, stale analysis record, missing quote, retry behavior, idempotent duplicate, conflicting terminal callback, and timeout recovery.
- Component tests: all user-visible copy is Vietnamese; fund wallet → buy → quote → sell → wallet credit; edit/delete confirmations; error mapping.
- Browser verification at 320, 375, 768, 1024, and 1440px with keyboard focus, no horizontal overflow, and both positive and negative P/L states.

## Success criteria

- No user-facing English remains in normal, loading, empty, validation, error, authentication, or PWA surfaces.
- A clean account cannot buy before depositing cash.
- Wallet and share invariants cannot be bypassed through the browser or direct authenticated table mutation.
- Editing or deleting an incorrect entry immediately and correctly recomputes wallet cash, positions, realized P/L, and totals.
- A sell credits the exact net proceeds to the wallet and records sale price and realized P/L.
- A real tracked GitHub run reaches a terminal state, stores a valid quote, and renders its timestamped price and P/L.
- Missing or late callbacks recover to a safe retryable state instead of polling forever.
- App tests, lint, TypeScript, production build, migration checks, root callback tests, and staged two-user RLS verification pass.

## Approval decisions

Approval of this specification accepts these recommended defaults:

1. Moving weighted-average cost for realized and unrealized P/L.
2. Sell fee plus optional sell tax (default zero) deducted from wallet proceeds.
3. Automatic minimum opening-balance entries for valid legacy portfolios.
4. Direct edit/delete with optimistic concurrency and full-ledger validation; `updated_at` identifies corrected rows, but a separate immutable revision-history table is deferred.
5. Latest analysis-time price with a 30-minute stale label, not a promise of live pricing.
6. Deposits and withdrawals are both supported so wallet accounting remains complete.

## References

- [Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Supabase database functions and security](https://supabase.com/docs/guides/database/functions)
- [Supabase breaking changes](https://supabase.com/changelog?tags=breaking-change)
- [GitHub workflow dispatch REST API](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
- [GitHub Actions secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
