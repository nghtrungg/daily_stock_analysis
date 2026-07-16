import { requireVietnamSymbol } from './symbols';

export type CashEntryType = 'deposit' | 'withdrawal' | 'opening_balance';

export type CashEntry = {
  id: string;
  type: CashEntryType;
  amountVnd: number;
  note?: string;
  occurredAt: string;
  createdAt: string;
  updatedAt: string;
};

export type LedgerTrade = {
  id: string;
  type: 'buy' | 'sell';
  symbol: string;
  quantity: number;
  unitPriceVnd: number;
  feeVnd: number;
  taxVnd: number;
  occurredAt: string;
  createdAt: string;
  updatedAt: string;
};

export type LedgerPosition = {
  symbol: string;
  quantity: number;
  averageCostVnd: number;
  totalCostVnd: number;
  positionOpenedAt: string;
};

export type RealizedSale = {
  tradeId: string;
  symbol: string;
  quantity: number;
  grossProceedsVnd: number;
  netProceedsVnd: number;
  removedCostBasisVnd: number;
  realizedProfitLossVnd: number;
  occurredAt: string;
};

export type LedgerEvent = {
  id: string;
  kind: 'cash' | 'trade';
  occurredAt: string;
  createdAt: string;
  walletEffectVnd: number;
  walletAfterVnd: number;
};

export type LedgerInvariantCode = 'INSUFFICIENT_CASH' | 'INSUFFICIENT_SHARES';

export class LedgerInvariantError extends Error {
  constructor(public readonly code: LedgerInvariantCode, public readonly eventId: string) {
    super(`${code}: ${eventId}`);
    this.name = 'LedgerInvariantError';
  }
}

type OrderedEvent =
  | { kind: 'cash'; value: CashEntry }
  | { kind: 'trade'; value: LedgerTrade };

function requireTimestamp(value: string, field: string): void {
  if (Number.isNaN(Date.parse(value))) throw new Error(`${field} must be a valid timestamp`);
}

function requireVnd(value: number, field: string, allowZero = false): void {
  if (!Number.isSafeInteger(value) || (allowZero ? value < 0 : value <= 0)) {
    throw new Error(`${field} must be ${allowZero ? 'a non-negative' : 'a positive'} integer VND amount`);
  }
}

function validateSharedEvent(value: CashEntry | LedgerTrade): void {
  if (!value.id) throw new Error('event id is required');
  requireTimestamp(value.occurredAt, 'occurredAt');
  requireTimestamp(value.createdAt, 'createdAt');
  requireTimestamp(value.updatedAt, 'updatedAt');
}

function validateCashEntry(entry: CashEntry): void {
  validateSharedEvent(entry);
  requireVnd(entry.amountVnd, 'amountVnd');
  if (entry.note && entry.note.length > 500) throw new Error('note is too long');
}

function validateTrade(trade: LedgerTrade): string {
  validateSharedEvent(trade);
  if (!Number.isFinite(trade.quantity) || trade.quantity <= 0) throw new Error('quantity must be positive');
  if (Math.round(trade.quantity * 10_000) !== trade.quantity * 10_000) throw new Error('quantity supports at most four decimal places');
  requireVnd(trade.unitPriceVnd, 'unitPriceVnd');
  requireVnd(trade.feeVnd, 'feeVnd', true);
  requireVnd(trade.taxVnd, 'taxVnd', true);
  return requireVietnamSymbol(trade.symbol);
}

function compareEvents(left: OrderedEvent, right: OrderedEvent): number {
  return Date.parse(left.value.occurredAt) - Date.parse(right.value.occurredAt)
    || Date.parse(left.value.createdAt) - Date.parse(right.value.createdAt)
    || left.value.id.localeCompare(right.value.id);
}

export function replayLedger(cashEntries: readonly CashEntry[], trades: readonly LedgerTrade[]) {
  const ordered: OrderedEvent[] = [
    ...cashEntries.map((value): OrderedEvent => ({ kind: 'cash', value })),
    ...trades.map((value): OrderedEvent => ({ kind: 'trade', value }))
  ].sort(compareEvents);
  const positions = new Map<string, LedgerPosition>();
  const realizedSales: RealizedSale[] = [];
  const events: LedgerEvent[] = [];
  let availableCashVnd = 0;

  for (const event of ordered) {
    let walletEffectVnd: number;

    if (event.kind === 'cash') {
      validateCashEntry(event.value);
      walletEffectVnd = event.value.type === 'withdrawal' ? -event.value.amountVnd : event.value.amountVnd;
    } else {
      const trade = event.value;
      const symbol = validateTrade(trade);
      const principalVnd = Math.round(trade.quantity * trade.unitPriceVnd);
      const current = positions.get(symbol);

      if (trade.type === 'buy') {
        const purchaseCostVnd = principalVnd + trade.feeVnd;
        walletEffectVnd = -purchaseCostVnd;
        const quantity = (current?.quantity ?? 0) + trade.quantity;
        const totalCostVnd = (current?.totalCostVnd ?? 0) + purchaseCostVnd;
        positions.set(symbol, {
          symbol,
          quantity,
          averageCostVnd: totalCostVnd / quantity,
          totalCostVnd,
          positionOpenedAt: current?.positionOpenedAt ?? trade.occurredAt
        });
      } else {
        if (!current || trade.quantity > current.quantity) {
          throw new LedgerInvariantError('INSUFFICIENT_SHARES', trade.id);
        }

        const grossProceedsVnd = principalVnd;
        const netProceedsVnd = grossProceedsVnd - trade.feeVnd - trade.taxVnd;
        const removedCostBasisVnd = current.averageCostVnd * trade.quantity;
        const remainingQuantity = current.quantity - trade.quantity;
        walletEffectVnd = netProceedsVnd;
        realizedSales.push({
          tradeId: trade.id,
          symbol,
          quantity: trade.quantity,
          grossProceedsVnd,
          netProceedsVnd,
          removedCostBasisVnd,
          realizedProfitLossVnd: netProceedsVnd - removedCostBasisVnd,
          occurredAt: trade.occurredAt
        });

        if (remainingQuantity === 0) {
          positions.delete(symbol);
        } else {
          const totalCostVnd = current.totalCostVnd - removedCostBasisVnd;
          positions.set(symbol, { ...current, quantity: remainingQuantity, totalCostVnd, averageCostVnd: totalCostVnd / remainingQuantity });
        }
      }
    }

    if (availableCashVnd + walletEffectVnd < 0) {
      throw new LedgerInvariantError('INSUFFICIENT_CASH', event.value.id);
    }
    availableCashVnd += walletEffectVnd;
    events.push({
      id: event.value.id,
      kind: event.kind,
      occurredAt: event.value.occurredAt,
      createdAt: event.value.createdAt,
      walletEffectVnd,
      walletAfterVnd: availableCashVnd
    });
  }

  return {
    availableCashVnd,
    positions: [...positions.values()].sort((left, right) => left.symbol.localeCompare(right.symbol)),
    realizedSales,
    events
  };
}
