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

    expect(screen.getByRole('status', { name: 'Đang tải danh mục' })).toBeInTheDocument();
    expect(screen.queryByText('Chưa có khoản nắm giữ')).not.toBeInTheDocument();
  });

  it('explains the empty portfolio without presenting price or analysis data as available', async () => {
    renderDashboard();

    expect(screen.getByRole('heading', { name: 'Tổng quan danh mục' })).toBeInTheDocument();
    expect(await screen.findByText('Chưa có khoản nắm giữ')).toBeInTheDocument();
    expect(screen.getByText('Giá: Chưa có')).toBeInTheDocument();
    expect(screen.getByText('Phân tích: Chưa từng phân tích')).toBeInTheDocument();
  });

  it('uses real application routes for every bottom-navigation destination', () => {
    renderDashboard();

    expect(screen.getByRole('link', { name: 'Trang chủ' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'Danh mục' })).toHaveAttribute('href', '/portfolio');
    expect(screen.getByRole('link', { name: 'Theo dõi' })).toHaveAttribute('href', '/watchlist');
    expect(screen.getByRole('link', { name: 'Lịch sử' })).toHaveAttribute('href', '/activity');
    expect(screen.getByRole('link', { name: 'Cài đặt' })).toHaveAttribute('href', '/settings');
  });

  it('adds a valid buy transaction and derives the holding locally', async () => {
    renderDashboard();

    fireEvent.click(screen.getAllByRole('button', { name: 'Ghi giao dịch' })[0]);
    fireEvent.change(screen.getByLabelText('Mã chứng khoán'), { target: { value: 'vnm.vn' } });
    fireEvent.change(screen.getByLabelText('Khối lượng'), { target: { value: '10' } });
    fireEvent.change(screen.getByLabelText('Đơn giá (VND)'), { target: { value: '50000' } });
    fireEvent.change(screen.getByLabelText('Phí (VND)'), { target: { value: '1000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu giao dịch' }));

    expect(await screen.findByText('VNM.VN')).toBeInTheDocument();
    expect(screen.getByText(/10 cổ phiếu/)).toBeInTheDocument();
    expect(screen.getByText(/50\.100/)).toBeInTheDocument();
  });
});
