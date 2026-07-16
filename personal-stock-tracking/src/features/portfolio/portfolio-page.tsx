'use client';

import Link from 'next/link';
import { Eye, WalletCards } from 'lucide-react';
import { AppShell } from '../../components/app-shell';
import { formatVnd } from '../../lib/money';
import { usePortfolio } from './portfolio-provider';

export function PortfolioPage() {
  const { positions, totalCostVnd } = usePortfolio();

  return (
    <AppShell activePath="/portfolio" action={<Link className="button button--primary" href="/">Add transaction</Link>}>
      <section className="portfolio-lead" aria-labelledby="portfolio-title">
        <div>
          <p className="utility-label">Portfolio ledger · VND</p>
          <h1 id="portfolio-title">Your holdings</h1>
        </div>
        <p className="lead-copy">Review positions derived from your secure ledger. Market value remains unavailable until a trusted quote source is connected.</p>
      </section>

      <section className="summary-grid" aria-label="Portfolio summary">
        <article className="summary-card summary-card--emphasis">
          <span>Total cost</span>
          <strong>{formatVnd(totalCostVnd)}</strong>
          <small>From recorded buys</small>
        </article>
        <article className="summary-card">
          <span>Market value</span>
          <strong>—</strong>
          <small>Market value unavailable</small>
        </article>
      </section>

      <section className="workbench" aria-label="Holdings list">
        {positions.length === 0 ? (
          <div className="empty-frame">
            <div className="empty-frame__mark" aria-hidden="true"><WalletCards size={28} strokeWidth={1.5} /></div>
            <div className="empty-frame__copy">
              <h2>No holdings yet</h2>
              <p>Record a buy transaction from the dashboard to establish a position and its weighted-average cost.</p>
            </div>
            <Link className="button button--secondary" href="/">Go to dashboard</Link>
          </div>
        ) : (
          <div className="holding-list" aria-label="Recorded holdings">
            {positions.map((position) => (
              <article className="holding-frame" key={position.symbol}>
                <div className="holding-frame__identity">
                  <span className="ticker-mark" aria-hidden="true">VN</span>
                  <div>
                    <h2>{position.symbol}</h2>
                    <p>Holding · {position.quantity} shares</p>
                  </div>
                </div>
                <dl className="holding-frame__metrics">
                  <div><dt>Average cost</dt><dd>{formatVnd(position.averageCostVnd)}</dd></div>
                  <div><dt>Market value</dt><dd>—</dd></div>
                </dl>
                <p className="disabled-note"><Eye aria-hidden="true" size={14} /> Market value unavailable</p>
              </article>
            ))}
          </div>
        )}
      </section>
    </AppShell>
  );
}
