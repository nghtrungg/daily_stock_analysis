'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import {
  BarChart3,
  Eye,
  Plus,
  WalletCards
} from 'lucide-react';
import { AppShell } from '../../components/app-shell';
import { formatVnd } from '../../lib/money';
import { usePortfolio } from '../portfolio/portfolio-provider';

type TransactionFields = {
  symbol: string;
  quantity: number;
  unitPriceVnd: number;
  feeVnd: number;
};

function StateChip({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'quiet' }) {
  return <span className={`state-chip state-chip--${tone}`}>{children}</span>;
}

export function DashboardPage() {
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const { addBuyTransaction, analysisRequestStateFor, errorMessage, isLoading, isMutating, latestAnalysisFor, positions, requestAnalysis, totalCostVnd } = usePortfolio();
  const {
    formState: { errors },
    handleSubmit,
    register,
    reset
  } = useForm<TransactionFields>({
    defaultValues: { symbol: '', quantity: undefined, unitPriceVnd: undefined, feeVnd: 0 }
  });

  function closeForm() {
    setIsFormOpen(false);
    setFormError(null);
  }

  async function saveTransaction(fields: TransactionFields) {
    try {
      await addBuyTransaction(fields);
      closeForm();
      reset();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Transaction could not be saved.');
    }
  }

  async function analyzeSymbol(symbol: string) {
    try {
      await requestAnalysis(symbol);
    } catch {
      // The shared provider renders a user-safe error below the holdings list.
    }
  }

  return (
    <AppShell
      activePath="/"
      action={(
        <button className="button button--primary" disabled={isMutating} type="button" onClick={() => setIsFormOpen(true)}>
          <Plus aria-hidden="true" size={17} strokeWidth={2.2} />
          <span>Add transaction</span>
        </button>
      )}
    >

      <section className="portfolio-lead" aria-labelledby="dashboard-title">
        <div>
          <p className="utility-label">Personal portfolio · VND</p>
          <h1 id="dashboard-title">Portfolio at a glance</h1>
        </div>
        <p className="lead-copy">Record the ledger first. This view calculates cost from your transactions and keeps absent market data visibly absent.</p>
      </section>

      <section className="summary-grid" aria-label="Portfolio summary">
        <article className="summary-card summary-card--emphasis">
          <span>Total cost</span>
          <strong>{formatVnd(totalCostVnd)}</strong>
          <small>From recorded buys</small>
        </article>
        <article className="summary-card">
          <span>Market value</span>
          <strong>—</strong>
          <small>Quote unavailable</small>
        </article>
        <article className="summary-card">
          <span>Unrealised P/L</span>
          <strong>—</strong>
          <small>Needs a current quote</small>
        </article>
      </section>

      <section className="workbench" aria-labelledby="holdings-title">
        <div className="section-heading">
          <div>
            <p className="utility-label">Current positions</p>
            <h2 id="holdings-title">Holdings</h2>
          </div>
          <span className="local-indicator">{isLoading ? 'Syncing' : 'Secure sync'}</span>
        </div>

        {positions.length === 0 ? (
          <section className="empty-frame" aria-label="Empty portfolio">
            <div className="empty-frame__mark" aria-hidden="true"><WalletCards size={28} strokeWidth={1.5} /></div>
            <div className="empty-frame__copy">
              <h3>No holdings yet</h3>
              <p>Your first buy creates a holding and calculates its weighted-average cost.</p>
            </div>
            <div className="state-list" aria-label="Data states">
              <StateChip><Eye aria-hidden="true" size={14} />Quote: Missing</StateChip>
              <StateChip tone="quiet"><BarChart3 aria-hidden="true" size={14} />Analysis: Never analysed</StateChip>
            </div>
            <button className="button button--secondary" disabled={isMutating} type="button" onClick={() => setIsFormOpen(true)}>
              Add transaction
            </button>
          </section>
        ) : (
          <div className="holding-list" aria-label="Holdings">
            {positions.map((position) => {
              const run = latestAnalysisFor(position.symbol);
              const requestState = analysisRequestStateFor(position.symbol);
              const analysisLabel = run ? `Analysis: ${run.status}` : 'Analysis: Never analysed';
              const analysisNote = run?.summary
                ?? (run?.status === 'failed'
                  ? 'The latest analysis could not be completed. You can try again after one minute.'
                  : run
                    ? 'Analysis is running through the secure worker.'
                    : 'Request a fresh analysis through the secure worker.');

              return (
              <article className="holding-frame" key={position.symbol}>
                <div className="holding-frame__identity">
                  <span className="ticker-mark" aria-hidden="true">VN</span>
                  <div>
                    <h3>{position.symbol}</h3>
                    <p>Holding · {position.quantity} shares</p>
                  </div>
                </div>
                <dl className="holding-frame__metrics">
                  <div><dt>Average cost</dt><dd>{formatVnd(position.averageCostVnd)}</dd></div>
                  <div><dt>Market value</dt><dd>—</dd></div>
                </dl>
                <div className="holding-frame__states">
                  <StateChip><Eye aria-hidden="true" size={14} />Quote: Missing</StateChip>
                  <StateChip tone="quiet"><BarChart3 aria-hidden="true" size={14} />{analysisLabel}</StateChip>
                </div>
                <button className="button button--secondary" type="button" disabled={requestState !== 'ready'} onClick={() => void analyzeSymbol(position.symbol)} aria-describedby={`${position.symbol}-analysis-note`}>
                  {requestState === 'requesting' ? 'Requesting…' : requestState === 'in-progress' ? 'Analysis in progress' : requestState === 'cooldown' ? 'Available shortly' : 'Analyze'}
                </button>
                <p className="disabled-note" id={`${position.symbol}-analysis-note`}>{analysisNote}</p>
              </article>
              );
            })}
          </div>
        )}
        {errorMessage && <p className="form-error" role="alert">{errorMessage}</p>}
      </section>

      {isFormOpen && (
        <section className="form-frame" aria-label="New buy transaction">
          <div className="form-frame__heading">
            <div>
              <p className="utility-label">New ledger entry</p>
              <h2>Add a buy transaction</h2>
            </div>
            <button className="text-button" type="button" onClick={closeForm}>Close</button>
          </div>
          <form className="transaction-form" noValidate onSubmit={handleSubmit(saveTransaction)}>
            <label>
              <span>Symbol</span>
              <input aria-invalid={Boolean(errors.symbol)} aria-label="Symbol" placeholder="VNM.VN" {...register('symbol', { required: 'Enter a .VN symbol.' })} />
              <small>{errors.symbol?.message ?? 'Vietnam symbols must end in .VN.'}</small>
            </label>
            <label>
              <span>Quantity</span>
              <input aria-invalid={Boolean(errors.quantity)} aria-label="Quantity" inputMode="numeric" min="1" type="number" {...register('quantity', { min: { value: 1, message: 'Quantity must be at least 1.' }, required: 'Enter a quantity.', valueAsNumber: true })} />
              <small>{errors.quantity?.message ?? 'Whole shares only for this local preview.'}</small>
            </label>
            <label>
              <span>Unit price (VND)</span>
              <input aria-invalid={Boolean(errors.unitPriceVnd)} aria-label="Unit price (VND)" inputMode="numeric" min="1" type="number" {...register('unitPriceVnd', { min: { value: 1, message: 'Price must be greater than zero.' }, required: 'Enter a unit price.', valueAsNumber: true })} />
              <small>{errors.unitPriceVnd?.message ?? 'Use the execution price in VND.'}</small>
            </label>
            <label>
              <span>Fees (VND)</span>
              <input aria-invalid={Boolean(errors.feeVnd)} aria-label="Fees (VND)" inputMode="numeric" min="0" type="number" {...register('feeVnd', { min: { value: 0, message: 'Fees cannot be negative.' }, valueAsNumber: true })} />
              <small>{errors.feeVnd?.message ?? 'Optional. Fees are included in the average cost.'}</small>
            </label>
            {formError && <p className="form-error" role="alert">{formError}</p>}
            <div className="form-actions">
              <button className="button button--primary" disabled={isMutating} type="submit">Save transaction</button>
              <button className="button button--secondary" disabled={isMutating} type="button" onClick={closeForm}>Cancel</button>
            </div>
          </form>
        </section>
      )}

    </AppShell>
  );
}
