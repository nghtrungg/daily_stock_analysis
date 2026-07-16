import type { LedgerPosition } from './ledger';

export const QUOTE_STALE_AFTER_MS = 30 * 60 * 1000;

export type Quote = {
  currentPriceVnd: number;
  asOf: string;
  source: string;
};

export type ValuedPosition = LedgerPosition & {
  quote: Quote | null;
  quoteState: 'fresh' | 'stale' | 'missing';
  marketValueVnd: number | null;
  unrealizedProfitLossVnd: number | null;
  unrealizedProfitLossPercent: number | null;
};

function isValidQuote(quote: Quote | undefined): quote is Quote {
  return Boolean(
    quote
    && Number.isSafeInteger(quote.currentPriceVnd)
    && quote.currentPriceVnd > 0
    && !Number.isNaN(Date.parse(quote.asOf))
    && quote.source.trim().length > 0
    && quote.source.length <= 120
  );
}

export function isQuoteStale(quote: Quote, now = new Date()): boolean {
  if (!isValidQuote(quote)) return true;
  return now.getTime() - Date.parse(quote.asOf) > QUOTE_STALE_AFTER_MS;
}

export function valuePortfolio(
  availableCashVnd: number,
  positions: readonly LedgerPosition[],
  quotesBySymbol: Readonly<Record<string, Quote | undefined>>,
  now = new Date()
) {
  const valuedPositions: ValuedPosition[] = positions.map((position) => {
    const quote = quotesBySymbol[position.symbol];
    if (!isValidQuote(quote)) {
      return {
        ...position,
        quote: null,
        quoteState: 'missing' as const,
        marketValueVnd: null,
        unrealizedProfitLossVnd: null,
        unrealizedProfitLossPercent: null
      };
    }

    const marketValueVnd = Math.round(position.quantity * quote.currentPriceVnd);
    const unrealizedProfitLossVnd = marketValueVnd - position.totalCostVnd;
    return {
      ...position,
      quote,
      quoteState: isQuoteStale(quote, now) ? 'stale' as const : 'fresh' as const,
      marketValueVnd,
      unrealizedProfitLossVnd,
      unrealizedProfitLossPercent: position.totalCostVnd > 0 ? unrealizedProfitLossVnd / position.totalCostVnd * 100 : null
    };
  });
  const missingSymbols = valuedPositions.filter((position) => position.quoteState === 'missing').map((position) => position.symbol);
  const knownMarketValueVnd = valuedPositions.reduce((total, position) => total + (position.marketValueVnd ?? 0), 0);
  const isComplete = missingSymbols.length === 0;

  return {
    availableCashVnd,
    positions: valuedPositions,
    knownMarketValueVnd,
    marketValueVnd: isComplete ? knownMarketValueVnd : null,
    totalAssetsVnd: isComplete ? availableCashVnd + knownMarketValueVnd : null,
    missingSymbols,
    isComplete
  };
}
