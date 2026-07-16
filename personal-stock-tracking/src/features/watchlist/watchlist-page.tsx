'use client';

import { useState, type FormEvent } from 'react';
import { BarChart3, Eye, Plus } from 'lucide-react';
import { AppShell } from '../../components/app-shell';
import { analysisActionLabel, analysisNote, analysisStatusLabel } from '../portfolio/analysis-messages';
import { usePortfolio } from '../portfolio/portfolio-provider';

export function WatchlistPage() {
  const [symbol, setSymbol] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const { addWatchlistSymbol, analysisRequestStateFor, errorMessage, isLoading, isMutating, latestAnalysisFor, requestAnalysis, watchlistSymbols } = usePortfolio();

  async function submitWatchlistSymbol(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      await addWatchlistSymbol(symbol);
      setSymbol('');
      setFormError(null);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Không thể thêm mã vào danh sách theo dõi.');
    }
  }

  async function analyzeSymbol(watchSymbol: string) {
    try {
      await requestAnalysis(watchSymbol);
    } catch {
      // The shared provider exposes a user-safe error message below the list.
    }
  }

  return (
    <AppShell activePath="/watchlist">
      <section className="portfolio-lead" aria-labelledby="watchlist-title">
        <div>
          <p className="utility-label">Danh sách nghiên cứu</p>
          <h1 id="watchlist-title">Theo dõi</h1>
        </div>
        <p className="lead-copy">Lưu các mã chứng khoán Việt Nam bạn muốn nghiên cứu. Mã trong danh sách không đồng nghĩa đã có giá trực tiếp hoặc bản phân tích.</p>
      </section>

      <form className="watchlist-form" noValidate onSubmit={submitWatchlistSymbol}>
        <label>
          <span>Mã theo dõi</span>
          <input
            aria-invalid={Boolean(formError)}
            aria-label="Mã theo dõi"
            onChange={(event) => setSymbol(event.target.value)}
            placeholder="VNM.VN"
            value={symbol}
          />
          <small>{formError ?? 'Mã chứng khoán Việt Nam phải kết thúc bằng .VN.'}</small>
        </label>
        <div className="form-actions">
          <button className="button button--primary" disabled={isMutating} type="submit">
            <Plus aria-hidden="true" size={17} strokeWidth={2.2} />
            Thêm vào theo dõi
          </button>
        </div>
      </form>

      <section className="workbench" aria-label="Các mã đang theo dõi">
        {isLoading ? (
          <div className="empty-frame" aria-busy="true" aria-label="Đang tải danh sách theo dõi">
            <div className="empty-frame__copy"><h2>Đang tải danh sách theo dõi</h2><p>Danh sách theo dõi an toàn của bạn đang được tải.</p></div>
          </div>
        ) : watchlistSymbols.length === 0 ? (
          <div className="empty-frame">
            <div className="empty-frame__mark" aria-hidden="true"><Eye size={28} strokeWidth={1.5} /></div>
            <div className="empty-frame__copy">
              <h2>Chưa có mã nào trong danh sách theo dõi</h2>
              <p>Thêm mã có hậu tố `.VN` ở trên để theo dõi riêng với các khoản đang nắm giữ.</p>
            </div>
          </div>
        ) : (
          <ul className="watchlist" aria-label="Các mã theo dõi đã lưu">
            {watchlistSymbols.map((watchSymbol) => {
              const run = latestAnalysisFor(watchSymbol);
              const requestState = analysisRequestStateFor(watchSymbol);
              const note = analysisNote(run);

              return (
                <li className="watchlist-entry" key={watchSymbol}>
                  <div className="watchlist-entry__identity">
                    <span className="ticker-mark" aria-hidden="true">VN</span>
                    <h2>{watchSymbol}</h2>
                  </div>
                  <div className="state-list" aria-label={`Trạng thái dữ liệu ${watchSymbol}`}>
                    <span className="state-chip"><Eye aria-hidden="true" size={14} />Giá: Chưa có</span>
                    <span className="state-chip state-chip--quiet"><BarChart3 aria-hidden="true" size={14} />Phân tích: {analysisStatusLabel(run)}</span>
                  </div>
                  <div className="watchlist-entry__analysis">
                    <button className="button button--secondary" type="button" disabled={requestState !== 'ready'} onClick={() => void analyzeSymbol(watchSymbol)} aria-describedby={`${watchSymbol}-analysis-note`}>
                      {analysisActionLabel(requestState)}
                    </button>
                    <p id={`${watchSymbol}-analysis-note`}>{note}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {errorMessage && <p className="form-error" role="alert">{errorMessage}</p>}
      </section>
    </AppShell>
  );
}
