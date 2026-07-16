import { render, screen } from '@testing-library/react';
import { describe, expect, it } from '@jest/globals';
import { PortfolioPage } from './portfolio-page';
import { PortfolioProvider } from './portfolio-provider';

describe('PortfolioPage', () => {
  it('shows the dedicated holdings empty state without inventing a market value', () => {
    render(
      <PortfolioProvider store={{
        load: async () => ({ transactions: [], watchlistSymbols: [], analysisRuns: [] }),
        addBuyTransaction: async () => undefined,
        addWatchlistSymbol: async () => undefined,
        requestAnalysis: async () => undefined
      }}>
        <PortfolioPage />
      </PortfolioProvider>
    );

    expect(screen.getByRole('heading', { name: 'Các khoản nắm giữ' })).toBeInTheDocument();
    expect(screen.getByText('Chưa có khoản nắm giữ')).toBeInTheDocument();
    expect(screen.getByText('Chưa có giá trị thị trường')).toBeInTheDocument();
  });
});
