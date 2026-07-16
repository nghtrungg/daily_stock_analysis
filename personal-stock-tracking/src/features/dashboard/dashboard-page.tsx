'use client';

import { useState } from 'react';
import { BarChart3, Eye, Plus, WalletCards } from 'lucide-react';
import { AppShell } from '../../components/app-shell';
import { formatVnd } from '../../lib/money';
import { PositionCard } from '../portfolio/position-card';
import { TradeForm } from '../portfolio/trade-form';
import { usePortfolio } from '../portfolio/portfolio-provider';
import { WalletForm } from '../portfolio/wallet-form';

export function DashboardPage() {
  const [tradeForm, setTradeForm] = useState<{ type: 'buy' | 'sell'; symbol?: string; quantity?: number } | null>(null);
  const {
    analysisRequestStateFor, errorMessage, isLoading, isMutating, latestAnalysisFor,
    marketValueVnd, missingQuoteSymbols, positions, requestAnalysis, totalAssetsVnd, totalCostVnd, wallet
  } = usePortfolio();

  async function analyzeSymbol(symbol: string) {
    try { await requestAnalysis(symbol); } catch { /* The provider exposes the safe message below. */ }
  }

  return (
    <AppShell
      activePath="/"
      action={<button className="button button--primary" disabled={isMutating} type="button" onClick={() => setTradeForm({ type: 'buy' })}><Plus aria-hidden="true" size={17} /><span>Ghi giao dịch</span></button>}
    >
      <section className="portfolio-lead" aria-labelledby="dashboard-title">
        <div><p className="utility-label">Danh mục cá nhân · VND</p><h1 id="dashboard-title">Tổng quan danh mục</h1></div>
        <p className="lead-copy">Theo dõi ví ghi sổ, khoản nắm giữ và giá tại lần phân tích gần nhất. Ứng dụng không chuyển tiền thật hoặc đặt lệnh tại công ty chứng khoán.</p>
      </section>

      <section className="summary-grid" aria-label="Tóm tắt danh mục">
        <article className="summary-card summary-card--emphasis"><span>Số dư khả dụng</span><strong>{formatVnd(wallet.availableCashVnd)}</strong><small>Tiền còn lại trong ví ghi sổ</small></article>
        <article className="summary-card"><span>Tổng giá vốn</span><strong>{formatVnd(totalCostVnd)}</strong><small>Giá vốn của các vị thế đang mở</small></article>
        <article className="summary-card"><span>Giá trị thị trường</span><strong>{marketValueVnd === null ? 'Chưa đủ dữ liệu' : formatVnd(marketValueVnd)}</strong><small>{missingQuoteSymbols.length ? `Thiếu giá: ${missingQuoteSymbols.join(', ')}` : 'Theo giá phân tích gần nhất'}</small></article>
        <article className="summary-card"><span>Tổng tài sản</span><strong>{totalAssetsVnd === null ? 'Chưa đủ dữ liệu' : formatVnd(totalAssetsVnd)}</strong><small>Ví khả dụng + giá trị thị trường</small></article>
      </section>

      <WalletForm />

      <section className="workbench" aria-labelledby="holdings-title">
        <div className="section-heading">
          <div><p className="utility-label">Vị thế hiện tại</p><h2 id="holdings-title">Khoản nắm giữ</h2></div>
          <span className="local-indicator">{isLoading ? 'Đang đồng bộ' : 'Đã đồng bộ an toàn'}</span>
        </div>

        {isLoading ? (
          <div className="loading-frame" role="status" aria-label="Đang tải danh mục">
            <div className="loading-frame__heading"><span className="skeleton skeleton--mark" aria-hidden="true" /><div><span className="skeleton skeleton--title" aria-hidden="true" /><span className="skeleton skeleton--copy" aria-hidden="true" /></div></div>
            <span className="skeleton skeleton--panel" aria-hidden="true" /><span className="visually-hidden">Đang tải danh mục của bạn.</span>
          </div>
        ) : positions.length === 0 ? (
          <section className="empty-frame" aria-label="Danh mục trống">
            <div className="empty-frame__mark" aria-hidden="true"><WalletCards size={28} /></div>
            <div className="empty-frame__copy"><h3>Chưa có khoản nắm giữ</h3><p>{wallet.availableCashVnd === 0 ? 'Nạp tiền vào ví ghi sổ, sau đó ghi giao dịch mua đầu tiên.' : 'Ví đã có tiền. Bạn có thể ghi giao dịch mua đầu tiên.'}</p></div>
            <div className="state-list"><span className="state-chip"><Eye aria-hidden="true" size={14} />Giá: Chưa có</span><span className="state-chip state-chip--quiet"><BarChart3 aria-hidden="true" size={14} />Phân tích: Chưa từng phân tích</span></div>
            <button className="button button--secondary" disabled={isMutating || wallet.availableCashVnd === 0} type="button" onClick={() => setTradeForm({ type: 'buy' })}>Ghi giao dịch mua</button>
          </section>
        ) : (
          <div className="holding-list" aria-label="Các khoản nắm giữ">
            {positions.map((position) => <PositionCard
              key={position.symbol}
              position={position}
              run={latestAnalysisFor(position.symbol)}
              requestState={analysisRequestStateFor(position.symbol)}
              onAnalyze={() => void analyzeSymbol(position.symbol)}
              onSell={() => setTradeForm({ type: 'sell', symbol: position.symbol, quantity: position.quantity })}
            />)}
          </div>
        )}
        {errorMessage && <p className="form-error" role="alert">{errorMessage}</p>}
      </section>

      {tradeForm && <TradeForm initialType={tradeForm.type} initialSymbol={tradeForm.symbol} initialQuantity={tradeForm.quantity} onClose={() => setTradeForm(null)} />}
    </AppShell>
  );
}
