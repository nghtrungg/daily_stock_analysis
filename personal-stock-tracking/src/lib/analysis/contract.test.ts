import { describe, expect, it } from '@jest/globals';
import { parseAnalysisCallback, parseAnalysisRequest } from './contract';

const runId = 'a59a1476-2ea4-4c86-9a3c-d0df438e8102';

describe('analysis request contract', () => {
  it('canonicalises a valid Vietnam symbol before dispatch', () => {
    expect(parseAnalysisRequest({ symbol: '  vnm.vn ' })).toEqual({ symbol: 'VNM.VN' });
  });

  it('rejects a symbol outside the approved Vietnam market scope', () => {
    expect(() => parseAnalysisRequest({ symbol: 'VNM' })).toThrow('symbol must use the .VN suffix');
  });
});

describe('analysis callback contract', () => {
  it('accepts a completed run with a bounded textual summary', () => {
    expect(parseAnalysisCallback({ runId, status: 'succeeded', summary: 'Earnings growth remains the main watch item.' })).toEqual({
      runId,
      status: 'succeeded',
      summary: 'Earnings growth remains the main watch item.'
    });
  });

  it('rejects a successful callback without an analysis summary', () => {
    expect(() => parseAnalysisCallback({ runId, status: 'succeeded' })).toThrow();
  });

  it('rejects a failed callback without an allowlisted error code', () => {
    expect(() => parseAnalysisCallback({ runId, status: 'failed', errorCode: 'WORKER_STACK_TRACE' })).toThrow();
  });
});
