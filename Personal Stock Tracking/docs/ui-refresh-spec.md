# Spec: Responsive portfolio workspace refresh

## Objective

Refresh the authenticated Personal Stock Tracking interface so a private Vietnam investor can scan portfolio state and complete common actions comfortably on phones, tablets, laptops, and desktop screens. Preserve the existing VND-only, `.VN`-only, secure-ledger behavior while improving information hierarchy, navigation, loading feedback, accessibility, and touch ergonomics.

## Tech stack and commands

- Next.js App Router, React 19, strict TypeScript, CSS custom properties, and Lucide icons.
- Reuse the existing component and token system; add no dependency.
- Verify with `npm run test:run`, `npm run lint`, and `npm run build`.
- Inspect the running app at 320px, 768px, 1024px, and 1440px widths.

## Project structure and style

- `src/components/app-shell.tsx`: shared navigation and page frame.
- `src/features/*`: page-specific content and loading states.
- `src/styles/tokens.css`: semantic design tokens.
- `src/styles/app.css`: responsive layout and component presentation.
- Tests remain colocated with their components or features.

Use a restrained navy, blue, and neutral fintech palette; semantic tokens; one page-level heading; tabular numerals for financial values; consistent spacing/radii; and native interactive elements. Avoid decorative gradients, oversized cards, hidden data states, and color-only status signals.

## Testing strategy

- Component tests prove navigation state, skip navigation, and honest loading behavior.
- Existing domain and persistence tests protect portfolio behavior and Supabase contracts.
- Browser checks cover overflow, layout, readable text, visible focus, and touch targets at the target widths.

## Boundaries

- Always: preserve VND output, `.VN` validation, current routes, honest unavailable-data labels, keyboard access, and secure persistence behavior.
- Ask first: change the database, API contracts, authentication flow, dependencies, or deployment configuration.
- Never: expose credentials, invent live prices or returns, add trade execution, or replace user portfolio state with visual mock data.

## Success criteria

- Desktop and laptop widths use a stable sidebar and spacious content canvas; phone widths use a compact header and safe-area-aware bottom navigation.
- The shell includes a working skip-to-content link and exposes the active destination to assistive technology.
- Dashboard loading does not briefly claim that the portfolio is empty.
- Cards, forms, holdings, watchlist rows, and activity entries reflow without horizontal page scrolling at 320px, 768px, 1024px, and 1440px.
- Tests, lint, and production build pass; browser inspection shows no application console errors.

## Open questions

- English remains the interface language for this refresh.
- Live quote integration, charts, transaction types beyond buys, and localisation remain separate product slices.
