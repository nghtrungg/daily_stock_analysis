'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';
import { Eye, House, ListPlus, Settings, WalletCards } from 'lucide-react';

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
  return (
    <main className="app-shell">
      <header className="app-header">
        <Link className="wordmark" href="/" aria-label="Personal portfolio tracker home">Ledger</Link>
        {action}
      </header>

      {children}

      <nav className="mobile-nav" aria-label="Primary navigation">
        {navigation.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} aria-current={activePath === href ? 'page' : undefined}>
            <Icon aria-hidden="true" size={18} />
            <span>{label}</span>
          </Link>
        ))}
      </nav>

      <footer className="app-footer">
        <p>Ledger · Vietnam portfolio tracking · Informational only</p>
        <p>All values in VND</p>
      </footer>
    </main>
  );
}
