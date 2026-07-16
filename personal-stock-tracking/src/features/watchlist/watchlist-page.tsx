'use client';

import { useState, type FormEvent } from 'react';
import { BarChart3, Eye, Plus } from 'lucide-react';
import { AppShell } from '../../components/app-shell';
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
      setFormError(error instanceof Error ? error.message : 'Symbol could not be added to the watchlist.');
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
          <p className="utility-label">Research queue</p>
          <h1 id="watchlist-title">Watchlist</h1>
        </div>
        <p className="lead-copy">Keep an intentional list of Vietnam symbols to research. Watchlist entries never imply that a live quote or analysis is available.</p>
      </section>

      <form className="watchlist-form" noValidate onSubmit={submitWatchlistSymbol}>
        <label>
          <span>Watch symbol</span>
          <input
            aria-invalid={Boolean(formError)}
            aria-label="Watch symbol"
            onChange={(event) => setSymbol(event.target.value)}
            placeholder="VNM.VN"
            value={symbol}
          />
          <small>{formError ?? 'Vietnam symbols must end in .VN.'}</small>
        </label>
        <div className="form-actions">
          <button className="button button--primary" disabled={isMutating} type="submit">
            <Plus aria-hidden="true" size={17} strokeWidth={2.2} />
            Add to watchlist
          </button>
        </div>
      </form>

      <section className="workbench" aria-label="Watchlist symbols">
        {isLoading ? (
          <div className="empty-frame" aria-busy="true" aria-label="Loading watchlist">
            <div className="empty-frame__copy"><h2>Loading watchlist</h2><p>Your secure watchlist is being retrieved.</p></div>
          </div>
        ) : watchlistSymbols.length === 0 ? (
          <div className="empty-frame">
            <div className="empty-frame__mark" aria-hidden="true"><Eye size={28} strokeWidth={1.5} /></div>
            <div className="empty-frame__copy">
              <h2>No symbols on your watchlist</h2>
              <p>Add a `.VN` symbol above to keep it separate from your actual holdings.</p>
            </div>
          </div>
        ) : (
          <ul className="watchlist" aria-label="Saved watchlist symbols">
            {watchlistSymbols.map((watchSymbol) => {
              const run = latestAnalysisFor(watchSymbol);
              const requestState = analysisRequestStateFor(watchSymbol);
              const analysisLabel = run
                ? `Analysis: ${run.status}`
                : 'Analysis: Never analysed';
              const analysisNote = run?.summary
                ?? (run?.status === 'failed'
                  ? 'The latest analysis could not be completed. You can try again after one minute.'
                  : run
                    ? 'Analysis is running through the secure worker.'
                    : 'Request a fresh analysis through the secure worker.');

              return (
                <li className="watchlist-entry" key={watchSymbol}>
                  <div className="watchlist-entry__identity">
                    <span className="ticker-mark" aria-hidden="true">VN</span>
                    <h2>{watchSymbol}</h2>
                  </div>
                  <div className="state-list" aria-label={`${watchSymbol} data states`}>
                    <span className="state-chip"><Eye aria-hidden="true" size={14} />Quote: Missing</span>
                    <span className="state-chip state-chip--quiet"><BarChart3 aria-hidden="true" size={14} />{analysisLabel}</span>
                  </div>
                  <div className="watchlist-entry__analysis">
                    <button className="button button--secondary" type="button" disabled={requestState !== 'ready'} onClick={() => void analyzeSymbol(watchSymbol)} aria-describedby={`${watchSymbol}-analysis-note`}>
                      {requestState === 'requesting' ? 'Requesting…' : requestState === 'in-progress' ? 'Analysis in progress' : requestState === 'cooldown' ? 'Available shortly' : 'Analyze'}
                    </button>
                    <p id={`${watchSymbol}-analysis-note`}>{analysisNote}</p>
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
