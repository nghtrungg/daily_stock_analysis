'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Plus, WalletCards } from 'lucide-react';
import { AppShell } from '../../components/app-shell';
import { formatVnd } from '../../lib/money';
import { PositionCard } from './position-card';
import { TradeForm } from './trade-form';
import { usePortfolio } from './portfolio-provider';

export function PortfolioPage() {
  const [sellPosition, setSellPosition] = useState<{ symbol: string; quantity: number } | null>(null);
  const { marketValueVnd, missingQuoteSymbols, positions, totalAssetsVnd, totalCostVnd, wallet } = usePortfolio();

  return (
    <AppShell activePath="/portfolio" action={<Link className="button button--primary" href="/"><Plus aria-hidden="true" size={17} />Ghi giao dịch</Link>}>
      <section className="portfolio-lead" aria-labelledby="portfolio-title">
        <div><p className="utility-label">Sổ danh mục · VND</p><h1 id="portfolio-title">Các khoản nắm giữ</h1></div>
        <p className="lead-copy">Giá trị được tính từ sổ giao dịch và giá tại lần phân tích gần nhất. Giá cũ hoặc còn thiếu luôn được ghi rõ.</p>
      </section>

      <section className="summary-grid" aria-label="Tóm tắt danh mục">
        <article className="summary-card summary-card--emphasis"><span>Số dư khả dụng</span><strong>{formatVnd(wallet.availableCashVnd)}</strong><small>Ví ghi sổ</small></article>
        <article className="summary-card"><span>Tổng giá vốn</span><strong>{formatVnd(totalCostVnd)}</strong><small>Các vị thế đang mở</small></article>
        <article className="summary-card"><span>Giá trị thị trường</span><strong>{marketValueVnd === null ? 'Chưa đủ dữ liệu' : formatVnd(marketValueVnd)}</strong><small>{missingQuoteSymbols.length ? `Thiếu giá: ${missingQuoteSymbols.join(', ')}` : 'Theo giá gần nhất'}</small></article>
        <article className="summary-card"><span>Tổng tài sản</span><strong>{totalAssetsVnd === null ? 'Chưa đủ dữ liệu' : formatVnd(totalAssetsVnd)}</strong><small>Ví + giá trị thị trường</small></article>
      </section>

      <section className="workbench" aria-label="Danh sách khoản nắm giữ">
        {positions.length === 0 ? (
          <div className="empty-frame">
            <div className="empty-frame__mark" aria-hidden="true"><WalletCards size={28} /></div>
            <div className="empty-frame__copy"><h2>Chưa có khoản nắm giữ</h2><p>Nạp tiền và ghi giao dịch mua tại trang chủ để tạo vị thế.</p></div>
            <Link className="button button--secondary" href="/">Về trang chủ</Link>
          </div>
        ) : (
          <div className="holding-list" aria-label="Các khoản nắm giữ đã ghi">
            {positions.map((position) => <PositionCard key={position.symbol} position={position} onSell={() => setSellPosition({ symbol: position.symbol, quantity: position.quantity })} />)}
          </div>
        )}
      </section>

      {sellPosition && <TradeForm initialType="sell" initialSymbol={sellPosition.symbol} initialQuantity={sellPosition.quantity} onClose={() => setSellPosition(null)} />}
    </AppShell>
  );
}
