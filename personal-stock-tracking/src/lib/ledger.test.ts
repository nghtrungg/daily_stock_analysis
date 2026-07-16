import { describe, expect, it } from '@jest/globals';
import { LedgerInvariantError, replayLedger, type CashEntry, type LedgerTrade } from './ledger';

const deposit: CashEntry = {
  id: 'cash-1',
  type: 'deposit',
  amountVnd: 2_000_000,
  note: 'Nạp vốn',
  occurredAt: '2026-07-01T08:00:00+07:00',
  createdAt: '2026-07-01T08:00:01+07:00',
  updatedAt: '2026-07-01T08:00:01+07:00'
};

function trade(overrides: Partial<LedgerTrade> = {}): LedgerTrade {
  return {
    id: 'trade-1',
    type: 'buy',
    symbol: 'VNM.VN',
    quantity: 10,
    unitPriceVnd: 50_000,
    feeVnd: 1_000,
    taxVnd: 0,
    occurredAt: '2026-07-01T09:00:00+07:00',
    createdAt: '2026-07-01T09:00:01+07:00',
    updatedAt: '2026-07-01T09:00:01+07:00',
    ...overrides
  };
}

describe('replayLedger', () => {
  it('debits buys, includes buy fees in weighted-average cost, and preserves wallet cash', () => {
    const result = replayLedger([deposit], [
      trade(),
      trade({ id: 'trade-2', quantity: 10, unitPriceVnd: 60_000, occurredAt: '2026-07-02T09:00:00+07:00', createdAt: '2026-07-02T09:00:01+07:00' })
    ]);

    expect(result.availableCashVnd).toBe(898_000);
    expect(result.positions).toEqual([expect.objectContaining({
      symbol: 'VNM.VN', quantity: 20, averageCostVnd: 55_100, totalCostVnd: 1_102_000
    })]);
  });

  it('credits net sell proceeds and calculates realized profit using cost basis before sale', () => {
    const result = replayLedger([deposit], [
      trade(),
      trade({ id: 'trade-2', type: 'sell', quantity: 4, unitPriceVnd: 70_000, feeVnd: 1_000, taxVnd: 280, occurredAt: '2026-07-02T09:00:00+07:00', createdAt: '2026-07-02T09:00:01+07:00' })
    ]);

    expect(result.availableCashVnd).toBe(1_777_720);
    expect(result.positions[0]).toEqual(expect.objectContaining({ quantity: 6, totalCostVnd: 300_600 }));
    expect(result.realizedSales[0]).toEqual(expect.objectContaining({
      netProceedsVnd: 278_720,
      removedCostBasisVnd: 200_400,
      realizedProfitLossVnd: 78_320
    }));
  });

  it('rejects any replay point that would make wallet cash negative', () => {
    expect(() => replayLedger([], [trade()])).toThrow(LedgerInvariantError);

    try {
      replayLedger([], [trade()]);
    } catch (error) {
      expect(error).toMatchObject({ code: 'INSUFFICIENT_CASH', eventId: 'trade-1' });
    }
  });

  it('rejects overselling and removes a fully closed position while retaining the realized sale', () => {
    const laterSale = { occurredAt: '2026-07-02T09:00:00+07:00', createdAt: '2026-07-02T09:00:01+07:00' };
    expect(() => replayLedger([deposit], [trade(), trade({ id: 'sell-too-many', type: 'sell', quantity: 11, ...laterSale })]))
      .toThrow('INSUFFICIENT_SHARES');

    const closed = replayLedger([deposit], [trade(), trade({ id: 'sell-all', type: 'sell', quantity: 10, unitPriceVnd: 55_000, ...laterSale })]);
    expect(closed.positions).toEqual([]);
    expect(closed.realizedSales).toHaveLength(1);
  });

  it('orders tied events by occurred_at, created_at, then id', () => {
    const sameTime = '2026-07-01T09:00:00+07:00';
    const result = replayLedger([
      { ...deposit, id: 'cash-b', occurredAt: sameTime, createdAt: '2026-07-01T08:00:02+07:00', amountVnd: 100_000 },
      { ...deposit, id: 'cash-a', occurredAt: sameTime, createdAt: '2026-07-01T08:00:01+07:00', amountVnd: 500_000 }
    ], [trade({ occurredAt: sameTime, createdAt: '2026-07-01T08:00:03+07:00' })]);

    expect(result.events.map((event) => event.id)).toEqual(['cash-a', 'cash-b', 'trade-1']);
  });
});
