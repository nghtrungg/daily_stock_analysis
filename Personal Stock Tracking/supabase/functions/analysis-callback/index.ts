import "@supabase/functions-js/edge-runtime.d.ts";
import { withSupabase } from "@supabase/server";

const runIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const errorCodes = new Set(["SOURCE_UNAVAILABLE", "PROCESSING_FAILED"]);

type CallbackPayload =
  | { runId: string; status: "succeeded"; summary: string }
  | { runId: string; status: "failed"; errorCode: "SOURCE_UNAVAILABLE" | "PROCESSING_FAILED" };

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

function parseCallback(input: unknown): CallbackPayload | null {
  if (!input || typeof input !== "object") {
    return null;
  }

  const payload = input as Record<string, unknown>;
  if (typeof payload.runId !== "string" || !runIdPattern.test(payload.runId)) {
    return null;
  }

  if (payload.status === "succeeded" && typeof payload.summary === "string") {
    const summary = payload.summary.trim();
    return summary.length > 0 && summary.length <= 4_000 ? { runId: payload.runId, status: "succeeded", summary } : null;
  }

  if (payload.status === "failed" && typeof payload.errorCode === "string" && errorCodes.has(payload.errorCode)) {
    return { runId: payload.runId, status: "failed", errorCode: payload.errorCode as "SOURCE_UNAVAILABLE" | "PROCESSING_FAILED" };
  }

  return null;
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

    let input: unknown;
    try {
      input = JSON.parse(rawBody);
    } catch {
      return json({ error: { code: "VALIDATION_ERROR", message: "Send a JSON request body." } }, 400);
    }

    const payload = parseCallback(input);
    if (!payload) {
      return json({ error: { code: "VALIDATION_ERROR", message: "Callback payload is invalid." } }, 422);
    }

    const completedAt = new Date().toISOString();
    const update = payload.status === "succeeded"
      ? { status: "succeeded", summary: payload.summary, error_code: null, completed_at: completedAt, updated_at: completedAt }
      : { status: "failed", summary: null, error_code: payload.errorCode, completed_at: completedAt, updated_at: completedAt };

    const { error } = await ctx.supabaseAdmin
      .from("analysis_runs")
      .update(update)
      .eq("id", payload.runId)
      .in("status", ["queued", "dispatched", "running"]);

    if (error) {
      return json({ error: { code: "PROCESSING_FAILED", message: "The callback could not be recorded." } }, 500);
    }

    return json({ received: true });
  }),
};
