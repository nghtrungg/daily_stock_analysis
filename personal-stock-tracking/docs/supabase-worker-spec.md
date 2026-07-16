# Spec: Supabase persistence and secure stock-analysis worker

## Status

Implemented locally through the wallet, correction-ledger, tracked-quote, and worker-contract slices. The additive migrations and Edge Functions have not been applied or deployed to a hosted Supabase project in this worktree. Hosted backup, migration, secrets, deployment, and staging checks still require explicit approval.

## Objective

Provide authenticated, per-user Supabase persistence for a VND wallet, cash entries, trades, watchlist symbols, and analysis quotes. A signed-in owner can correct non-opening ledger entries through atomic RPCs, request analysis for a symbol, and see quote-aware portfolio valuation when every held symbol has a valid tracked quote.

The first release uses email/password registration and sign-in and has no trading or broker integration. It does not claim a quote or analysis is live until a worker callback has recorded a result.

## Assumptions to approve

1. Email/password registration and sign-in are the MVP account method.
2. Each signed-in user may only read and change their own portfolio, watchlist, and analysis runs.
3. The worker is the repository's `00-daily-analysis.yml` GitHub Actions workflow, dispatched through GitHub's REST API with a fine-grained Actions-write token.
4. The workflow does not execute trades, access broker accounts, or receive Supabase service-role credentials.
5. A 60-second cooldown per signed-in user and symbol limits normal retries. An active run older than 45 minutes is failed as `CALLBACK_TIMEOUT` for that same owner and symbol immediately before a replacement request is created.

## Tech stack

- Next.js 16 App Router and TypeScript.
- `@supabase/supabase-js` and `@supabase/ssr` for browser and cookie-backed server clients.
- Supabase Auth, Postgres with RLS, and Edge Functions.
- Zod for browser request validation and a strict, dependency-free runtime parser shared by the callback Edge Function.

## Commands (Command Prompt)

```cmd
npm run test:run
npm run lint
npm run build
npx tsc --noEmit
npx supabase --help
npx supabase migration --help
npx supabase functions --help
```

## Project structure

```text
src/lib/supabase/         browser, server, and session-refresh helpers
src/features/auth/        sign-in form and authenticated UI boundary
src/features/portfolio/   Supabase-backed portfolio adapter and provider
src/lib/analysis/         input/output schemas and user-safe error mapping
supabase/migrations/      CLI-created schema/RLS migrations
supabase/functions/       request-analysis and analysis-callback Edge Functions
docs/                     this specification and its implementation plan
```

## Data model and authorization

All following tables are in the `public` schema, exposed only through the Supabase Data API with RLS enabled and explicit grants for `authenticated`:

| Table | Essential fields | Ownership rule |
| --- | --- | --- |
| `portfolio_wallets` | `user_id`, `currency`, `available_cash_vnd`, timestamps | The owner may select their VND wallet. Only financial RPCs mutate it. |
| `portfolio_cash_entries` | `id`, `user_id`, `entry_type`, `amount_vnd`, `note`, timestamps | The owner may select their ledger. Deposit/withdrawal changes use RPCs; migrated `opening_balance` rows are read-only. |
| `portfolio_transactions` | `id`, `user_id`, `transaction_type`, `symbol`, `quantity`, `unit_price_vnd`, `fee_vnd`, `tax_vnd`, timestamps | The owner may select their trades. Create/update/delete operations use RPCs that replay the complete ledger atomically. |
| `watchlist_symbols` | `id`, `user_id`, `symbol`, `created_at` | The owner may select, insert, and delete only their rows; `(user_id, symbol)` is unique. |
| `analysis_runs` | Status fields plus `current_price_vnd`, `quote_as_of`, `quote_source`, `external_run_id`, and `external_run_url` | The owner can read their rows. Edge Functions create/update runs; three quote fields must be all null or all present. |

Input constraints reject non-`.VN` symbols, non-positive quantities/prices, negative fees/taxes, incomplete quotes, invalid statuses, and duplicate watchlist rows. Every owner-facing RLS policy uses `TO authenticated` and `(select auth.uid()) = user_id`. The authenticated role has no direct insert/update/delete grant on financial tables. Public `security definer` RPCs use `set search_path = ''`, derive the owner from `auth.uid()`, lock one wallet, replay cash and shares in deterministic order, and roll back the whole statement on insufficient cash or shares.

