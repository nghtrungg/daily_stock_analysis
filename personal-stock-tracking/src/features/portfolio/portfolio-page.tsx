'use client';

import Link from 'next/link';
import { Eye, WalletCards } from 'lucide-react';
import { AppShell } from '../../components/app-shell';
import { formatVnd } from '../../lib/money';
import { usePortfolio } from './portfolio-provider';

export function PortfolioPage() {
  const { positions, totalCostVnd } = usePortfolio();

  return (
    <AppShell activePath="/portfolio" action={<Link className="button button--primary" href="/">Ghi giao dịch</Link>}>
      <section className="portfolio-lead" aria-labelledby="portfolio-title">
        <div>
          <p className="utility-label">Sổ danh mục · VND</p>
          <h1 id="portfolio-title">Các khoản nắm giữ</h1>
        </div>
        <p className="lead-copy">Xem các vị thế được tính từ sổ giao dịch an toàn. Giá trị thị trường sẽ được nêu rõ là chưa có cho đến khi kết nối nguồn giá đáng tin cậy.</p>
      </section>

      <section className="summary-grid" aria-label="Tóm tắt danh mục">
        <article className="summary-card summary-card--emphasis">
          <span>Tổng giá vốn</span>
          <strong>{formatVnd(totalCostVnd)}</strong>
          <small>Từ các giao dịch mua đã ghi</small>
        </article>
        <article className="summary-card">
          <span>Giá trị thị trường</span>
          <strong>—</strong>
          <small>Chưa có giá trị thị trường</small>
        </article>
      </section>

      <section className="workbench" aria-label="Danh sách khoản nắm giữ">
        {positions.length === 0 ? (
          <div className="empty-frame">
            <div className="empty-frame__mark" aria-hidden="true"><WalletCards size={28} strokeWidth={1.5} /></div>
            <div className="empty-frame__copy">
              <h2>Chưa có khoản nắm giữ</h2>
              <p>Ghi giao dịch mua tại trang chủ để tạo vị thế và tính giá vốn bình quân gia quyền.</p>
            </div>
            <Link className="button button--secondary" href="/">Về trang chủ</Link>
          </div>
        ) : (
          <div className="holding-list" aria-label="Các khoản nắm giữ đã ghi">
            {positions.map((position) => (
              <article className="holding-frame" key={position.symbol}>
                <div className="holding-frame__identity">
                  <span className="ticker-mark" aria-hidden="true">VN</span>
                  <div>
                    <h2>{position.symbol}</h2>
                    <p>Nắm giữ · {position.quantity} cổ phiếu</p>
                  </div>
                </div>
                <dl className="holding-frame__metrics">
                  <div><dt>Giá vốn bình quân</dt><dd>{formatVnd(position.averageCostVnd)}</dd></div>
                  <div><dt>Giá trị thị trường</dt><dd>—</dd></div>
                </dl>
                <p className="disabled-note"><Eye aria-hidden="true" size={14} /> Chưa có giá trị thị trường</p>
              </article>
            ))}
          </div>
        )}
      </section>
    </AppShell>
  );
}
