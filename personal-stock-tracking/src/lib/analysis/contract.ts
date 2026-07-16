import { z } from 'zod';
import { requireVietnamSymbol } from '../symbols';
export { parseAnalysisCallback, type AnalysisCallback } from './callback-contract';

const analysisRequestSchema = z.object({
  symbol: z.string().trim().min(1)
});

export function parseAnalysisRequest(input: unknown) {
  const request = analysisRequestSchema.parse(input);

  return { symbol: requireVietnamSymbol(request.symbol) };
}
