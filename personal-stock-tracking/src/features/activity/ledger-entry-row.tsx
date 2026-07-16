'use client';

import { Pencil, TrendingDown, TrendingUp, WalletCards } from 'lucide-react';
import { formatVietnamDateTime } from '../../lib/datetime';
import type { CashEntry, LedgerTrade, RealizedSale } from '../../lib/ledger';
import { formatVnd } from '../../lib/money';

export type ActivityLedgerItem = {
  kind: 'cash';
  entry: CashEntry;
  walletEffectVnd: number;
  walletAfterVnd: number;
} | {
  kind: 'trade';
  entry: LedgerTrade;
  walletEffectVnd: number;
  walletAfterVnd: number;
  realizedSale?: RealizedSale;
};

function isEdited(createdAt: string, updatedAt: string) {
  return Date.parse(updatedAt) > Date.parse(createdAt) + 1;
}

export function ledgerItemLabel(item: ActivityLedgerItem): string {
  if (item.kind === 'cash') {
    if (item.entry.type === 'deposit') return 'Nạp tiền';
    if (item.entry.type === 'withdrawal') return 'Rút tiền';
    return 'Số dư đầu kỳ';
  }
  return item.entry.type === 'buy' ? 'Mua' : 'Bán';
}

export function LedgerEntryRow({ item, onEdit }: { item: ActivityLedgerItem; onEdit: () => void }) {
  const label = ledgerItemLabel(item);
  const editable = !(item.kind === 'cash' && item.entry.type === 'opening_balance');
  const Icon = item.walletEffectVnd > 0 ? TrendingUp : item.walletEffectVnd < 0 ? TrendingDown : WalletCards;

  return (
    <li className="activity-entry">
      <div className="activity-entry__icon" aria-hidden="true"><Icon size={20} /></div>
      <div className="activity-entry__copy">
        <p className="utility-label">{label}{isEdited(item.entry.createdAt, item.entry.updatedAt) ? ' · Đã chỉnh sửa' : ''}</p>
        <h2>{item.kind === 'cash' ? formatVnd(item.entry.amountVnd) : `${item.entry.symbol} · ${item.entry.quantity.toLocaleString('vi-VN')} cổ phiếu`}</h2>
        <p>{formatVietnamDateTime(item.entry.occurredAt)}{item.kind === 'cash' && item.entry.note ? ` · ${item.entry.note}` : ''}</p>
        {item.kind === 'trade' && <p>Đơn giá {formatVnd(item.entry.unitPriceVnd)} · Phí {formatVnd(item.entry.feeVnd)}{item.entry.taxVnd ? ` · Thuế ${formatVnd(item.entry.taxVnd)}` : ''}</p>}
        {item.kind === 'trade' && item.realizedSale && <p>Lãi/lỗ đã thực hiện: {formatVnd(item.realizedSale.realizedProfitLossVnd)}</p>}
        {item.kind === 'cash' && item.entry.type === 'opening_balance' && <p className="opening-note">Bút toán chuyển đổi dữ liệu, không thể chỉnh sửa hoặc xóa.</p>}
      </div>
      <div className="activity-entry__amount">
        <strong>{item.walletEffectVnd >= 0 ? '+' : '−'}{formatVnd(Math.abs(item.walletEffectVnd))}</strong>
        <span>Số dư sau bút toán {formatVnd(item.walletAfterVnd)}</span>
        {editable && <button id={`edit-${item.kind}-${item.entry.id}`} className="button button--secondary" type="button" onClick={onEdit}><Pencil aria-hidden="true" size={15} />Chỉnh sửa</button>}
      </div>
    </li>
  );
}
