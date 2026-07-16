import { describe, expect, it } from '@jest/globals';
import { callbackRunUpdate, terminalCallbackMatches, type StoredAnalysisRun } from './callback-state';

const completedAt = '2026-07-16T08:15:00.000Z';
const success = {
  runId: 'a59a1476-2ea4-4c86-9a3c-d0df438e8102',
  status: 'succeeded' as const,
  summary: 'Phân tích đã hoàn tất.',
  quote: { currentPriceVnd: 68400, asOf: '2026-07-16T15:10:00+07:00', source: 'realtime:tencent' }
};

describe('analysis callback terminal state', () => {
  it('builds one complete success update', () => {
    expect(callbackRunUpdate(success, completedAt)).toEqual({
      status: 'succeeded',
      summary: success.summary,
      error_code: null,
      current_price_vnd: 68400,
      quote_as_of: success.quote.asOf,
      quote_source: success.quote.source,
      completed_at: completedAt,
      updated_at: completedAt
    });
  });

  it('clears all quote fields for a failed callback', () => {
    expect(callbackRunUpdate({ runId: success.runId, status: 'failed', errorCode: 'QUOTE_UNAVAILABLE' }, completedAt)).toEqual({
      status: 'failed',
      summary: null,
      error_code: 'QUOTE_UNAVAILABLE',
      current_price_vnd: null,
      quote_as_of: null,
      quote_source: null,
      completed_at: completedAt,
      updated_at: completedAt
    });
  });

  it('accepts only an identical terminal success as idempotent', () => {
    const stored: StoredAnalysisRun = {
      status: 'succeeded', summary: success.summary, error_code: null,
      current_price_vnd: 68400, quote_as_of: '2026-07-16T08:10:00Z', quote_source: success.quote.source
    };
    expect(terminalCallbackMatches(stored, success)).toBe(true);
    expect(terminalCallbackMatches({ ...stored, current_price_vnd: 68401 }, success)).toBe(false);
  });

  it('accepts only an identical terminal failure as idempotent', () => {
    const failure = { runId: success.runId, status: 'failed' as const, errorCode: 'PROCESSING_FAILED' as const };
    const stored: StoredAnalysisRun = {
      status: 'failed', summary: null, error_code: 'PROCESSING_FAILED',
      current_price_vnd: null, quote_as_of: null, quote_source: null
    };
    expect(terminalCallbackMatches(stored, failure)).toBe(true);
    expect(terminalCallbackMatches({ ...stored, error_code: 'QUOTE_UNAVAILABLE' }, failure)).toBe(false);
  });
});
