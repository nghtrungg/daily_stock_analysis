import { z } from 'zod';
import { requireVietnamSymbol } from '../symbols';

const analysisRequestSchema = z.object({
  symbol: z.string().trim().min(1)
});

const analysisCallbackSchema = z.discriminatedUnion('status', [
  z.object({
    runId: z.uuid(),
    status: z.literal('succeeded'),
    summary: z.string().trim().min(1).max(4_000)
  }),
  z.object({
    runId: z.uuid(),
    status: z.literal('failed'),
    errorCode: z.enum(['SOURCE_UNAVAILABLE', 'PROCESSING_FAILED'])
  })
]);

export type AnalysisCallback = z.infer<typeof analysisCallbackSchema>;

export function parseAnalysisRequest(input: unknown) {
  const request = analysisRequestSchema.parse(input);

  return { symbol: requireVietnamSymbol(request.symbol) };
}

export function parseAnalysisCallback(input: unknown): AnalysisCallback {
  return analysisCallbackSchema.parse(input);
}
