import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from '@jest/globals';
import { replayLedger, type CashEntry, type LedgerTrade } from '../../lib/ledger';
import { DashboardPage } from './dashboard-page';
import { PortfolioProvider } from '../portfolio/portfolio-provider';
import { createEmptyPortfolioSnapshot, type PortfolioStore } from '../portfolio/portfolio-store';

function createDashboardStore({ funded = false, withHolding = false } = {}): PortfolioStore {
  const cashEntries: CashEntry[] = funded || withHolding ? [{
    id: 'cash-1', type: 'deposit', amountVnd: 1000000, note: 'Vốn thử nghiệm',
    occurredAt: '2026-07-15T01:00:00.000Z', createdAt: '2026-07-15T01:00:00.000Z', updatedAt: '2026-07-15T01:00:00.000Z'
  }] : [];
  const transactions: LedgerTrade[] = withHolding ? [{
    id: 'trade-1', type: 'buy', symbol: 'VNM.VN', quantity: 10, unitPriceVnd: 50000, feeVnd: 0, taxVnd: 0,
    occurredAt: '2026-07-15T02:00:00.000Z', createdAt: '2026-07-15T02:00:00.000Z', updatedAt: '2026-07-15T02:00:00.000Z'
  }] : [];
  let cashId = 1;
  let tradeId = 1;

  function load() {
    const ledger = replayLedger(cashEntries, transactions);
    return Promise.resolve({
      ...createEmptyPortfolioSnapshot(),
      wallet: { currency: 'VND' as const, availableCashVnd: ledger.availableCashVnd, createdAt: null, updatedAt: null },
      cashEntries: [...cashEntries],
      transactions: [...transactions],
      positions: ledger.positions,
      realizedSales: ledger.realizedSales,
      ledgerEvents: ledger.events
    });
  }

  return {
    load,
    recordCashEntry: async (input) => {
      cashId += 1;
      cashEntries.push({ id: `cash-${cashId}`, ...input, note: input.note, createdAt: input.occurredAt, updatedAt: input.occurredAt });
    },
    updateCashEntry: async () => undefined,
    deleteCashEntry: async () => undefined,
    recordTrade: async (input) => {
      tradeId += 1;
      transactions.push({ id: `trade-${tradeId}`, ...input, createdAt: input.occurredAt, updatedAt: input.occurredAt });
    },
    updateTrade: async () => undefined,
    deleteTrade: async () => undefined,
    addWatchlistSymbol: async () => undefined,
    requestAnalysis: async () => undefined
  };
}

function renderDashboard(options?: { funded?: boolean; withHolding?: boolean }) {
  return render(<PortfolioProvider store={createDashboardStore(options)}><DashboardPage /></PortfolioProvider>);
}

describe('DashboardPage', () => {
  it('shows a loading state before deciding that the portfolio is empty', () => {
    const store: PortfolioStore = {
      ...createDashboardStore(),
      load: () => new Promise<never>(() => undefined)
    };
    render(<PortfolioProvider store={store}><DashboardPage /></PortfolioProvider>);

    expect(screen.getByRole('status', { name: 'Đang tải danh mục' })).toBeInTheDocument();
    expect(screen.queryByText('Chưa có khoản nắm giữ')).not.toBeInTheDocument();
  });

  it('guides a new user to deposit before buying and keeps all navigation routes real', async () => {
    renderDashboard();

    expect(await screen.findByText('Chưa có khoản nắm giữ')).toBeInTheDocument();
    expect(screen.getByText('Hãy nạp tiền vào sổ trước khi ghi giao dịch mua.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ghi giao dịch mua' })).toBeDisabled();
    expect(screen.getByRole('link', { name: 'Trang chủ' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'Danh mục' })).toHaveAttribute('href', '/portfolio');
    expect(screen.getByRole('link', { name: 'Lịch sử' })).toHaveAttribute('href', '/activity');
  });

  it('records a deposit and then a wallet-backed buy without a page refresh', async () => {
    renderDashboard();

    fireEvent.change(screen.getByLabelText('Số tiền (VND)'), { target: { value: '1000000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ghi bút toán ví' }));
    expect(await screen.findByText('Đã ghi nhận khoản nạp tiền.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Ghi giao dịch' }));
    const tradeDialog = screen.getByRole('dialog');
    fireEvent.change(within(tradeDialog).getByLabelText('Mã chứng khoán'), { target: { value: 'vnm.vn' } });
    fireEvent.change(within(tradeDialog).getByLabelText('Khối lượng'), { target: { value: '10' } });
    fireEvent.change(within(tradeDialog).getByLabelText('Đơn giá (VND)'), { target: { value: '50000' } });
    fireEvent.change(within(tradeDialog).getByLabelText('Phí (VND)'), { target: { value: '1000' } });
    expect(within(tradeDialog).getByText(/Tổng chi.*501\.000/)).toBeInTheDocument();
    fireEvent.click(within(tradeDialog).getByRole('button', { name: 'Ghi giao dịch mua' }));

    expect(await screen.findByText('VNM.VN')).toBeInTheDocument();
    expect(screen.getByText(/10 cổ phiếu/)).toBeInTheDocument();
    expect(screen.getByText(/50\.100/)).toBeInTheDocument();
  });

  it('prefills a holding sale and previews exact net wallet proceeds', async () => {
    renderDashboard({ withHolding: true });

    expect(await screen.findByText('VNM.VN')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Bán' }));
    const tradeDialog = screen.getByRole('dialog');
    expect(within(tradeDialog).getByLabelText('Mã chứng khoán')).toHaveValue('VNM.VN');
    expect(within(tradeDialog).getByLabelText('Khối lượng')).toHaveValue(10);
    fireEvent.change(within(tradeDialog).getByLabelText('Khối lượng'), { target: { value: '5' } });
    fireEvent.change(within(tradeDialog).getByLabelText('Đơn giá (VND)'), { target: { value: '60000' } });
    fireEvent.change(within(tradeDialog).getByLabelText('Phí (VND)'), { target: { value: '1000' } });
    fireEvent.change(within(tradeDialog).getByLabelText('Thuế (VND)'), { target: { value: '500' } });

    expect(within(tradeDialog).getByText(/Thu ròng.*298\.500/)).toBeInTheDocument();
    expect(within(tradeDialog).getByText(/Sau bán còn tối đa 5 cổ phiếu/)).toBeInTheDocument();
  });
});
