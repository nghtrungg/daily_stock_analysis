'use client';

import Link from 'next/link';
import { ListPlus } from 'lucide-react';
import { AppShell } from '../../components/app-shell';
import { formatVnd } from '../../lib/money';
import { usePortfolio } from '../portfolio/portfolio-provider';

export function ActivityPage() {
  const { transactions } = usePortfolio();

  return (
    <AppShell activePath="/activity" action={<Link className="button button--primary" href="/">Add transaction</Link>}>
      <section className="portfolio-lead" aria-labelledby="activity-title">
        <div>
          <p className="utility-label">Transaction ledger</p>
          <h1 id="activity-title">Activity</h1>
        </div>
        <p className="lead-copy">Every portfolio change begins as a ledger entry. The secure ledger remains the source of truth for cost calculations.</p>
      </section>

      <section className="workbench" aria-label="Transaction activity">
        {transactions.length === 0 ? (
          <div className="empty-frame">
            <div className="empty-frame__mark" aria-hidden="true"><ListPlus size={28} strokeWidth={1.5} /></div>
            <div className="empty-frame__copy">
              <h2>No transactions recorded</h2>
              <p>Start with a buy transaction on the dashboard. It will appear here and update your holdings wherever you sign in.</p>
            </div>
            <Link className="button button--secondary" href="/">Record a transaction</Link>
          </div>
        ) : (
          <ol className="activity-list">
            {[...transactions].reverse().map((transaction) => (
              <li className="activity-entry" key={transaction.id}>
                <div className="activity-entry__copy">
                  <p className="utility-label">Buy transaction</p>
                  <h2>{transaction.symbol} · {transaction.quantity} shares</h2>
                </div>
                <div className="activity-entry__amount">
                  <strong>{formatVnd(transaction.unitPriceVnd)}</strong>
                  <span>{formatVnd(transaction.feeVnd)} fees</span>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </AppShell>
  );
}
