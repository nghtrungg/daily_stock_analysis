'use client';

import { ArrowDownRight, ArrowUpRight, BarChart3, Eye, Minus } from 'lucide-react';
import { formatVietnamDateTime } from '../../lib/datetime';
import { formatVnd } from '../../lib/money';
import type { ValuedPosition } from '../../lib/quotes';
import { analysisActionLabel, analysisNote, analysisStatusLabel } from './analysis-messages';
import type { AnalysisRun } from './portfolio-store';

function ProfitLoss({ amount, percent }: { amount: number | null; percent: number | null }) {
  if (amount === null) return <span className="profit-loss profit-loss--neutral"><Minus aria-hidden="true" size={15} /> Chưa có giá</span>;
  const tone = amount > 0 ? 'positive' : amount < 0 ? 'negative' : 'neutral';
  const Icon = amount > 0 ? ArrowUpRight : amount < 0 ? ArrowDownRight : Minus;
  const label = amount > 0 ? 'Lãi' : amount < 0 ? 'Lỗ' : 'Hòa vốn';
  return <span className={`profit-loss profit-loss--${tone}`}><Icon aria-hidden="true" size={15} /> {label} {formatVnd(Math.abs(amount))}{percent === null ? '' : ` (${Math.abs(percent).toLocaleString('vi-VN', { maximumFractionDigits: 2 })}%)`}</span>;
}

type PositionCardProps = {
  position: ValuedPosition;
  run?: AnalysisRun;
  requestState?: 'ready' | 'requesting' | 'in-progress' | 'cooldown';
  onAnalyze?: () => void;
  onSell: () => void;
};

export function PositionCard({ position, run, requestState = 'ready', onAnalyze, onSell }: PositionCardProps) {
  return (
    <article className="holding-frame">
      <div className="holding-frame__identity">
        <span className="ticker-mark" aria-hidden="true">VN</span>
        <div><h3>{position.symbol}</h3><p>Nắm giữ · {position.quantity.toLocaleString('vi-VN')} cổ phiếu</p></div>
      </div>
      <dl className="holding-frame__metrics">
        <div><dt>Giá vốn bình quân</dt><dd>{formatVnd(position.averageCostVnd)}</dd></div>
        <div><dt>Giá gần nhất</dt><dd>{position.quote ? formatVnd(position.quote.currentPriceVnd) : '—'}</dd></div>
        <div><dt>Giá trị thị trường</dt><dd>{position.marketValueVnd === null ? '—' : formatVnd(position.marketValueVnd)}</dd></div>
        <div><dt>Lãi/lỗ chưa thực hiện</dt><dd><ProfitLoss amount={position.unrealizedProfitLossVnd} percent={position.unrealizedProfitLossPercent} /></dd></div>
      </dl>
      <div className="holding-frame__states">
        <span className="state-chip"><Eye aria-hidden="true" size={14} />{position.quoteState === 'missing' ? 'Giá: Chưa có' : position.quoteState === 'stale' ? 'Giá: Đã cũ' : 'Giá: Mới'}</span>
        <span className="state-chip state-chip--quiet"><BarChart3 aria-hidden="true" size={14} />Phân tích: {analysisStatusLabel(run)}</span>
      </div>
      {position.quote && <p className="quote-provenance">Nguồn {position.quote.source} · {formatVietnamDateTime(position.quote.asOf)}{position.quoteState === 'stale' ? ' · Đã cũ, nên phân tích lại.' : ''}</p>}
      <div className="holding-frame__actions">
        {onAnalyze && <button className="button button--secondary" type="button" disabled={requestState !== 'ready'} onClick={onAnalyze}>{analysisActionLabel(requestState)}</button>}
        <button className="button button--secondary" type="button" onClick={onSell}>Bán</button>
      </div>
      {onAnalyze && <p className="disabled-note">{analysisNote(run)}</p>}
    </article>
  );
}
