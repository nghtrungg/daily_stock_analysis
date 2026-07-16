import "@supabase/functions-js/edge-runtime.d.ts";
import { withSupabase } from "@supabase/server";
import { createGithubWorkflowDispatch, readGithubDispatchConfig } from "../../../src/lib/analysis/github-dispatch.ts";

const vietnamSymbol = /^[A-Z0-9]{1,10}[.]VN$/;

type ApiErrorCode =
  | "ACTIVE_RUN_EXISTS"
  | "COOLDOWN_ACTIVE"
  | "DISPATCH_FAILED"
  | "NOT_WATCHED"
  | "ORIGIN_NOT_ALLOWED"
  | "VALIDATION_ERROR"
  | "WORKER_NOT_CONFIGURED";

function json(body: unknown, status = 200, headers: HeadersInit = {}) {
  return Response.json(body, {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

function error(code: ApiErrorCode, message: string, status: number, headers: HeadersInit = {}) {
  return json({ error: { code, message } }, status, headers);
}

function corsHeaders(origin: string | null) {
  const allowedOrigin = Deno.env.get("APP_ORIGIN") ?? "http://localhost:3000";

  if (origin && origin !== allowedOrigin) {
    return null;
  }

  return {
    "Access-Control-Allow-Origin": allowedOrigin,
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    Vary: "Origin",
  };
}

function canonicaliseSymbol(input: unknown) {
  if (typeof input !== "string") {
    return null;
  }

  const symbol = input.trim().toUpperCase();
  return vietnamSymbol.test(symbol) ? symbol : null;
}

function databaseErrorCode(error: { code?: string; message?: string }) {
  if (error.message?.includes("ANALYSIS_COOLDOWN_ACTIVE")) {
    return "COOLDOWN_ACTIVE" as const;
  }

  if (error.code === "23505") {
    return "ACTIVE_RUN_EXISTS" as const;
  }

  return null;
}

export default {
  fetch: withSupabase({ auth: "user" }, async (request, ctx) => {
    const cors = corsHeaders(request.headers.get("Origin"));

    if (!cors) {
      return error("ORIGIN_NOT_ALLOWED", "This application origin is not allowed.", 403);
    }

    if (request.method === "OPTIONS") {
      return new Response("ok", { headers: cors });
    }

    if (request.method !== "POST") {
      return error("VALIDATION_ERROR", "Use POST to request analysis.", 405, cors);
    }

    let payload: { symbol?: unknown };

    try {
      payload = await request.json();
    } catch {
      return error("VALIDATION_ERROR", "Send a JSON request body.", 400, cors);
    }

    const symbol = canonicaliseSymbol(payload.symbol);

    if (!symbol) {
      return error("VALIDATION_ERROR", "Symbol must use the .VN suffix.", 422, cors);
    }

    const userId = ctx.userClaims?.id;

    if (!userId) {
      return error("VALIDATION_ERROR", "A verified user is required.", 401, cors);
    }

    const [{ data: watchlist, error: watchlistError }, { data: holding, error: holdingError }] = await Promise.all([
      ctx.supabase.from("watchlist_symbols").select("id").eq("symbol", symbol).limit(1).maybeSingle(),
      ctx.supabase.from("portfolio_transactions").select("id").eq("symbol", symbol).limit(1).maybeSingle(),
    ]);

    if (watchlistError || holdingError) {
      return error("DISPATCH_FAILED", "Analysis could not be prepared. Try again shortly.", 500, cors);
    }

    if (!watchlist && !holding) {
      return error("NOT_WATCHED", "Add this symbol to your watchlist or portfolio before analysing it.", 422, cors);
    }

    const githubDispatch = readGithubDispatchConfig({
      GITHUB_ACTIONS_DISPATCH_TOKEN: Deno.env.get("GITHUB_ACTIONS_DISPATCH_TOKEN"),
      GITHUB_REPOSITORY: Deno.env.get("GITHUB_REPOSITORY"),
      GITHUB_WORKFLOW_FILE: Deno.env.get("GITHUB_WORKFLOW_FILE"),
      GITHUB_WORKFLOW_REF: Deno.env.get("GITHUB_WORKFLOW_REF"),
    });

    if (!githubDispatch) {
      return error("WORKER_NOT_CONFIGURED", "Analysis is temporarily unavailable.", 503, cors);
    }

    const { data: run, error: createRunError } = await ctx.supabaseAdmin
      .from("analysis_runs")
      .insert({ user_id: userId, symbol, status: "queued" })
      .select("id, status, requested_at")
      .single();

    if (createRunError) {
      const code = databaseErrorCode(createRunError);
      if (code === "COOLDOWN_ACTIVE") {
        return error(code, "Wait a minute before analysing this symbol again.", 429, cors);
      }
      if (code === "ACTIVE_RUN_EXISTS") {
        return error(code, "An analysis request is already in progress.", 409, cors);
      }
      return error("DISPATCH_FAILED", "Analysis could not be prepared. Try again shortly.", 500, cors);
    }

    const dispatchRequest = createGithubWorkflowDispatch(githubDispatch, symbol, run.id);

    try {
      const workerResponse = await fetch(dispatchRequest.url, {
        method: "POST",
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: `Bearer ${githubDispatch.token}`,
          "Content-Type": "application/json",
          "X-GitHub-Api-Version": "2026-03-10",
        },
        body: JSON.stringify(dispatchRequest.body),
        signal: AbortSignal.timeout(10_000),
      });

      if (!workerResponse.ok) {
        throw new Error("GitHub Actions rejected the dispatch.");
      }
    } catch {
      await ctx.supabaseAdmin
        .from("analysis_runs")
        .update({ status: "failed", error_code: "DISPATCH_FAILED", completed_at: new Date().toISOString(), updated_at: new Date().toISOString() })
        .eq("id", run.id)
        .eq("status", "queued");

      return error("DISPATCH_FAILED", "Analysis could not be started. Try again shortly.", 502, cors);
    }

    await ctx.supabaseAdmin
      .from("analysis_runs")
      .update({ status: "dispatched", updated_at: new Date().toISOString() })
      .eq("id", run.id)
      .eq("status", "queued");

    return json({ runId: run.id, status: "dispatched" }, 202, cors);
  }),
};
