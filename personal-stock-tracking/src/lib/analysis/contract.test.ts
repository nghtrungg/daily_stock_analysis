import { describe, expect, it } from '@jest/globals';
import { parseAnalysisCallback, parseAnalysisRequest } from './contract';

const runId = 'a59a1476-2ea4-4c86-9a3c-d0df438e8102';
const quote = { currentPriceVnd: 68400, asOf: '2026-07-16T15:10:00+07:00', source: 'realtime:tencent' };

describe('analysis request contract', () => {
  it('canonicalises a valid Vietnam symbol before dispatch', () => {
    expect(parseAnalysisRequest({ symbol: '  vnm.vn ' })).toEqual({ symbol: 'VNM.VN' });
  });

  it('rejects a symbol outside the approved Vietnam market scope', () => {
    expect(() => parseAnalysisRequest({ symbol: 'VNM' })).toThrow('symbol must use the .VN suffix');
  });
});

describe('analysis callback contract', () => {
  it('accepts a successful run only with a complete timestamped VND quote', () => {
    expect(parseAnalysisCallback({ runId, status: 'succeeded', summary: 'Phân tích đã hoàn tất.', quote })).toEqual({
      runId, status: 'succeeded', summary: 'Phân tích đã hoàn tất.', quote
    });
  });

  it.each([
    { runId, status: 'succeeded', summary: 'Xong' },
    { runId, status: 'succeeded', summary: 'Xong', quote: { ...quote, currentPriceVnd: 0 } },
    { runId, status: 'succeeded', summary: 'Xong', quote: { ...quote, currentPriceVnd: 68400.5 } },
    { runId, status: 'succeeded', summary: 'Xong', quote: { ...quote, asOf: 'not-a-time' } },
    { runId, status: 'succeeded', summary: 'Xong', quote: { ...quote, asOf: '2026-07-16T15:10:00' } },
    { runId, status: 'succeeded', summary: 'Xong', quote: { ...quote, source: ' ' } },
    { runId, status: 'succeeded', summary: 'Xong', quote, privateReport: 'không được phép' }
  ])('rejects malformed or over-broad success callbacks', (payload) => {
    expect(() => parseAnalysisCallback(payload)).toThrow();
  });

  it('preserves existing failures and adds a safe quote-unavailable result', () => {
    expect(parseAnalysisCallback({ runId, status: 'failed', errorCode: 'SOURCE_UNAVAILABLE' })).toEqual({ runId, status: 'failed', errorCode: 'SOURCE_UNAVAILABLE' });
    expect(parseAnalysisCallback({ runId, status: 'failed', errorCode: 'QUOTE_UNAVAILABLE' })).toEqual({ runId, status: 'failed', errorCode: 'QUOTE_UNAVAILABLE' });
    expect(() => parseAnalysisCallback({ runId, status: 'failed', errorCode: 'WORKER_STACK_TRACE' })).toThrow();
  });
});
