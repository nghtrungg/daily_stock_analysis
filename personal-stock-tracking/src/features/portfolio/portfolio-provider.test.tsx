import { act, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, jest } from '@jest/globals';
import { PortfolioProvider } from './portfolio-provider';
import type { PortfolioSnapshot, PortfolioStore } from './portfolio-store';
import { WatchlistPage } from '../watchlist/watchlist-page';

describe('PortfolioProvider', () => {
  it('refreshes an in-progress analysis run until the workflow callback completes it', async () => {
    jest.useFakeTimers();
    const dispatchedSnapshot: PortfolioSnapshot = {
      transactions: [],
      watchlistSymbols: ['VNM.VN'],
      analysisRuns: [{
        id: '9ad2bc4c-4d18-4b7c-8e55-c2764644cba1',
        symbol: 'VNM.VN',
        status: 'dispatched',
        requestedAt: '2026-07-16T08:00:00.000Z',
        completedAt: null,
        summary: null,
        errorCode: null
      }]
    };
    const completedSnapshot: PortfolioSnapshot = {
      transactions: [],
      watchlistSymbols: ['VNM.VN'],
      analysisRuns: [{
        id: '9ad2bc4c-4d18-4b7c-8e55-c2764644cba1',
        symbol: 'VNM.VN',
        status: 'succeeded',
        requestedAt: '2026-07-16T08:00:00.000Z',
        completedAt: '2026-07-16T08:02:00.000Z',
        summary: 'Phân tích chứng khoán Việt Nam đã hoàn tất.',
        errorCode: null
      }]
    };
    let loadCount = 0;
    const store: PortfolioStore = {
      load: async () => {
        loadCount += 1;
        return loadCount === 1 ? dispatchedSnapshot : completedSnapshot;
      },
      addBuyTransaction: jest.fn(async () => undefined),
      addWatchlistSymbol: jest.fn(async () => undefined),
      requestAnalysis: jest.fn(async () => undefined)
    };

    render(
      <PortfolioProvider store={store}>
        <WatchlistPage />
      </PortfolioProvider>
    );

    expect(await screen.findByText('Phân tích: Đã gửi')).toBeInTheDocument();

    await act(async () => {
      await jest.advanceTimersByTimeAsync(10_000);
    });

    await waitFor(() => expect(screen.getByText('Phân tích: Hoàn tất')).toBeInTheDocument());
    expect(screen.getByText('Phân tích chứng khoán Việt Nam đã hoàn tất.')).toBeInTheDocument();
    jest.useRealTimers();
  });

  it('does not expose raw store errors to the user', async () => {
    const store: PortfolioStore = {
      load: async () => { throw new Error('relation portfolio_wallets does not exist'); },
      addBuyTransaction: jest.fn(async () => undefined),
      addWatchlistSymbol: jest.fn(async () => undefined),
      requestAnalysis: jest.fn(async () => undefined)
    };

    render(
      <PortfolioProvider store={store}>
        <WatchlistPage />
      </PortfolioProvider>
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('Không thể tải dữ liệu danh mục. Vui lòng làm mới và thử lại.');
    expect(screen.queryByText(/portfolio_wallets/)).not.toBeInTheDocument();
  });
});
