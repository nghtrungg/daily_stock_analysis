import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, jest } from '@jest/globals';
import { replayLedger, type CashEntry, type LedgerTrade } from '../../lib/ledger';
import { PortfolioProvider } from '../portfolio/portfolio-provider';
import { createEmptyPortfolioSnapshot, PortfolioStoreError, type PortfolioStore } from '../portfolio/portfolio-store';
import { ActivityPage } from './activity-page';

function activityStore(cashEntries: CashEntry[], transactions: LedgerTrade[] = []): PortfolioStore {
  function load() {
    const ledger = replayLedger(cashEntries, transactions);
    return Promise.resolve({
      ...createEmptyPortfolioSnapshot(),
      wallet: { currency: 'VND' as const, availableCashVnd: ledger.availableCashVnd, createdAt: null, updatedAt: null },
      cashEntries: [...cashEntries], transactions: [...transactions], positions: ledger.positions,
      realizedSales: ledger.realizedSales, ledgerEvents: ledger.events
    });
  }
  return {
    load,
    recordCashEntry: jest.fn(async () => undefined),
    updateCashEntry: jest.fn<PortfolioStore['updateCashEntry']>(async (input) => {
      const entry = cashEntries.find((candidate) => candidate.id === input.id)!;
      Object.assign(entry, { type: input.type, amountVnd: input.amountVnd, occurredAt: input.occurredAt, note: input.note, updatedAt: '2026-07-16T09:00:00Z' });
    }),
    deleteCashEntry: jest.fn(async (id) => { cashEntries.splice(cashEntries.findIndex((entry) => entry.id === id), 1); }),
    recordTrade: jest.fn(async () => undefined), updateTrade: jest.fn(async () => undefined), deleteTrade: jest.fn(async () => undefined),
    addWatchlistSymbol: jest.fn(async () => undefined), requestAnalysis: jest.fn(async () => undefined)
  };
}

const deposit: CashEntry = {
  id: 'cash-1', type: 'deposit', amountVnd: 1000000, note: 'Vốn tháng 7',
  occurredAt: '2026-07-16T01:00:00Z', createdAt: '2026-07-16T01:00:00Z', updatedAt: '2026-07-16T01:00:00Z'
};

describe('ActivityPage', () => {
  it('shows cash and trades in deterministic reverse chronology with wallet effects and realized profit', async () => {
    const cashEntries: CashEntry[] = [deposit, {
      id: 'cash-2', type: 'withdrawal', amountVnd: 100000, occurredAt: '2026-07-16T04:00:00Z', createdAt: '2026-07-16T04:00:00Z', updatedAt: '2026-07-16T04:00:00Z'
    }];
    const trades: LedgerTrade[] = [
      { id: 'trade-1', type: 'buy', symbol: 'VNM.VN', quantity: 10, unitPriceVnd: 50000, feeVnd: 0, taxVnd: 0, occurredAt: '2026-07-16T02:00:00Z', createdAt: '2026-07-16T02:00:00Z', updatedAt: '2026-07-16T02:00:00Z' },
      { id: 'trade-2', type: 'sell', symbol: 'VNM.VN', quantity: 5, unitPriceVnd: 60000, feeVnd: 1000, taxVnd: 0, occurredAt: '2026-07-16T03:00:00Z', createdAt: '2026-07-16T03:00:00Z', updatedAt: '2026-07-16T03:00:00Z' }
    ];

    render(<PortfolioProvider store={activityStore(cashEntries, trades)}><ActivityPage /></PortfolioProvider>);

    const items = await screen.findAllByRole('listitem');
    expect(within(items[0]).getByText(/Rút tiền/)).toBeInTheDocument();
    expect(within(items[1]).getByText(/Bán/)).toBeInTheDocument();
    expect(within(items[1]).getByText(/Lãi\/lỗ đã thực hiện:.*49\.000/)).toBeInTheDocument();
    expect(within(items[2]).getByText(/Mua/)).toBeInTheDocument();
    expect(within(items[3]).getByText(/Nạp tiền/)).toBeInTheDocument();
  });

  it('edits a user cash entry, keeps the editor open on rejection, and restores a visible corrected row', async () => {
    const entries = [{ ...deposit }];
    const store = activityStore(entries);
    render(<PortfolioProvider store={store}><ActivityPage /></PortfolioProvider>);

    fireEvent.click(await screen.findByRole('button', { name: 'Chỉnh sửa' }));
    fireEvent.change(screen.getByLabelText('Số tiền (VND)'), { target: { value: '1200000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu chỉnh sửa' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.getByText(/Nạp tiền · Đã chỉnh sửa/)).toBeInTheDocument();
    expect(screen.getAllByText(/1\.200\.000/).length).toBeGreaterThan(0);
  });

  it('does not delete after cancellation and retains entered corrections after an invariant rejection', async () => {
    const entries = [{ ...deposit }];
    const store = activityStore(entries);
    store.updateCashEntry = jest.fn(async () => { throw new PortfolioStoreError('Số dư ví không đủ cho bút toán này.'); });
    const confirm = jest.spyOn(window, 'confirm').mockReturnValue(false);
    render(<PortfolioProvider store={store}><ActivityPage /></PortfolioProvider>);

    fireEvent.click(await screen.findByRole('button', { name: 'Chỉnh sửa' }));
    fireEvent.change(screen.getByLabelText('Số tiền (VND)'), { target: { value: '1500000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Xóa bút toán' }));
    expect(store.deleteCashEntry).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Lưu chỉnh sửa' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Số dư ví không đủ cho bút toán này.');
    expect(screen.getByLabelText('Số tiền (VND)')).toHaveValue(1500000);
    confirm.mockRestore();
  });

  it('shows the migration opening balance but does not offer edit or delete actions', async () => {
    const opening: CashEntry = { ...deposit, id: 'opening-1', type: 'opening_balance', note: 'Số dư đầu kỳ được tạo khi chuyển đổi dữ liệu' };
    render(<PortfolioProvider store={activityStore([opening])}><ActivityPage /></PortfolioProvider>);

    expect((await screen.findAllByText(/Số dư đầu kỳ/)).length).toBeGreaterThan(0);
    expect(screen.getByText(/không thể chỉnh sửa hoặc xóa/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Chỉnh sửa' })).not.toBeInTheDocument();
  });
});
