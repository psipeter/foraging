// db.ts -- the one thing the handlers need from the database: call a function of the `server` schema
// (supabase/migrations/20261029000100_online_functions.sql) with positional arguments and get its jsonb result.
// The Edge Functions connect directly (SUPABASE_DB_URL, which Supabase provides to every Edge Function); if that ever
// has to change, only this file does.

import postgres from 'npm:postgres@3.4.9';

export interface Db {
  call(fn: string, args: unknown[]): Promise<any>;
}

export class DbError extends Error {
  constructor(public code: string, message: string) {
    super(message);
  }
}

let shared: ReturnType<typeof postgres> | null = null;

export function getDb(url = Deno.env.get('SUPABASE_DB_URL') ?? Deno.env.get('FORAGING_DB_URL')): Db {
  // Without a URL the libpq variables (PGHOST, PGUSER, PGDATABASE, ...) are used; the local tests reach a unix socket that way.
  if (!url && !Deno.env.get('PGHOST')) throw new Error('SUPABASE_DB_URL is not set');
  // prepare: false because the pooled connection is in transaction mode; max 1 because each isolate serves one request at a time.
  const options = { max: 1, prepare: false, onnotice: () => {} };
  shared ??= url ? postgres(url, options) : postgres(options);
  const sql = shared;
  return {
    async call(fn, args) {
      if (!/^server\.[a-z_]+$/.test(fn)) throw new Error('bad function name');
      // objects and arrays are jsonb: the driver serializes them itself once the cast tells it the parameter's type
      const params = args.map((a, i) => `$${i + 1}${typeof a === 'object' && a !== null ? '::jsonb' : ''}`).join(', ');
      try {
        const rows = await sql.unsafe(`select ${fn}(${params}) as result`, args as any);
        return rows[0].result;
      } catch (e: any) {
        throw new DbError(String(e?.code ?? ''), String(e?.message ?? e));
      }
    },
  };
}
