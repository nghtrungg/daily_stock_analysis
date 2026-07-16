import { render, screen } from '@testing-library/react';
import { describe, expect, it, jest } from '@jest/globals';
import { PortfolioPage } from './portfolio-page';
import { PortfolioProvider } from './portfolio-provider';
import { createEmptyPortfolioSnapshot, type PortfolioSnapshot, type PortfolioStore } from './portfolio-store';

function storeWith(snapshot: PortfolioSnapshot): PortfolioStore {
  return {
    load: async () => snapshot,
    recordCashEntry: jest.fn(async () => undefined), updateCashEntry: jest.fn(async () => undefined), deleteCashEntry: jest.fn(async () => undefined),
    recordTrade: jest.fn(async () => undefined), updateTrade: jest.fn(async () => undefined), deleteTrade: jest.fn(async () => undefined),
    addWatchlistSymbol: jest.fn(async () => undefined), requestAnalysis: jest.fn(async () => undefined)
  };
}

describe('PortfolioPage', () => {
  it('shows the dedicated holdings empty state without inventing a market value', async () => {
    render(<PortfolioProvider store={storeWith(createEmptyPortfolioSnapshot())}><PortfolioPage /></PortfolioProvider>);

    expect(screen.getByRole('heading', { name: 'Các khoản nắm giữ' })).toBeInTheDocument();
    expect(await screen.findByText('Chưa có khoản nắm giữ')).toBeInTheDocument();
    expect(screen.getAllByText(/0\s*₫/).length).toBeGreaterThan(0);
  });

  it('renders the same quote-backed value, provenance, and accessible profit state as the provider', async () => {
    const base = createEmptyPortfolioSnapshot();
    const quoteTime = new Date().toISOString();
    const valueSnapshot: PortfolioSnapshot = {
      ...base,
      wallet: { currency: 'VND', availableCashVnd: 300000, createdAt: null, updatedAt: null },
      positions: [{ symbol: 'VNM.VN', quantity: 10, averageCostVnd: 50000, totalCostVnd: 500000, positionOpenedAt: '2026-07-16T01:00:00Z' }],
      latestQuotes: { 'VNM.VN': { currentPriceVnd: 52000, asOf: quoteTime, source: 'realtime:tencent' } }
    };

    render(<PortfolioProvider store={storeWith(valueSnapshot)}><PortfolioPage /></PortfolioProvider>);

    expect(await screen.findByText('VNM.VN')).toBeInTheDocument();
    expect(screen.getAllByText(/520\.000/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Lãi.*20\.000.*4/)).toBeInTheDocument();
    expect(screen.getByText(/Nguồn realtime:tencent/)).toBeInTheDocument();
    expect(screen.getByText('Giá: Mới')).toBeInTheDocument();
  });
});
