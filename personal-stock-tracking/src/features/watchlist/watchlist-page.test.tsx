import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, jest } from '@jest/globals';
import { PortfolioProvider } from '../portfolio/portfolio-provider';
import { createEmptyPortfolioSnapshot, type PortfolioStore } from '../portfolio/portfolio-store';
import { WatchlistPage } from './watchlist-page';

function storeWith(symbols: string[], requestAnalysis: PortfolioStore['requestAnalysis']): PortfolioStore {
  return {
    load: jest.fn(async () => ({ ...createEmptyPortfolioSnapshot(), watchlistSymbols: symbols })),
    recordCashEntry: jest.fn(async () => undefined), updateCashEntry: jest.fn(async () => undefined), deleteCashEntry: jest.fn(async () => undefined),
    recordTrade: jest.fn(async () => undefined), updateTrade: jest.fn(async () => undefined), deleteTrade: jest.fn(async () => undefined),
    addWatchlistSymbol: jest.fn(async () => undefined), requestAnalysis
  };
}

describe('WatchlistPage', () => {
  it('requests analysis through the persisted store for a watched Vietnam symbol', async () => {
    const store = storeWith(['VNM.VN'], jest.fn(async (symbol: string) => {
        void symbol;
      }));

    render(
      <PortfolioProvider store={store}>
        <WatchlistPage />
      </PortfolioProvider>
    );

    const analyzeButton = await screen.findByRole('button', { name: 'Phân tích' });
    expect(analyzeButton).toBeEnabled();

    fireEvent.click(analyzeButton);

    await waitFor(() => expect(store.requestAnalysis).toHaveBeenCalledWith('VNM.VN'));
  });

  it('only marks the selected symbol as requesting analysis', async () => {
    let resolveAnalysis: (() => void) | undefined;
    const store = storeWith(['VNM.VN', 'FPT.VN'], jest.fn(() => new Promise<void>((resolve) => { resolveAnalysis = resolve; })));

    render(
      <PortfolioProvider store={store}>
        <WatchlistPage />
      </PortfolioProvider>
    );

    const analyzeButtons = await screen.findAllByRole('button', { name: 'Phân tích' });
    fireEvent.click(analyzeButtons[0]);

    expect(await screen.findByRole('button', { name: 'Đang gửi yêu cầu…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Phân tích' })).toBeEnabled();

    await act(async () => resolveAnalysis?.());
  });
});
