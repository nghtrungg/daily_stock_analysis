'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { ListPlus } from 'lucide-react';
import { AppShell } from '../../components/app-shell';
import { usePortfolio } from '../portfolio/portfolio-provider';
import { LedgerEntryEditor } from './ledger-entry-editor';
import { LedgerEntryRow, type ActivityLedgerItem } from './ledger-entry-row';

function compareItems(left: ActivityLedgerItem, right: ActivityLedgerItem) {
  return Date.parse(right.entry.occurredAt) - Date.parse(left.entry.occurredAt)
    || Date.parse(right.entry.createdAt) - Date.parse(left.entry.createdAt)
    || right.entry.id.localeCompare(left.entry.id);
}

export function ActivityPage() {
  const { cashEntries, ledgerEvents, realizedSales, transactions } = usePortfolio();
  const [editing, setEditing] = useState<ActivityLedgerItem | null>(null);
  const items = useMemo(() => {
    const effects = new Map(ledgerEvents.map((event) => [event.id, event]));
    const sales = new Map(realizedSales.map((sale) => [sale.tradeId, sale]));
    return [
      ...cashEntries.map((entry): ActivityLedgerItem => ({
        kind: 'cash', entry,
        walletEffectVnd: effects.get(entry.id)?.walletEffectVnd ?? (entry.type === 'withdrawal' ? -entry.amountVnd : entry.amountVnd),
        walletAfterVnd: effects.get(entry.id)?.walletAfterVnd ?? 0
      })),
      ...transactions.map((entry): ActivityLedgerItem => ({
        kind: 'trade', entry,
        walletEffectVnd: effects.get(entry.id)?.walletEffectVnd ?? 0,
        walletAfterVnd: effects.get(entry.id)?.walletAfterVnd ?? 0,
        realizedSale: sales.get(entry.id)
      }))
    ].sort(compareItems);
  }, [cashEntries, ledgerEvents, realizedSales, transactions]);

  function closeEditor() {
    const focusId = editing ? `edit-${editing.kind}-${editing.entry.id}` : null;
    setEditing(null);
    if (focusId) window.setTimeout(() => document.getElementById(focusId)?.focus(), 0);
  }

  return (
    <AppShell activePath="/activity" action={<Link className="button button--primary" href="/">Ghi bút toán</Link>}>
      <section className="portfolio-lead" aria-labelledby="activity-title">
        <div><p className="utility-label">Sổ ví và giao dịch</p><h1 id="activity-title">Lịch sử</h1></div>
        <p className="lead-copy">Nạp tiền, rút tiền, mua và bán được xếp theo thời điểm phát sinh. Chỉnh sửa hoặc xóa sẽ tính lại toàn bộ lịch sử phía sau.</p>
      </section>

      <section className="workbench" aria-label="Lịch sử bút toán">
        {items.length === 0 ? (
          <div className="empty-frame">
            <div className="empty-frame__mark" aria-hidden="true"><ListPlus size={28} /></div>
            <div className="empty-frame__copy"><h2>Chưa ghi bút toán nào</h2><p>Hãy bắt đầu bằng một khoản nạp tiền tại trang chủ.</p></div>
            <Link className="button button--secondary" href="/">Nạp tiền</Link>
          </div>
        ) : <ol className="activity-list">{items.map((item) => <LedgerEntryRow key={`${item.kind}-${item.entry.id}`} item={item} onEdit={() => setEditing(item)} />)}</ol>}
      </section>

      {editing && <LedgerEntryEditor item={editing} onClose={closeEditor} />}
    </AppShell>
  );
}
