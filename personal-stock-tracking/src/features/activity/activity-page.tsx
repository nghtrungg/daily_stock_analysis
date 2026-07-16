'use client';

import Link from 'next/link';
import { ListPlus } from 'lucide-react';
import { AppShell } from '../../components/app-shell';
import { formatVnd } from '../../lib/money';
import { usePortfolio } from '../portfolio/portfolio-provider';

export function ActivityPage() {
  const { transactions } = usePortfolio();

  return (
    <AppShell activePath="/activity" action={<Link className="button button--primary" href="/">Ghi giao dịch</Link>}>
      <section className="portfolio-lead" aria-labelledby="activity-title">
        <div>
          <p className="utility-label">Sổ giao dịch</p>
          <h1 id="activity-title">Lịch sử</h1>
        </div>
        <p className="lead-copy">Mọi thay đổi trong danh mục đều bắt đầu bằng một bút toán. Sổ giao dịch an toàn là nguồn dữ liệu chính để tính giá vốn.</p>
      </section>

      <section className="workbench" aria-label="Lịch sử giao dịch">
        {transactions.length === 0 ? (
          <div className="empty-frame">
            <div className="empty-frame__mark" aria-hidden="true"><ListPlus size={28} strokeWidth={1.5} /></div>
            <div className="empty-frame__copy">
              <h2>Chưa ghi giao dịch nào</h2>
              <p>Hãy bắt đầu bằng giao dịch mua tại trang chủ. Giao dịch sẽ xuất hiện ở đây và cập nhật khoản nắm giữ trên mọi nơi bạn đăng nhập.</p>
            </div>
            <Link className="button button--secondary" href="/">Ghi giao dịch</Link>
          </div>
        ) : (
          <ol className="activity-list">
            {[...transactions].reverse().map((transaction) => (
              <li className="activity-entry" key={transaction.id}>
                <div className="activity-entry__copy">
                  <p className="utility-label">Giao dịch mua</p>
                  <h2>{transaction.symbol} · {transaction.quantity} cổ phiếu</h2>
                </div>
                <div className="activity-entry__amount">
                  <strong>{formatVnd(transaction.unitPriceVnd)}</strong>
                  <span>Phí {formatVnd(transaction.feeVnd)}</span>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </AppShell>
  );
}
