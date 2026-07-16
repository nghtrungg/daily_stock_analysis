import { render, screen } from '@testing-library/react';
import { describe, expect, it } from '@jest/globals';
import { AppShell } from './app-shell';

describe('AppShell', () => {
  it('provides skip navigation and exposes the active destination', () => {
    render(
      <AppShell activePath="/watchlist">
        <h1>Watchlist</h1>
      </AppShell>
    );

    expect(screen.getByRole('link', { name: 'Skip to portfolio content' })).toHaveAttribute('href', '#main-content');
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content');
    expect(screen.getByRole('link', { name: 'Watchlist' })).toHaveAttribute('aria-current', 'page');
  });
});
