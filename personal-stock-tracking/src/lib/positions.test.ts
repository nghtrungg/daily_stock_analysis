import { describe, expect, it } from '@jest/globals';
import { derivePositions } from './positions';

describe('derivePositions', () => {
  it('calculates a weighted-average cost including buy fees', () => {
    const positions = derivePositions([
      { id: 'buy-1', type: 'buy', symbol: 'VNM.VN', quantity: 10, unitPriceVnd: 50000, feeVnd: 1000, occurredAt: '2026-07-01T09:00:00+07:00' },
      { id: 'buy-2', type: 'buy', symbol: 'VNM.VN', quantity: 10, unitPriceVnd: 60000, feeVnd: 1000, occurredAt: '2026-07-02T09:00:00+07:00' }
    ]);

    expect(positions).toEqual([
      expect.objectContaining({
        symbol: 'VNM.VN',
        quantity: 20,
        averageCostVnd: 55100,
        totalCostVnd: 1102000
      })
    ]);
  });

  it('rejects a sell that would make a position negative', () => {
    expect(() => derivePositions([
      { id: 'sell-1', type: 'sell', symbol: 'VNM.VN', quantity: 1, unitPriceVnd: 50000, feeVnd: 0, occurredAt: '2026-07-01T09:00:00+07:00' }
    ])).toThrow('cannot sell more shares than are held');
  });
});
