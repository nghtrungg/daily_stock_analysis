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
        summary: 'GitHub Actions completed the requested Vietnam stock analysis.',
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

    expect(await screen.findByText('Analysis: dispatched')).toBeInTheDocument();

    await act(async () => {
      await jest.advanceTimersByTimeAsync(10_000);
    });

    await waitFor(() => expect(screen.getByText('Analysis: succeeded')).toBeInTheDocument());
    expect(screen.getByText('GitHub Actions completed the requested Vietnam stock analysis.')).toBeInTheDocument();
    jest.useRealTimers();
  });
});
