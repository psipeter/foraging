// serve.ts -- the three Edge Functions on a local port, without the Supabase platform (no Docker needed):
//   FORAGING_DB_URL=postgresql://... SUPABASE_ANON_KEY=testkey PORT=54399 deno run -A supabase/local/serve.ts
// Paths /run-start, /append and /run-finish, as the deployed functions are under /functions/v1/.

import { routes } from '../functions/_shared/routes.ts';

const port = Number(Deno.env.get('PORT') ?? 54399);
Deno.serve({ port, hostname: '127.0.0.1', onListen: () => console.log(`listening on ${port}`) }, (req) => {
  const name = new URL(req.url).pathname.split('/').filter(Boolean).pop() ?? '';
  const handler = routes[name];
  return handler ? handler(req) : Promise.resolve(new Response('not found', { status: 404 }));
});
