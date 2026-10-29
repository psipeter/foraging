// routes.ts -- the three endpoints wired to the database; each function's index.ts and the local server (local/serve.ts)
// use these, so what is tested locally is what is deployed.

import { getDb } from './db.ts';
import { append, runFinish, runStart } from './handlers.ts';
import { serve } from './http.ts';

export const routes: Record<string, (req: Request) => Promise<Response>> = {
  'run-start': serve((body) => runStart(getDb(), body)),
  'append': serve((body) => append(getDb(), body)),
  'run-finish': serve((body) => runFinish(getDb(), body)),
};
