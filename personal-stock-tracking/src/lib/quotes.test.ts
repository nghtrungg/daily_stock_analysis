import { describe, expect, it } from '@jest/globals';
import { QUOTE_STALE_AFTER_MS, isQuoteStale, valuePortfolio, type Quote } from './quotes';
import type { LedgerPosition } from './ledger';

const position: LedgerPosition = {
  symbol: 'VNM.VN',
  quantity: 10,
  averageCostVnd: 50_100,
  totalCostVnd: 501_000,
  positionOpenedAt: '2026-07-01T09:00:00+07:00'
};

const quote: Quote = {
  currentPriceVnd: 60_000,
  asOf: '2026-07-16T15:00:00+07:00',
  source: 'configured-market-provider'
};

describe('quote valuation', () => {
  it('marks a quote stale only after the tested 30-minute threshold', () => {
    const asOf = Date.parse(quote.asOf);
    expect(QUOTE_STALE_AFTER_MS).toBe(30 * 60 * 1000);
    expect(isQuoteStale(quote, new Date(asOf + QUOTE_STALE_AFTER_MS))).toBe(false);
    expect(isQuoteStale(quote, new Date(asOf + QUOTE_STALE_AFTER_MS + 1))).toBe(true);
  });

  it('calculates market value and unrealized profit for a quoted position', () => {
    const result = valuePortfolio(100_000, [position], { 'VNM.VN': quote }, new Date('2026-07-16T15:10:00+07:00'));

    expect(result.positions[0]).toEqual(expect.objectContaining({
      quoteState: 'fresh',
      marketValueVnd: 600_000,
      unrealizedProfitLossVnd: 99_000,
      unrealizedProfitLossPercent: expect.closeTo(19.7604, 3)
    }));
    expect(result.marketValueVnd).toBe(600_000);
    expect(result.totalAssetsVnd).toBe(700_000);
  });

  it('uses stale quotes for a labeled estimate but never treats a missing quote as zero', () => {
    const fpt = { ...position, symbol: 'FPT.VN', totalCostVnd: 400_000 };
    const staleResult = valuePortfolio(100_000, [position], { 'VNM.VN': quote }, new Date('2026-07-16T16:00:01+07:00'));
    expect(staleResult.positions[0].quoteState).toBe('stale');
    expect(staleResult.marketValueVnd).toBe(600_000);

    const incomplete = valuePortfolio(100_000, [position, fpt], { 'VNM.VN': quote }, new Date('2026-07-16T15:10:00+07:00'));
    expect(incomplete.positions[1]).toEqual(expect.objectContaining({ quoteState: 'missing', marketValueVnd: null }));
    expect(incomplete.missingSymbols).toEqual(['FPT.VN']);
    expect(incomplete.knownMarketValueVnd).toBe(600_000);
    expect(incomplete.marketValueVnd).toBeNull();
    expect(incomplete.totalAssetsVnd).toBeNull();
  });
});
