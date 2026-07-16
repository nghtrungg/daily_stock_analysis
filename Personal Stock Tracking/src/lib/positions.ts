import { requireVietnamSymbol } from './symbols';

export type PortfolioTransaction = {
  id: string;
  type: 'buy' | 'sell';
  symbol: string;
  quantity: number;
  unitPriceVnd: number;
  feeVnd: number;
  occurredAt: string;
};

export type Position = {
  symbol: string;
  quantity: number;
  averageCostVnd: number;
  totalCostVnd: number;
  initialEntryPriceVnd: number;
  positionOpenedAt: string;
};

type MutablePosition = Position;

function assertTransaction(transaction: PortfolioTransaction): void {
  if (!Number.isFinite(transaction.quantity) || transaction.quantity <= 0) {
    throw new Error('quantity must be greater than zero');
  }

  if (!Number.isFinite(transaction.unitPriceVnd) || transaction.unitPriceVnd <= 0) {
    throw new Error('unit price must be greater than zero');
  }

  if (!Number.isFinite(transaction.feeVnd) || transaction.feeVnd < 0) {
    throw new Error('fee must be zero or greater');
  }

  if (Number.isNaN(Date.parse(transaction.occurredAt))) {
    throw new Error('occurredAt must be a valid timestamp');
  }
}

export function derivePositions(transactions: readonly PortfolioTransaction[]): Position[] {
  const positions = new Map<string, MutablePosition>();
  const orderedTransactions = [...transactions].sort(
    (left, right) => Date.parse(left.occurredAt) - Date.parse(right.occurredAt)
  );

  for (const transaction of orderedTransactions) {
    assertTransaction(transaction);
    const symbol = requireVietnamSymbol(transaction.symbol);
    const current = positions.get(symbol);

    if (transaction.type === 'buy') {
      const purchaseCost = transaction.quantity * transaction.unitPriceVnd + transaction.feeVnd;

      if (!current) {
        positions.set(symbol, {
          symbol,
          quantity: transaction.quantity,
          averageCostVnd: purchaseCost / transaction.quantity,
          totalCostVnd: purchaseCost,
          initialEntryPriceVnd: transaction.unitPriceVnd,
          positionOpenedAt: transaction.occurredAt
        });
        continue;
      }

      const quantity = current.quantity + transaction.quantity;
      const totalCostVnd = current.totalCostVnd + purchaseCost;
      positions.set(symbol, {
        ...current,
        quantity,
        averageCostVnd: totalCostVnd / quantity,
        totalCostVnd
      });
      continue;
    }

    if (!current || transaction.quantity > current.quantity) {
      throw new Error('cannot sell more shares than are held');
    }

    const quantity = current.quantity - transaction.quantity;
    if (quantity === 0) {
      positions.delete(symbol);
      continue;
    }

    const totalCostVnd = current.averageCostVnd * quantity;
    positions.set(symbol, {
      ...current,
      quantity,
      totalCostVnd
    });
  }

  return [...positions.values()].sort((left, right) => left.symbol.localeCompare(right.symbol));
}
