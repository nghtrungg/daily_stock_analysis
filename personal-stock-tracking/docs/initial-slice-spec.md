# Spec: Portfolio tracker initial application slice

## Objective

Build the first usable, phone-first shell of the Personal Vietnam Portfolio Tracker. It gives a single private investor a clear empty dashboard, an in-memory transaction flow, VND-only presentation, `.VN` symbol validation, and a visible distinction between portfolio, analysis, and quote states. It is a safe frontend foundation for the Supabase-backed product defined in the approved product plan.

Success for this slice is a local user who can add a valid buy transaction, see the holding and cost basis update immediately, and understand that the displayed price and analysis are unavailable until a trusted integration provides them.

## Tech stack

- Next.js App Router + React 19 + TypeScript (strict).
- Next.js file-system routing and route-level layouts.
- Jest and Testing Library for unit and component tests.
- Next.js web-manifest metadata and an offline fallback. A Next-compatible service-worker adapter will be added only in the PWA hardening slice.
- Supabase client configuration only; no privileged key or backend mutation is included in this slice.

## Commands

```cmd
npm run dev
npm run test
npm run test:run
npm run build
npm run lint
```

## Project structure

```text
src/
  app/          Next.js routes, layouts, metadata, and providers
  components/   Layout, portfolio, and reusable UI components
  features/     Dashboard and local portfolio feature state
  lib/          VND, dates, symbols, and position calculations
  styles/       Hallmark-stamped page styles
  test/         Test setup and domain tests
public/         PWA icons and offline page
docs/           Product decisions and implementation plans
```

## Code style

- Use named exports, strict TypeScript, and immutable data transforms.
- Keep financial rules in `src/lib`, not in JSX.
- Use `Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' })` for money display.
- Validate and canonicalise symbols before storing them.

```ts
export function isVietnamSymbol(value: string): boolean {
  return /^[A-Z0-9]{1,10}\.VN$/.test(value.trim().toUpperCase());
}
```

## Testing strategy

- Unit-test VND formatting, symbol canonicalisation, and weighted-average position calculations.
- Test the dashboard’s empty state and the add-transaction flow with Testing Library.
- Use only deterministic local fixtures. Do not call market-data providers, Supabase, GitHub, or a broker in tests.

## Boundaries

- Always: preserve VND-only and `.VN` validation, label data freshness, and show states separately.
- Ask first: add a database migration, configure Supabase/Vercel/GitHub secrets, add a broker/provider integration, or make a network dispatch.
- Never: expose credentials, execute trades, present cached data as live, or create an Analyse-all action.

## Success criteria

- A mobile-width Next.js dashboard opens with a safe, useful empty state.
- A valid buy is recorded in local state and recalculates quantity and weighted average cost.
- Invalid symbols and non-positive quantities/prices are rejected before storage.
- No UI invents a current quote, performance metric, or analysis result.
- The app builds, linting passes, and domain/UI tests pass.

## Open questions

- English is the initial interface language; Vietnamese or bilingual copy can follow as a dedicated localisation slice.
- Supabase project credentials, authenticated owner, and RLS schema are not yet present in this repository.
- Quote freshness window and analysis cooldown remain 60-second/default-plan decisions until the backend slice starts.
