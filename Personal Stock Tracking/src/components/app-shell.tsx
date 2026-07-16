'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';
import { Eye, House, ListPlus, LockKeyhole, Settings, WalletCards } from 'lucide-react';

type AppPath = '/' | '/portfolio' | '/watchlist' | '/activity' | '/settings';

type AppShellProps = {
  activePath: AppPath;
  action?: ReactNode;
  children: ReactNode;
};

const navigation = [
  { href: '/', label: 'Home', icon: House },
  { href: '/portfolio', label: 'Portfolio', icon: WalletCards },
  { href: '/watchlist', label: 'Watchlist', icon: Eye },
  { href: '/activity', label: 'Activity', icon: ListPlus },
  { href: '/settings', label: 'Settings', icon: Settings }
] as const;

export function AppShell({ activePath, action, children }: AppShellProps) {
  const activeLabel = navigation.find(({ href }) => href === activePath)?.label ?? 'Portfolio';

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to portfolio content</a>

      <aside className="app-sidebar">
        <Link className="brand-lockup" href="/" aria-label="Personal portfolio tracker home">
          <span className="brand-mark" aria-hidden="true">L</span>
          <span className="brand-copy"><strong>Ledger</strong><small>Personal investing</small></span>
        </Link>

        <nav className="primary-nav" aria-label="Primary navigation">
          {navigation.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} aria-current={activePath === href ? 'page' : undefined}>
              <Icon aria-hidden="true" size={19} strokeWidth={1.9} />
              <span>{label}</span>
            </Link>
          ))}
        </nav>

        <div className="sidebar-note">
          <LockKeyhole aria-hidden="true" size={18} />
          <div><strong>Private workspace</strong><small>Owner-only portfolio data</small></div>
        </div>
      </aside>

      <div className="app-canvas">
        <header className="app-header">
          <Link className="mobile-wordmark" href="/" aria-label="Personal portfolio tracker home">Ledger</Link>
          <div className="header-context">
            <span>Vietnam portfolio</span>
            <strong>{activeLabel}</strong>
          </div>
          <div className="header-action">{action ?? <span className="secure-status"><LockKeyhole aria-hidden="true" size={14} />Protected</span>}</div>
        </header>

        <main className="app-main" id="main-content" tabIndex={-1}>{children}</main>

        <footer className="app-footer">
          <p>Ledger · Vietnam portfolio tracking · Informational only</p>
          <p>All values in VND</p>
        </footer>
      </div>
    </div>
  );
}