A private, non-callable database trigger rejects a new analysis request when that user-symbol has a run in the last 60 seconds. A partial unique index also prevents concurrent active runs for the same user-symbol. These safeguards live in the database so browser retries cannot bypass them.

## Public contracts

### `request-analysis` Edge Function

Input:

```ts
type RequestAnalysisInput = {
  symbol: string; // canonical, validated as `SYMBOL.VN`
};
```

It requires the caller's Supabase JWT (`verify_jwt = true`), validates the body, and uses the RLS-scoped client. Before insert it fails only that owner's matching active run older than 45 minutes with `CALLBACK_TIMEOUT`. On success it creates one run and returns `{ runId, status: 'dispatched' }`. The function dispatches `00-daily-analysis.yml` at the configured repository ref with `stock_symbols` and `tracking_run_id` inputs. Current GitHub API responses persist the returned workflow run ID and safe GitHub URL; legacy empty successful responses remain compatible. No client secret or Supabase service-role key leaves Supabase.

Errors follow `{ error: { code, message } }`: `UNAUTHENTICATED`, `VALIDATION_ERROR`, `COOLDOWN_ACTIVE`, `ACTIVE_RUN_EXISTS`, `WORKER_NOT_CONFIGURED`, or `DISPATCH_FAILED`. Messages never reveal the worker URL, token, stack trace, or database detail.

### `analysis-callback` Edge Function

Input:

```ts
type AnalysisCallbackInput = {
  runId: string;
  status: 'succeeded';
  summary: string;
  quote: {
    currentPriceVnd: number; // positive safe integer VND
    asOf: string; // timezone-aware timestamp
    source: string;
  };
} | {
  runId: string;
  status: 'failed';
  errorCode: 'SOURCE_UNAVAILABLE' | 'PROCESSING_FAILED' | 'QUOTE_UNAVAILABLE';
};
```

The endpoint intentionally has `verify_jwt = false` because the worker is not a Supabase user. It authenticates every raw request with a constant-time HMAC signature using `ANALYSIS_CALLBACK_SECRET`, rejects unknown or incomplete fields, and uses server-only privileged access to update the exact run and owner atomically. An identical terminal callback is idempotent; a conflicting terminal callback returns `409` and never overwrites the saved result.

The workflow records the tracking start time immediately before analysis. After a successful analysis, the callback helper reads the isolated SQLite database in read-only mode and accepts exactly one matching `.VN` record created during that workflow. Missing, invalid, old, or ambiguous quote data produces `QUOTE_UNAVAILABLE`, not a nominal success. Delivery uses at most three attempts with 1- and 2-second backoff and logs only the run ID, attempt number, and sanitized category.

## Code style

```ts
const requestAnalysisSchema = z.object({
  symbol: z.string().trim().toUpperCase().regex(/^[A-Z]{1,10}\.VN$/),
});

export function parseAnalysisRequest(input: unknown) {
  return requestAnalysisSchema.parse(input);
}
```

Validate at the browser form, Edge Function, and callback boundary. Internal domain functions receive typed, canonical values. Keep visual components focused; data fetching and mutations live in the portfolio/auth adapters.

## Testing strategy

- Unit: symbol/request/callback schemas, quote valuation, ledger replay, RPC adapter behavior, dispatch metadata, callback signing, current-run quote extraction, and retry limits.
- Component: deposit/withdrawal, buy/sell, correction rejection, mixed activity ordering, quote completeness/staleness, pending states, and safe errors.
- Local database: `npx supabase start`, then `npx supabase test db`. `supabase/tests/portfolio_wallet.test.sql` reruns the convergence migration twice inside a transaction and verifies preservation, idempotency, RLS, grants, RPC behavior, and oversell failure.
- Hosted staging after approval: database advisors, two-account RLS isolation, direct-write denial, cooldown, stale-run recovery, missing worker configuration, current and legacy dispatch responses, invalid signature, identical callback replay, conflicting callback, and a real `.VN` quote callback.

## Threat model and boundaries

| Boundary | Abuse case | Control |
| --- | --- | --- |
| Browser to Supabase | A user reads another portfolio | RLS ownership policies and authenticated cookie session. |
| Browser to function | A caller requests arbitrary symbols or floods requests | JWT validation, `.VN` schema, database cooldown, active-run constraint. |
| Function to GitHub Actions | A browser steals a dispatch credential or changes the repository target | The fine-grained token and repository/workflow configuration exist only in Edge Function secrets; repository and workflow names are validated before dispatch. |
| GitHub Actions to callback | A third party marks a run complete | HMAC verification before any privileged update. |

