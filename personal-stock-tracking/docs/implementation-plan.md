# Implementation Plan: Personal Portfolio Tracker

## Overview

This plan turns the approved product plan into small, verifiable slices. The first checkpoint establishes a polished local PWA shell and financial rules without pretending that a local prototype is connected to Supabase or a market-data provider.

## Architecture decisions

- Build the approved React, TypeScript, Next.js App Router, and PWA web shell in this repository.
- Keep the transaction ledger as the source of truth; derive holdings with weighted-average cost in pure functions.
- Start with local browser state. Replace only the data adapter in the later Supabase/RLS slice.
- Use English initially; keep money and time helpers locale-aware for a later Vietnamese/bilingual switch.
- Use a Hallmark custom monochrome design: near-white and graphite tokens with a restrained focus signal.

## Dependency graph

```text
Tooling + tokens
        |
Domain validation + position calculations
        |
Local dashboard state + transaction form
        |
Responsive app shell + PWA manifest
        |
Supabase schema/RLS + authenticated data adapter
        |
Single-stock analysis dispatch + queue/status UI
```

## Task list

### Phase 1: Local portfolio foundation

#### Task 1: Initialise the tested Next.js/PWA shell

- Acceptance: the project has typed Next.js build/test/lint scripts, an installable manifest, and no private variables in source control.
- Verify: `npm run build`, `npm run lint`, and `npm run test:run` succeed.
- Dependencies: none.
- Files: package/configuration files, `public/`, `src/app/layout.tsx`, and `src/app/page.tsx`.

#### Task 2: Implement and test portfolio domain rules

- Acceptance: VND formatting, `.VN` canonicalisation, and weighted-average holdings are deterministic and tested.
- Verify: `npm run test:run` covers valid and invalid inputs.
- Dependencies: Task 1.
- Files: `src/lib/*`, `src/lib/*.test.ts`.

#### Task 3: Build the local dashboard and transaction slice

- Acceptance: the user can add a buy transaction locally, see one derived holding, and view separate portfolio/analysis/quote state labels.
- Verify: component test plus a build at phone and desktop widths.
- Dependencies: Task 2.
- Files: dashboard/portfolio components and styles.

#### Task 4: Complete responsive PWA and accessibility polish

- Acceptance: the app handles 320, 375, 414, and 768px layouts with no horizontal scrolling; controls meet touch/focus requirements.
- Verify: production build and manual browser inspection.
- Dependencies: Task 3.
- Files: styles, PWA configuration, icons, offline page.

### Checkpoint: Local foundation

- Tests, linting, and build pass.
- The local flow is useful without representing mock data as a live portfolio.
- Review the dashboard information hierarchy before connecting Supabase.

### Phase 2: Secure persistence

See `docs/supabase-worker-spec.md` for the approved contract and security boundaries.

#### Task 5: Create the RLS-backed portfolio foundation

- Acceptance: a CLI-created migration defines validated transaction/watchlist/run tables, explicit authenticated grants, owner RLS policies, an active-run constraint, and a 60-second cooldown trigger.
- Verify: inspect migration SQL; link a project only after approval, then run its migration and Supabase database advisors.
- Dependencies: Phase 1 checkpoint and user approval of the Supabase/worker specification.
- Files: one generated migration, `supabase/config.toml`, and migration notes.

#### Task 6: Add cookie-backed email/password authentication

- Acceptance: signed-out users see a focused sign-in state; signed-in users have a verified cookie session refreshed by the Next.js proxy.
- Verify: component tests, lint, build, and a manual Supabase registration/password sign-in round trip.
- Dependencies: Task 5 and approved Supabase Auth redirect configuration.
- Files: Supabase client helpers, proxy, auth route/form, app shell, package files, and tests.

#### Task 7: Replace local state with the Supabase data adapter

- Acceptance: ledger/watchlist mutations persist to the signed-in owner and display loading, empty, and safe error states.
- Verify: adapter/component tests, lint, TypeScript, build, then a two-account RLS check in staging.
- Dependencies: Tasks 5–6.
- Files: portfolio provider/adapter, selected page components, tests, and styles.

### Checkpoint: Secure persistence

- A new session persists only after the owner signs in.
- RLS isolation is proven with two different accounts.
- No secret appears in Git or browser-delivered JavaScript.
- Status: migration and deployed function boundaries are complete; registration confirmation redirect URLs and a two-account staging check remain before this checkpoint is closed.

### Phase 3: Single-stock analysis

#### Task 8: Define and test the analysis contracts

- Acceptance: typed request/callback schemas, canonical `.VN` validation, and consistent user-safe error codes exist before function implementation.
- Verify: unit tests demonstrate invalid input and unsafe callback payloads are rejected.
- Dependencies: approved specification.
- Files: analysis contract module and tests.

#### Task 9: Implement secure Edge Function dispatch and callback

- Acceptance: an authenticated request inserts one constrained run, dispatches only with server-side worker secrets, and an HMAC-authenticated callback updates it idempotently.
- Verify: local function tests; staged missing-secret, valid callback, invalid signature, and cooldown checks.
- Dependencies: Tasks 5 and 8; supplied Edge Function secrets for dispatch.
- Files: two CLI-generated Edge Functions, function configuration, and tests.

#### Task 10: Connect `Analyze` UI to persistent run status

- Acceptance: enabled Analyze controls clearly show queued, dispatched, succeeded, or failed; no hidden section is inserted and route navigation remains unchanged.
- Verify: component tests plus responsive keyboard/manual checks at 320, 768, 1024, and 1440px.
- Dependencies: Tasks 7 and 9.
- Files: watchlist/dashboard components, portfolio adapter, styles, and tests.

### Checkpoint: Analysis worker

- Browser calls only the authenticated Edge Function, never the worker.
- The worker callback is authenticated and cannot disclose credentials or other users’ data.
- A real staging run completes with a known test symbol.
- Status: the dispatch/callback functions are deployed and reject unauthenticated calls; a signed owner request and a worker-signed callback remain to be exercised.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Prototype is mistaken for live data | High | Use empty/default states and label local data clearly. |
| Incorrect accounting logic | High | Keep calculations pure and test weighted-average cases first. |
| Private data leaks into client code | High | Use only public placeholder environment variables; add Supabase RLS before server data. |
| Mobile layout hides a state or action | Medium | Test four target widths and use responsive cards rather than a desktop table. |
| Worker secret or callback is abused | High | Keep credentials in Edge Function secrets; authenticate callbacks with HMAC and restrict updates to one run. |
| Duplicate requests consume quota | Medium | Enforce database-level cooldown and active-run uniqueness rather than relying on browser state. |

## Open questions

- Approve `docs/supabase-worker-spec.md`, including email/password authentication and the worker callback contract.
- Configure the GitHub Actions dispatch integration before production use: set `GITHUB_ACTIONS_DISPATCH_TOKEN`, `GITHUB_REPOSITORY`, `GITHUB_WORKFLOW_FILE`, `GITHUB_WORKFLOW_REF`, and `ANALYSIS_CALLBACK_SECRET` as Supabase Edge Function secrets. Set the same callback secret as the GitHub `ANALYSIS_CALLBACK_SECRET` repository secret and set `PERSONAL_TRACKING_CALLBACK_URL` as a GitHub repository variable.
- Provide `SUPABASE_ACCESS_TOKEN` and `SUPABASE_PROJECT_REF` only if this workspace should deploy to the hosted project.
- Confirm whether English remains the MVP UI language after the prototype review.
