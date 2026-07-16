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
  { href: '/', label: 'Trang chủ', icon: House },
  { href: '/portfolio', label: 'Danh mục', icon: WalletCards },
  { href: '/watchlist', label: 'Theo dõi', icon: Eye },
  { href: '/activity', label: 'Lịch sử', icon: ListPlus },
  { href: '/settings', label: 'Cài đặt', icon: Settings }
] as const;

export function AppShell({ activePath, action, children }: AppShellProps) {
  const activeLabel = navigation.find(({ href }) => href === activePath)?.label ?? 'Danh mục';

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Bỏ qua để đến nội dung danh mục</a>

      <aside className="app-sidebar">
        <Link className="brand-lockup" href="/" aria-label="Trang chủ sổ theo dõi danh mục cá nhân">
          <span className="brand-mark" aria-hidden="true">L</span>
          <span className="brand-copy"><strong>Ledger</strong><small>Đầu tư cá nhân</small></span>
        </Link>

        <nav className="primary-nav" aria-label="Điều hướng chính">
          {navigation.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} aria-current={activePath === href ? 'page' : undefined}>
              <Icon aria-hidden="true" size={19} strokeWidth={1.9} />
              <span>{label}</span>
            </Link>
          ))}
        </nav>

        <div className="sidebar-note">
          <LockKeyhole aria-hidden="true" size={18} />
          <div><strong>Không gian riêng tư</strong><small>Dữ liệu chỉ dành cho chủ sở hữu</small></div>
        </div>
      </aside>

      <div className="app-canvas">
        <header className="app-header">
          <Link className="mobile-wordmark" href="/" aria-label="Trang chủ sổ theo dõi danh mục cá nhân">Ledger</Link>
          <div className="header-context">
            <span>Danh mục Việt Nam</span>
            <strong>{activeLabel}</strong>
          </div>
          <div className="header-action">{action ?? <span className="secure-status"><LockKeyhole aria-hidden="true" size={14} />Được bảo vệ</span>}</div>
        </header>

        <main className="app-main" id="main-content" tabIndex={-1}>{children}</main>

        <footer className="app-footer">
          <p>Ledger · Theo dõi danh mục Việt Nam · Chỉ mang tính tham khảo</p>
          <p>Mọi giá trị đều bằng VND</p>
        </footer>
      </div>
    </div>
  );
}
