import type { AnalysisCallback } from './callback-contract';

export type StoredAnalysisRun = {
  status: 'queued' | 'dispatched' | 'running' | 'succeeded' | 'failed';
  summary: string | null;
  error_code: string | null;
  current_price_vnd: number | null;
  quote_as_of: string | null;
  quote_source: string | null;
};

export function terminalCallbackMatches(run: StoredAnalysisRun, payload: AnalysisCallback) {
  if (run.status !== payload.status) return false;
  if (payload.status === 'failed') {
    return run.error_code === payload.errorCode
      && run.summary === null
      && run.current_price_vnd === null
      && run.quote_as_of === null
      && run.quote_source === null;
  }
  return run.summary === payload.summary
    && run.error_code === null
    && Number(run.current_price_vnd) === payload.quote.currentPriceVnd
    && run.quote_as_of !== null
    && Date.parse(run.quote_as_of) === Date.parse(payload.quote.asOf)
    && run.quote_source === payload.quote.source;
}

export function callbackRunUpdate(payload: AnalysisCallback, completedAt: string) {
  if (payload.status === 'succeeded') {
    return {
      status: 'succeeded' as const,
      summary: payload.summary,
      error_code: null,
      current_price_vnd: payload.quote.currentPriceVnd,
      quote_as_of: payload.quote.asOf,
      quote_source: payload.quote.source,
      completed_at: completedAt,
      updated_at: completedAt,
    };
  }
  return {
    status: 'failed' as const,
    summary: null,
    error_code: payload.errorCode,
    current_price_vnd: null,
    quote_as_of: null,
    quote_source: null,
    completed_at: completedAt,
    updated_at: completedAt,
  };
}