- Always: validate external input, enable RLS, use a verified Supabase identity on server code, keep secrets out of logs/source, and make failure states explicit.
- Ask first: run a migration against the hosted project, add `@supabase/ssr`, configure registration-confirmation redirect URLs/SMTP, or configure/deploy an external worker.
- Never: put a service-role key, worker credential, callback secret, or portfolio export in `NEXT_PUBLIC_*` variables; expose a callback without signature verification; execute trades.

## Required configuration

Already present locally (public by design):

```text
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
```

Required only in Supabase Edge Function secrets, never in the Next.js `.env` file or browser:

```text
GITHUB_ACTIONS_DISPATCH_TOKEN
GITHUB_REPOSITORY
GITHUB_WORKFLOW_FILE=00-daily-analysis.yml
GITHUB_WORKFLOW_REF
ANALYSIS_CALLBACK_SECRET
```

`GITHUB_ACTIONS_DISPATCH_TOKEN` must be a fine-grained token scoped to the configured repository with Actions read/write permission. `GITHUB_WORKFLOW_REF` must be the repository default branch that contains the workflow file, because GitHub only dispatches this trigger when the workflow exists on that branch. For a deployed browser client, also set `APP_ORIGIN` to the exact HTTPS application origin. Local development safely defaults to `http://localhost:3000`.

In GitHub repository settings, configure `ANALYSIS_CALLBACK_SECRET` as a repository secret with the same value and `PERSONAL_TRACKING_CALLBACK_URL` as a repository variable set to `https://<project-ref>.supabase.co/functions/v1/analysis-callback`. The workflow signs its raw JSON callback body as HMAC-SHA256 in the `x-analysis-signature` header. It must never receive a Supabase secret key.

`DATABASE_PATH` may be configured as a GitHub repository variable. It defaults to the Vietnam-local `./data/stock_analysis_vn.db` and must continue to point at the isolated Vietnam database used by the same workflow run.

The tracking app polls active `analysis_runs` every 10 seconds. This lets the UI show the terminal callback status without a manual page refresh; polling stops as soon as the run succeeds or fails.

Required only if Codex is to deploy through the Supabase CLI:

```text
SUPABASE_ACCESS_TOKEN
SUPABASE_PROJECT_REF
```

## Hosted rollout and rollback

1. Create a hosted database backup or export and verify it is listed and downloadable. Record existing transaction, wallet, cash-entry, policy, and index counts.
2. Obtain explicit approval for the resolved project reference and migration list. Apply only the existing additive migrations; do not use reset, repair, truncate, or destructive SQL.
3. Run database advisors and two-account RLS/direct-write checks. Compare representative legacy trade fingerprints and row counts with the pre-migration inventory.
4. Configure Edge Function secrets and the GitHub callback secret/URL, then deploy `request-analysis` and `analysis-callback`. Deploy the Web client only after the database and functions pass staging checks.
5. Exercise one tracked `.VN` symbol end to end and confirm run metadata, quote source/time, wallet valuation, retry/idempotency behavior, and sanitized logs.

For rollback, first revert the Web client and Edge Functions to the previous versions and disable the tracking callback variable if necessary. The schema changes are intentionally additive; do not drop the wallet, ledger, quote columns, policies, or functions as an emergency rollback. Restore the verified backup only for proven data corruption and only with a separately approved recovery plan.

## Success criteria

- A signed-out visitor is guided to password sign-in or registration; authenticated session cookies are refreshed safely.
- A user can fund a VND wallet, record/correct trades, reload, and see only their own ledger and watchlist entries.
- The database rejects invalid symbols, duplicate watchlist symbols, unauthorized row changes, concurrent active runs, and requests inside the cooldown.
- `Analyze` requests a run and renders queued/dispatched/succeeded/failed status without exposing internal failures; a successful run contributes a quote only when all quote fields are valid.
- GitHub Actions is never contacted from the browser; absent dispatch secrets cause a safe `WORKER_NOT_CONFIGURED` state.
- Tests, linting, TypeScript, production build, and a staged RLS/worker verification pass.

## Remaining approvals

- Start and validate the local Supabase stack when Docker is available.
- Approve a specific hosted backup/migration/function deployment only after reviewing the local verification evidence.
- Provide deployment credentials and secrets through secure environment configuration only if this workspace should perform that hosted rollout.
