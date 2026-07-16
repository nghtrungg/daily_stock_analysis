import type { ReactNode } from 'react';
import { AppShell } from './app-shell';

type UtilityPageProps = {
  activePath: '/portfolio' | '/watchlist' | '/activity' | '/settings';
  eyebrow: string;
  title: string;
  description: string;
  marker: ReactNode;
  emptyTitle: string;
  emptyCopy: string;
  action?: ReactNode;
};

export function UtilityPage({
  activePath,
  eyebrow,
  title,
  description,
  marker,
  emptyTitle,
  emptyCopy,
  action
}: UtilityPageProps) {
  return (
    <AppShell activePath={activePath}>
      <section className="portfolio-lead" aria-labelledby="page-title">
        <div>
          <p className="utility-label">{eyebrow}</p>
          <h1 id="page-title">{title}</h1>
        </div>
        <p className="lead-copy">{description}</p>
      </section>

      <section className="workbench" aria-label={`Khu vực ${title.toLocaleLowerCase('vi-VN')}`}>
        <div className="empty-frame">
          <div className="empty-frame__mark" aria-hidden="true">{marker}</div>
          <div className="empty-frame__copy">
            <h2>{emptyTitle}</h2>
            <p>{emptyCopy}</p>
          </div>
          {action}
        </div>
      </section>
    </AppShell>
  );
}
