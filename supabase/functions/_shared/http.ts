// http.ts -- the HTTP layer shared by the three functions: CORS on every response (a 500 without it looks like a network
// failure to a browser), the apikey filter, JSON in and out, and the error mapping. The functions are deployed with
// verify_jwt = false (config.toml), as in evidence_integration; the apikey header only filters out callers that are not our
// own client, the per-run token is what protects the data.

import { HttpError } from './handlers.ts';

const MAX_BODY_BYTES = 4_000_000;

function corsHeaders(): Record<string, string> {
  return {
    'Access-Control-Allow-Origin': Deno.env.get('ALLOWED_ORIGIN') ?? '*',
    'Access-Control-Allow-Headers': 'apikey, content-type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
  };
}

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...corsHeaders() } });
}

function expectedKey(): string {
  const raw = Deno.env.get('SUPABASE_PUBLISHABLE_KEYS');
  if (raw) {
    try {
      const parsed = JSON.parse(raw);
      if (parsed?.default) return parsed.default;
    } catch { /* fall through */ }
  }
  return Deno.env.get('SUPABASE_ANON_KEY') ?? '';
}

export function serve(run: (body: Record<string, unknown>) => Promise<unknown>): (req: Request) => Promise<Response> {
  return async (req) => {
    if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders() });
    const key = expectedKey();
    if (!key || req.headers.get('apikey') !== key) return respond({ error: 'unauthorized' }, 401);
    if (req.method !== 'POST') return respond({ error: 'method not allowed' }, 405);
    try {
      const text = await req.text();
      if (text.length > MAX_BODY_BYTES) throw new HttpError(413, 'too_large');
      let body: unknown;
      try {
        body = JSON.parse(text);
      } catch {
        throw new HttpError(400, 'invalid', 'invalid JSON body');
      }
      if (typeof body !== 'object' || body === null || Array.isArray(body)) throw new HttpError(400, 'invalid', 'the body must be a JSON object');
      return respond(await run(body as Record<string, unknown>));
    } catch (e) {
      if (e instanceof HttpError) return respond({ error: e.code, message: e.message }, e.status);
      console.error('unhandled error', e);
      return respond({ error: 'internal' }, 500);
    }
  };
}
