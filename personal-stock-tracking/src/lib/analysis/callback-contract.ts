const runIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const timezoneSuffixPattern = /(?:Z|[+-]\d{2}:\d{2})$/i;
const failureCodes = new Set(['SOURCE_UNAVAILABLE', 'PROCESSING_FAILED', 'QUOTE_UNAVAILABLE']);
type AnalysisFailureCode = 'SOURCE_UNAVAILABLE' | 'PROCESSING_FAILED' | 'QUOTE_UNAVAILABLE';

export type AnalysisCallback = {
  runId: string;
  status: 'succeeded';
  summary: string;
  quote: { currentPriceVnd: number; asOf: string; source: string };
} | {
  runId: string;
  status: 'failed';
  errorCode: AnalysisFailureCode;
};

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('callback must be an object');
  return value as Record<string, unknown>;
}

function exactKeys(value: Record<string, unknown>, allowed: readonly string[]) {
  const allowedKeys = new Set(allowed);
  if (Object.keys(value).some((key) => !allowedKeys.has(key)) || Object.keys(value).length !== allowed.length) {
    throw new Error('callback contains missing or unknown fields');
  }
}

export function parseAnalysisCallback(input: unknown): AnalysisCallback {
  const payload = record(input);
  if (typeof payload.runId !== 'string' || !runIdPattern.test(payload.runId)) throw new Error('runId is invalid');

  if (payload.status === 'succeeded') {
    exactKeys(payload, ['runId', 'status', 'summary', 'quote']);
    if (typeof payload.summary !== 'string' || payload.summary.trim().length === 0 || payload.summary.length > 4_000) {
      throw new Error('summary is invalid');
    }
    const quote = record(payload.quote);
    exactKeys(quote, ['currentPriceVnd', 'asOf', 'source']);
    if (!Number.isSafeInteger(quote.currentPriceVnd) || Number(quote.currentPriceVnd) <= 0) throw new Error('currentPriceVnd is invalid');
    if (typeof quote.asOf !== 'string'
      || quote.asOf.length > 64
      || !timezoneSuffixPattern.test(quote.asOf)
      || Number.isNaN(Date.parse(quote.asOf))) throw new Error('quote asOf is invalid');
    if (typeof quote.source !== 'string' || quote.source.trim().length === 0 || quote.source.length > 120) throw new Error('quote source is invalid');
    return {
      runId: payload.runId,
      status: 'succeeded',
      summary: payload.summary.trim(),
      quote: { currentPriceVnd: Number(quote.currentPriceVnd), asOf: quote.asOf, source: quote.source.trim() }
    };
  }

  if (payload.status === 'failed') {
    exactKeys(payload, ['runId', 'status', 'errorCode']);
    if (typeof payload.errorCode !== 'string' || !failureCodes.has(payload.errorCode)) throw new Error('errorCode is invalid');
    return { runId: payload.runId, status: 'failed', errorCode: payload.errorCode as AnalysisFailureCode };
  }

  throw new Error('callback status is invalid');
}
