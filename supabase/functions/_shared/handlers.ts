// handlers.ts -- the three endpoints as functions of (db, body): validation, chunk decoding, calling the SQL. No HTTP
// here (http.ts) and no Deno-specific database code (db.ts), so they run the same locally and deployed.

import { ChunkError, decodeChunk, fromBase64 } from './chunk.ts';
import { Db, DbError } from './db.ts';

export class HttpError extends Error {
  constructor(public status: number, public code: string, message?: string) {
    super(message ?? code);
  }
}

const MAX_EVENTS = 5000;
const MAX_CHUNKS = 50;
const MAX_TRIALS = 200;
const PID = /^[A-Za-z0-9_-]{1,64}$/;

type Body = Record<string, unknown>;

function bad(message: string): never {
  throw new HttpError(400, 'invalid', message);
}

function str(body: Body, key: string, max = 200, required = true): string | null {
  const v = body[key];
  if (v === undefined || v === null) {
    if (required) bad(`${key} is required`);
    return null;
  }
  if (typeof v !== 'string' || v.length === 0 || v.length > max) bad(`${key} must be a string of 1 to ${max} characters`);
  return v;
}

function list(body: Body, key: string, max: number): unknown[] {
  const v = body[key] ?? [];
  if (!Array.isArray(v) || v.length > max) bad(`${key} must be an array of at most ${max}`);
  return v;
}

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

function newToken(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes)).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
}

function runId(body: Body): string {
  const id = str(body, 'run_id', 36) as string;
  if (!/^[0-9a-f-]{36}$/.test(id)) bad('run_id must be a UUID');
  return id;
}

function sessionIndex(body: Body): number {
  const i = body.session_index;
  if (typeof i !== 'number' || !Number.isInteger(i) || i < 0 || i > 1000) bad('session_index must be a small non-negative integer');
  return i as number;
}

async function guarded<T>(work: () => Promise<T>): Promise<T> {
  try {
    return await work();
  } catch (e) {
    if (e instanceof HttpError) throw e;
    if (e instanceof ChunkError) throw new HttpError(400, 'invalid_chunk', e.message);
    if (e instanceof DbError) throw fromDbError(e);
    throw e;
  }
}

const CONFLICTS = ['no_session', 'session_gap', 'gap_events', 'gap_trajectory', 'overlap_trajectory', 'gap_trials'];

export function fromDbError(e: DbError): HttpError {
  if (e.message === 'unauthorized') return new HttpError(401, 'unauthorized');
  if (e.message === 'unknown_build' || e.message === 'unknown_world') return new HttpError(403, e.message);
  if (CONFLICTS.includes(e.message)) return new HttpError(409, e.message);
  if (/^2[23]/.test(e.code)) return new HttpError(400, 'invalid', 'a field has the wrong type, is missing or violates a constraint');
  console.error('database error', e.code, e.message);
  return new HttpError(500, 'internal');
}

// {build: {commit, dirty, platform, unity_version}, prolific_pid?} starts or (with a Prolific ID the server knows) continues
// a run; {run_id, token, build} continues an anonymous run. Returns {run_id, token, status, resume}; a finished run has no token.
export function runStart(db: Db, body: Body) {
  return guarded(async () => {
    const build = body.build as Body;
    if (typeof build !== 'object' || build === null) bad('build is required');
    const clean = {
      commit: str(build, 'commit', 64),
      dirty: build.dirty === true,
      platform: str(build, 'platform', 64, false),
      unity_version: str(build, 'unity_version', 64, false),
    };
    const token = newToken();
    const hash = await sha256Hex(token);
    let result;
    if (body.token !== undefined) {
      const oldHash = await sha256Hex(str(body, 'token', 100) as string);
      result = await db.call('server.resume_run', [runId(body), oldHash, hash, clean]);
    } else {
      const pid = str(body, 'prolific_pid', 64, false);
      if (pid !== null && !PID.test(pid)) bad('prolific_pid has unexpected characters');
      result = await db.call('server.start_run', [hash, clean, pid]);
    }
    return result.status === 'in_progress' ? { ...result, token, has_resume: result.resume != null } : result;
  });
}

// {run_id, token, session_index, session?, events?, trajectory?: [base64 chunk], plan?, trials?} -> {events_next, trajectory_next, trials_next}.
// A 200 means every row of the request is stored.
export function append(db: Db, body: Body) {
  return guarded(async () => {
    const rid = runId(body);
    const index = sessionIndex(body);
    const hash = await sha256Hex(str(body, 'token', 100) as string);
    const chunks = [];
    for (const item of list(body, 'trajectory', MAX_CHUNKS)) {
      if (typeof item !== 'string') bad('trajectory must be a list of base64 strings');
      const bytes = fromBase64(item);
      const c = await decodeChunk(bytes);
      chunks.push({ first_seq: c.firstSeq, n_frames: c.nFrames, t_start: c.tStart, t_end: c.tEnd, last_frame: c.last, data: item });
    }
    const batch: Body = {
      session: body.session ?? null,
      events: list(body, 'events', MAX_EVENTS),
      trajectory: chunks,
      plan: body.plan ?? null,
      trials: list(body, 'trials', MAX_TRIALS),
    };
    if (batch.session !== null && (typeof batch.session !== 'object' || Array.isArray(batch.session))) bad('session must be an object');
    if (batch.plan !== null && !Array.isArray(batch.plan)) bad('plan must be an array');
    const state = await db.call('server.append_batch', [rid, hash, index, batch]);
    return { ok: true, ...state };
  });
}

// {run_id, token} -> {ok, problems}; ok marks the run finished.
export function runFinish(db: Db, body: Body) {
  return guarded(async () => {
    const hash = await sha256Hex(str(body, 'token', 100) as string);
    return await db.call('server.finish_run', [runId(body), hash]);
  });
}
