import { render, screen } from '@testing-library/react';
import { describe, expect, it } from '@jest/globals';
import { AppShell } from './app-shell';

describe('AppShell', () => {
  it('provides skip navigation and exposes the active destination', () => {
    render(
      <AppShell activePath="/watchlist">
        <h1>Theo dõi</h1>
      </AppShell>
    );

    expect(screen.getByRole('link', { name: 'Bỏ qua để đến nội dung danh mục' })).toHaveAttribute('href', '#main-content');
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content');
    expect(screen.getByRole('link', { name: 'Theo dõi' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('navigation', { name: 'Điều hướng chính' })).toBeInTheDocument();
  });
});
