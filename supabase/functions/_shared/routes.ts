// routes.ts -- the five endpoints wired to the database; each function's index.ts and the local server (local/serve.ts)
// use these, so what is tested locally is what is deployed.

import { getDb } from './db.ts';
import { append, participantStart, runFinish, runStart, saveFeedback } from './handlers.ts';
import { serve } from './http.ts';

export const routes: Record<string, (req: Request) => Promise<Response>> = {
  'participant-start': serve((body) => participantStart(getDb(), body)),
  'run-start': serve((body) => runStart(getDb(), body)),
  'append': serve((body) => append(getDb(), body)),
  'run-finish': serve((body) => runFinish(getDb(), body)),
  'feedback': serve((body) => saveFeedback(getDb(), body)),
};
