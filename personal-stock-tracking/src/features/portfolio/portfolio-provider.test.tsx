import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, jest } from '@jest/globals';
import { PortfolioProvider, usePortfolio } from './portfolio-provider';
import { createEmptyPortfolioSnapshot, type PortfolioSnapshot, type PortfolioStore } from './portfolio-store';
import { WatchlistPage } from '../watchlist/watchlist-page';

function snapshot(overrides: Partial<PortfolioSnapshot> = {}): PortfolioSnapshot {
  return { ...createEmptyPortfolioSnapshot(), ...overrides };
}

function storeStub(overrides: Partial<PortfolioStore> = {}): PortfolioStore {
  return {
    load: async () => snapshot(),
    recordCashEntry: jest.fn(async () => undefined),
    updateCashEntry: jest.fn(async () => undefined),
    deleteCashEntry: jest.fn(async () => undefined),
    recordTrade: jest.fn(async () => undefined),
    updateTrade: jest.fn(async () => undefined),
    deleteTrade: jest.fn(async () => undefined),
    addWatchlistSymbol: jest.fn(async () => undefined),
    requestAnalysis: jest.fn(async () => undefined),
    ...overrides
  };
}

function ProviderProbe() {
  const portfolio = usePortfolio();
  return (
    <div>
      <span>Ví {portfolio.wallet.availableCashVnd}</span>
      <span>Tài sản {portfolio.totalAssetsVnd ?? 'chưa đủ'}</span>
      <span>Thiếu {portfolio.missingQuoteSymbols.join(',') || 'không'}</span>
      <button type="button" onClick={() => void portfolio.recordCashEntry({ type: 'deposit', amountVnd: 1000000, occurredAt: '2026-07-16T01:00:00Z' })}>Nạp thử</button>
    </div>
  );
}

describe('PortfolioProvider', () => {
  it('refreshes an in-progress analysis run until the workflow callback completes it', async () => {
    jest.useFakeTimers();
    const dispatchedSnapshot = snapshot({
      watchlistSymbols: ['VNM.VN'],
      analysisRuns: [{
        id: '9ad2bc4c-4d18-4b7c-8e55-c2764644cba1', symbol: 'VNM.VN', status: 'dispatched',
        requestedAt: '2026-07-16T08:00:00.000Z', completedAt: null, summary: null, errorCode: null,
        currentPriceVnd: null, quoteAsOf: null, quoteSource: null
      }]
    });
    const completedSnapshot = snapshot({
      watchlistSymbols: ['VNM.VN'],
      analysisRuns: [{
        id: '9ad2bc4c-4d18-4b7c-8e55-c2764644cba1', symbol: 'VNM.VN', status: 'succeeded',
        requestedAt: '2026-07-16T08:00:00.000Z', completedAt: '2026-07-16T08:02:00.000Z',
        summary: 'Phân tích chứng khoán Việt Nam đã hoàn tất.', errorCode: null,
        currentPriceVnd: 52000, quoteAsOf: '2026-07-16T08:01:00.000Z', quoteSource: 'realtime:tencent'
      }],
      latestQuotes: { 'VNM.VN': { currentPriceVnd: 52000, asOf: '2026-07-16T08:01:00.000Z', source: 'realtime:tencent' } }
    });
    let loadCount = 0;
    const store = storeStub({
      load: async () => {
        loadCount += 1;
        return loadCount === 1 ? dispatchedSnapshot : completedSnapshot;
      }
    });

    render(<PortfolioProvider store={store}><WatchlistPage /></PortfolioProvider>);

    expect(await screen.findByText('Phân tích: Đã gửi')).toBeInTheDocument();
    await act(async () => { await jest.advanceTimersByTimeAsync(10_000); });
    await waitFor(() => expect(screen.getByText('Phân tích: Hoàn tất')).toBeInTheDocument());
    expect(screen.getByText('Phân tích chứng khoán Việt Nam đã hoàn tất.')).toBeInTheDocument();
    jest.useRealTimers();
  });

  it('shows a stable zero-VND wallet for a new user and reloads after a successful deposit', async () => {
    let loadCount = 0;
    const funded = snapshot({
      wallet: { currency: 'VND', availableCashVnd: 1000000, createdAt: '2026-07-16T01:00:00Z', updatedAt: '2026-07-16T01:00:00Z' }
    });
    const recordCashEntry = jest.fn<PortfolioStore['recordCashEntry']>(async () => undefined);
    const store = storeStub({
      load: async () => (++loadCount === 1 ? snapshot() : funded),
      recordCashEntry
    });

    render(<PortfolioProvider store={store}><ProviderProbe /></PortfolioProvider>);

    expect(await screen.findByText('Ví 0')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Nạp thử' }));
    expect(await screen.findByText('Ví 1000000')).toBeInTheDocument();
    expect(recordCashEntry).toHaveBeenCalledWith({ type: 'deposit', amountVnd: 1000000, occurredAt: '2026-07-16T01:00:00Z', note: undefined });
  });

  it('derives total assets and reports missing quote symbols without treating them as zero', async () => {
    const positions = [
      { symbol: 'VNM.VN', quantity: 10, averageCostVnd: 50000, totalCostVnd: 500000, positionOpenedAt: '2026-07-16T01:00:00Z' },
      { symbol: 'FPT.VN', quantity: 2, averageCostVnd: 100000, totalCostVnd: 200000, positionOpenedAt: '2026-07-16T01:00:00Z' }
    ];
    const store = storeStub({ load: async () => snapshot({
      wallet: { currency: 'VND', availableCashVnd: 300000, createdAt: null, updatedAt: null },
      positions,
      latestQuotes: { 'VNM.VN': { currentPriceVnd: 52000, asOf: new Date().toISOString(), source: 'realtime:tencent' } }
    }) });

    render(<PortfolioProvider store={store}><ProviderProbe /></PortfolioProvider>);

    expect(await screen.findByText('Tài sản chưa đủ')).toBeInTheDocument();
    expect(screen.getByText('Thiếu FPT.VN')).toBeInTheDocument();
  });

  it('does not expose raw store errors to the user', async () => {
    const store = storeStub({ load: async () => { throw new Error('relation portfolio_wallets does not exist'); } });

    render(<PortfolioProvider store={store}><WatchlistPage /></PortfolioProvider>);

    expect(await screen.findByRole('alert')).toHaveTextContent('Không thể tải dữ liệu danh mục. Vui lòng làm mới và thử lại.');
    expect(screen.queryByText(/portfolio_wallets/)).not.toBeInTheDocument();
  });
});
