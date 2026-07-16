import { describe, expect, it, jest } from '@jest/globals';
import { createSupabasePortfolioStore } from './portfolio-store';

function queryResult(data: unknown) {
  return {
    select: jest.fn(() => ({
      order: jest.fn(async () => ({ data, error: null })),
      limit: jest.fn(() => ({ maybeSingle: jest.fn(async () => ({ data, error: null })) }))
    }))
  };
}

describe('Supabase portfolio store', () => {
  it('normalizes one complete owner ledger snapshot and keeps the newest valid quote per symbol', async () => {
    const rows = {
      portfolio_wallets: { user_id: 'owner', currency: 'VND', available_cash_vnd: '499000', created_at: '2026-07-16T01:00:00Z', updated_at: '2026-07-16T02:00:00Z' },
      portfolio_cash_entries: [{ id: 'cash-1', entry_type: 'deposit', amount_vnd: '1000000', note: 'Nạp vốn', occurred_at: '2026-07-16T01:00:00Z', created_at: '2026-07-16T01:00:00Z', updated_at: '2026-07-16T01:00:00Z' }],
      portfolio_transactions: [{ id: 'trade-1', transaction_type: 'buy', symbol: 'VNM.VN', quantity: '10', unit_price_vnd: '50000', fee_vnd: '1000', tax_vnd: '0', occurred_at: '2026-07-16T02:00:00Z', created_at: '2026-07-16T02:00:00Z', updated_at: '2026-07-16T02:00:00Z' }],
      watchlist_symbols: [{ symbol: 'VNM.VN' }],
      analysis_runs: [
        { id: 'run-new', symbol: 'VNM.VN', status: 'succeeded', requested_at: '2026-07-16T03:00:00Z', completed_at: '2026-07-16T03:02:00Z', summary: 'Mới', error_code: null, current_price_vnd: '52000', quote_as_of: '2026-07-16T03:01:00Z', quote_source: 'realtime:tencent' },
        { id: 'run-partial', symbol: 'FPT.VN', status: 'succeeded', requested_at: '2026-07-16T03:00:00Z', completed_at: '2026-07-16T03:02:00Z', summary: 'Thiếu nguồn', error_code: null, current_price_vnd: '110000', quote_as_of: null, quote_source: null },
        { id: 'run-old', symbol: 'VNM.VN', status: 'succeeded', requested_at: '2026-07-15T03:00:00Z', completed_at: '2026-07-15T03:02:00Z', summary: 'Cũ', error_code: null, current_price_vnd: '51000', quote_as_of: '2026-07-15T03:01:00Z', quote_source: 'realtime:tencent' }
      ]
    } as const;
    const from = jest.fn((table: keyof typeof rows) => queryResult(rows[table]));
    const snapshot = await createSupabasePortfolioStore({ from, rpc: jest.fn(), functions: { invoke: jest.fn() } } as never).load();

    expect(snapshot.wallet.availableCashVnd).toBe(499000);
    expect(snapshot.cashEntries[0]).toEqual(expect.objectContaining({ type: 'deposit', amountVnd: 1000000 }));
    expect(snapshot.transactions[0]).toEqual(expect.objectContaining({ type: 'buy', taxVnd: 0, updatedAt: '2026-07-16T02:00:00Z' }));
    expect(snapshot.positions[0]).toEqual(expect.objectContaining({ symbol: 'VNM.VN', quantity: 10, totalCostVnd: 501000 }));
    expect(snapshot.latestQuotes).toEqual({
      'VNM.VN': { currentPriceVnd: 52000, asOf: '2026-07-16T03:01:00Z', source: 'realtime:tencent' }
    });
    expect(snapshot.latestQuotes['FPT.VN']).toBeUndefined();
  });

  it('uses RPCs for every financial mutation and never writes a financial table directly', async () => {
    const rpc = jest.fn<(name: string, parameters: Record<string, unknown>) => Promise<{ data: object; error: null }>>(async () => ({ data: {}, error: null }));
    const from = jest.fn(() => { throw new Error('direct table mutation is forbidden'); });
    const store = createSupabasePortfolioStore({ from, rpc, functions: { invoke: jest.fn() } } as never);

    await store.recordCashEntry({ type: 'deposit', amountVnd: 1000000, occurredAt: '2026-07-16T01:00:00Z', note: ' Nạp vốn ' });
    await store.recordTrade({ type: 'sell', symbol: 'VNM.VN', quantity: 2.5, unitPriceVnd: 52000, feeVnd: 1000, taxVnd: 500, occurredAt: '2026-07-16T02:00:00Z' });
    await store.updateCashEntry({ id: 'cash-1', expectedUpdatedAt: '2026-07-16T01:00:00Z', type: 'withdrawal', amountVnd: 1000, occurredAt: '2026-07-16T01:30:00Z', note: '' });
    await store.deleteCashEntry('cash-1', '2026-07-16T01:30:00Z');
    await store.updateTrade({ id: 'trade-1', expectedUpdatedAt: '2026-07-16T02:00:00Z', type: 'buy', symbol: 'VNM.VN', quantity: 3, unitPriceVnd: 50000, feeVnd: 0, taxVnd: 0, occurredAt: '2026-07-16T02:30:00Z' });
    await store.deleteTrade('trade-1', '2026-07-16T02:30:00Z');

    expect(from).not.toHaveBeenCalled();
    expect(rpc.mock.calls.map(([name]) => name)).toEqual([
      'record_cash_entry',
      'record_portfolio_trade',
      'update_cash_entry',
      'delete_cash_entry',
      'update_portfolio_trade',
      'delete_portfolio_trade'
    ]);
    expect(rpc).toHaveBeenCalledWith('record_portfolio_trade', expect.objectContaining({
      p_transaction_type: 'sell', p_symbol: 'VNM.VN', p_quantity: 2.5, p_tax_vnd: 500
    }));
    expect(rpc).toHaveBeenCalledWith('update_cash_entry', expect.objectContaining({
      p_expected_updated_at: '2026-07-16T01:00:00Z', p_note: null
    }));
  });

  it('maps stable invariant and concurrency codes to actionable Vietnamese errors', async () => {
    const rpc = jest.fn<(name: string, parameters: Record<string, unknown>) => Promise<{ data: null; error: { message: string } }>>(async () => ({ data: null, error: { message: 'P0001: STALE_ENTRY' } }));
    await expect(createSupabasePortfolioStore({ from: jest.fn(), rpc, functions: { invoke: jest.fn() } } as never).deleteTrade('trade-1', '2026-07-16T02:00:00Z'))
      .rejects.toEqual(expect.objectContaining({
        message: 'Bút toán đã được thay đổi ở nơi khác. Hãy tải lại trước khi chỉnh sửa.'
      }));
  });
});
