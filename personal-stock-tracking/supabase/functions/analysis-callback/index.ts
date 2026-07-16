import "@supabase/functions-js/edge-runtime.d.ts";
import { withSupabase } from "@supabase/server";
import { parseAnalysisCallback, type AnalysisCallback } from "../../../src/lib/analysis/callback-contract.ts";
import {
  callbackRunUpdate,
  terminalCallbackMatches,
  type StoredAnalysisRun,
} from "../../../src/lib/analysis/callback-state.ts";

type StoredRun = StoredAnalysisRun & {
  id: string;
  user_id: string;
};

function json(body: unknown, status = 200) {
  return Response.json(body, { status, headers: { "Content-Type": "application/json" } });
}

function isEqualSignature(actual: string, expected: string) {
  let difference = actual.length ^ expected.length;
  const length = Math.max(actual.length, expected.length);
  for (let index = 0; index < length; index += 1) {
    difference |= (actual.charCodeAt(index) || 0) ^ (expected.charCodeAt(index) || 0);
  }
  return difference === 0;
}

async function signBody(secret: string, body: string) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  return Array.from(new Uint8Array(signature), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export default {
  fetch: withSupabase({ auth: "none" }, async (request, ctx) => {
    if (request.method !== "POST") {
      return json({ error: { code: "VALIDATION_ERROR", message: "Use POST for worker callbacks." } }, 405);
    }

    const callbackSecret = Deno.env.get("ANALYSIS_CALLBACK_SECRET");
    const rawBody = await request.text();
    const signature = request.headers.get("x-analysis-signature") ?? "";

    if (!callbackSecret || !signature || !isEqualSignature(signature, await signBody(callbackSecret, rawBody))) {
      return json({ error: { code: "UNAUTHENTICATED", message: "Callback authentication failed." } }, 401);
    }

    let payload: AnalysisCallback;
    try {
      payload = parseAnalysisCallback(JSON.parse(rawBody));
    } catch {
      return json({ error: { code: "VALIDATION_ERROR", message: "Callback payload is invalid." } }, 422);
    }

    const fields = "id, user_id, status, summary, error_code, current_price_vnd, quote_as_of, quote_source";
    const { data: existingData, error: readError } = await ctx.supabaseAdmin
      .from("analysis_runs")
      .select(fields)
      .eq("id", payload.runId)
      .maybeSingle();
    const existing = existingData as StoredRun | null;

    if (readError) return json({ error: { code: "PROCESSING_FAILED", message: "The callback could not be recorded." } }, 500);
    if (!existing || typeof existing.user_id !== "string" || existing.user_id.length === 0) {
      return json({ error: { code: "RUN_NOT_FOUND", message: "The addressed analysis run does not exist." } }, 404);
    }
    if (existing.status === "succeeded" || existing.status === "failed") {
      return terminalCallbackMatches(existing, payload)
        ? json({ received: true, idempotent: true })
        : json({ error: { code: "CALLBACK_CONFLICT", message: "The analysis run already has a different terminal result." } }, 409);
    }

    const { data: updatedData, error: updateError } = await ctx.supabaseAdmin
      .from("analysis_runs")
      .update(callbackRunUpdate(payload, new Date().toISOString()))
      .eq("id", payload.runId)
      .eq("user_id", existing.user_id)
      .in("status", ["queued", "dispatched", "running"])
      .select("id")
      .maybeSingle();

    if (updateError) return json({ error: { code: "PROCESSING_FAILED", message: "The callback could not be recorded." } }, 500);
    if (updatedData) return json({ received: true, idempotent: false });

    // A concurrent terminal callback may have won after the initial read.
    const { data: concurrentData, error: concurrentError } = await ctx.supabaseAdmin
      .from("analysis_runs")
      .select(fields)
      .eq("id", payload.runId)
      .eq("user_id", existing.user_id)
      .maybeSingle();
    const concurrent = concurrentData as StoredRun | null;
    if (concurrentError || !concurrent) {
      return json({ error: { code: "PROCESSING_FAILED", message: "The callback could not be recorded." } }, 500);
    }
    return terminalCallbackMatches(concurrent, payload)
      ? json({ received: true, idempotent: true })
      : json({ error: { code: "CALLBACK_CONFLICT", message: "The analysis run already has a different terminal result." } }, 409);
  }),
};
