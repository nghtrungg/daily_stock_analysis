import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from '@jest/globals';
import { DashboardPage } from './dashboard-page';
import { PortfolioProvider } from '../portfolio/portfolio-provider';

function renderDashboard() {
  let transactions: Array<{
    id: string;
    type: 'buy';
    symbol: string;
    quantity: number;
    unitPriceVnd: number;
    feeVnd: number;
    occurredAt: string;
  }> = [];

  const store = {
    load: async () => ({ transactions, watchlistSymbols: [], analysisRuns: [] }),
    addBuyTransaction: async (input: { symbol: string; quantity: number; unitPriceVnd: number; feeVnd: number }) => {
      transactions = [{ id: 'transaction-1', type: 'buy', occurredAt: '2026-07-15T00:00:00.000Z', ...input }];
    },
    addWatchlistSymbol: async () => undefined,
    requestAnalysis: async () => undefined
  };

  return render(
    <PortfolioProvider store={store}>
      <DashboardPage />
    </PortfolioProvider>
  );
}

describe('DashboardPage', () => {
  it('shows a loading state before deciding that the portfolio is empty', () => {
    const store = {
      load: () => new Promise<never>(() => undefined),
      addBuyTransaction: async () => undefined,
      addWatchlistSymbol: async () => undefined,
      requestAnalysis: async () => undefined
    };

    render(
      <PortfolioProvider store={store}>
        <DashboardPage />
      </PortfolioProvider>
    );

    expect(screen.getByRole('status', { name: 'Loading portfolio' })).toBeInTheDocument();
    expect(screen.queryByText('No holdings yet')).not.toBeInTheDocument();
  });

  it('explains the empty portfolio without presenting price or analysis data as available', async () => {
    renderDashboard();

    expect(screen.getByRole('heading', { name: 'Portfolio at a glance' })).toBeInTheDocument();
    expect(await screen.findByText('No holdings yet')).toBeInTheDocument();
    expect(screen.getByText('Quote: Missing')).toBeInTheDocument();
    expect(screen.getByText('Analysis: Never analysed')).toBeInTheDocument();
  });

  it('uses real application routes for every bottom-navigation destination', () => {
    renderDashboard();

    expect(screen.getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'Portfolio' })).toHaveAttribute('href', '/portfolio');
    expect(screen.getByRole('link', { name: 'Watchlist' })).toHaveAttribute('href', '/watchlist');
    expect(screen.getByRole('link', { name: 'Activity' })).toHaveAttribute('href', '/activity');
    expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute('href', '/settings');
  });

  it('adds a valid buy transaction and derives the holding locally', async () => {
    renderDashboard();

    fireEvent.click(screen.getAllByRole('button', { name: 'Add transaction' })[0]);
    fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'vnm.vn' } });
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '10' } });
    fireEvent.change(screen.getByLabelText('Unit price (VND)'), { target: { value: '50000' } });
    fireEvent.change(screen.getByLabelText('Fees (VND)'), { target: { value: '1000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save transaction' }));

    expect(await screen.findByText('VNM.VN')).toBeInTheDocument();
    expect(screen.getByText(/10 shares/)).toBeInTheDocument();
    expect(screen.getByText(/50\.100/)).toBeInTheDocument();
  });
});
