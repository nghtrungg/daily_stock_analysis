# Spec: Supabase persistence and secure stock-analysis worker

## Status

Draft for approval before schema, authentication, dependency, and external-worker changes.

## Objective

Replace the browser-only portfolio state with authenticated, per-user Supabase data. A signed-in owner can add transactions and watchlist symbols from any device. They can request analysis for a symbol; the request is queued safely, dispatched only by a server-side Edge Function to the repository's GitHub Actions workflow, and the resulting status is shown in the app.

The first release uses email/password registration and sign-in and has no trading or broker integration. It does not claim a quote or analysis is live until a worker callback has recorded a result.

## Assumptions to approve

1. Email/password registration and sign-in are the MVP account method.
2. Each signed-in user may only read and change their own portfolio, watchlist, and analysis runs.
3. The worker is the repository's `00-daily-analysis.yml` GitHub Actions workflow, dispatched through GitHub's REST API with a fine-grained Actions-write token.
4. The workflow does not execute trades, access broker accounts, or receive Supabase service-role credentials.
5. A 60-second cooldown per signed-in user and symbol is sufficient for the single-owner MVP.

## Tech stack

- Next.js 16 App Router and TypeScript.
- `@supabase/supabase-js` and `@supabase/ssr` for browser and cookie-backed server clients.
- Supabase Auth, Postgres with RLS, and Edge Functions.
- Zod for the public request/callback schemas.

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
| `portfolio_transactions` | `id`, `user_id`, `transaction_type`, `symbol`, `quantity`, `unit_price_vnd`, `fee_vnd`, `occurred_at` | The owner may select, insert, update, and delete only rows where `user_id = auth.uid()`. |
| `watchlist_symbols` | `id`, `user_id`, `symbol`, `created_at` | The owner may select, insert, and delete only their rows; `(user_id, symbol)` is unique. |
| `analysis_runs` | `id`, `user_id`, `symbol`, `status`, `requested_at`, `completed_at`, `summary`, `error_code` | The owner can read their rows. Only the request function inserts rows; the callback function updates run status. |

Input constraints reject non-`.VN` symbols, non-positive quantities/prices, negative fees, invalid statuses, and duplicate watchlist rows. Every owner-facing RLS policy uses `TO authenticated` and `(select auth.uid()) = user_id`; updates use both `USING` and `WITH CHECK`.

A private, non-callable database trigger rejects a new analysis request when that user-symbol has a run in the last 60 seconds. A partial unique index also prevents concurrent active runs for the same user-symbol. These safeguards live in the database so browser retries cannot bypass them.

## Public contracts

### `request-analysis` Edge Function

Input:

```ts
type RequestAnalysisInput = {
  symbol: string; // canonical, validated as `SYMBOL.VN`
};
```

It requires the caller's Supabase JWT (`verify_jwt = true`), validates the body, and uses the RLS-scoped client. On success it creates one run and returns `{ runId, status: 'queued' | 'dispatched' }`. The function dispatches `00-daily-analysis.yml` at the configured repository ref with `stock_symbols` and `tracking_run_id` inputs. The workflow uses the supplied `.VN` symbol only for that run, forces stock-only mode, and posts a signed completion callback. No client secret or Supabase service-role key leaves Supabase.

Errors follow `{ error: { code, message } }`: `UNAUTHENTICATED`, `VALIDATION_ERROR`, `COOLDOWN_ACTIVE`, `ACTIVE_RUN_EXISTS`, `WORKER_NOT_CONFIGURED`, or `DISPATCH_FAILED`. Messages never reveal the worker URL, token, stack trace, or database detail.

### `analysis-callback` Edge Function

Input:

```ts
type AnalysisCallbackInput = {
  runId: string;
  status: 'succeeded' | 'failed';
  summary?: string;
  errorCode?: 'SOURCE_UNAVAILABLE' | 'PROCESSING_FAILED';
};
```

The endpoint intentionally has `verify_jwt = false` because the worker is not a Supabase user. It authenticates every raw request with a constant-time HMAC signature using `ANALYSIS_CALLBACK_SECRET`, validates the body, and uses server-only privileged access to update only the addressed run. It is idempotent: completed runs are not overwritten.

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

- Unit: symbol/request/callback schemas, error mapping, and analysis run state transitions.
- Component: signed-out sign-in state; signed-in load, mutation, pending, and safe error states.
- Migration review: inspect RLS policy SQL and run Supabase advisors after a linked project is available.
- Manual staging: test registration (including email confirmation when enabled), password sign-in, cross-browser persistence, RLS isolation with two accounts, cooldown, a missing worker configuration, dispatch failure, valid callback, and an invalid callback signature.

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

Required only if Codex is to deploy through the Supabase CLI:

```text
SUPABASE_ACCESS_TOKEN
SUPABASE_PROJECT_REF
```

## Success criteria

- A signed-out visitor is guided to password sign-in or registration; authenticated session cookies are refreshed safely.
- A user can create, reload, and see only their own transactions and watchlist entries.
- The database rejects invalid symbols, duplicate watchlist symbols, unauthorized row changes, concurrent active runs, and requests inside the cooldown.
- `Analyze` requests a run and renders queued/dispatched/succeeded/failed status without exposing internal failures.
- GitHub Actions is never contacted from the browser; absent dispatch secrets cause a safe `WORKER_NOT_CONFIGURED` state.
- Tests, linting, TypeScript, production build, and a staged RLS/worker verification pass.

## Open questions

- Please approve the five assumptions above before implementation begins.
- Provide the three Edge Function secrets when the worker endpoint is ready. For a Codex-led hosted deployment, also provide a CLI access token and project ref through a secure local environment, not source control.
