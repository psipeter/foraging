// handlers.ts -- the endpoints as functions of (db, body): validation, chunk decoding, calling the SQL. No HTTP
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
const MAX_FEEDBACK = 5000;
// Mirror of IdPattern in Assets/Scripts/Session/ConsentScreen.cs.
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

function uuid(body: Body, key: string): string {
  const id = str(body, key, 36) as string;
  if (!/^[0-9a-f-]{36}$/.test(id)) bad(`${key} must be a UUID`);
  return id;
}

const runId = (body: Body) => uuid(body, 'run_id');

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
  if (['unknown_build', 'unknown_world', 'unknown_experiment', 'prerequisite_unmet', 'reduced_run_not_allowed'].includes(e.message)) return new HttpError(403, e.message);
  if (CONFLICTS.includes(e.message)) return new HttpError(409, e.message);
  if (/^2[23]/.test(e.code)) return new HttpError(400, 'invalid', 'a field has the wrong type, is missing or violates a constraint');
  console.error('database error', e.code, e.message);
  return new HttpError(500, 'internal');
}

function build(body: Body) {
  const b = body.build as Body;
  if (typeof b !== 'object' || b === null || Array.isArray(b)) bad('build is required');
  return {
    commit: str(b, 'commit', 64),
    dirty: b.dirty === true,
    platform: str(b, 'platform', 64, false),
    unity_version: str(b, 'unity_version', 64, false),
  };
}

const participantId = (body: Body) => uuid(body, 'participant_id');

// {build, prolific_pid?, consent_version?, consent?: {version, signature, at}} logs a participant in (a returning Prolific ID gets a fresh
// token) and returns {participant_id, token, experiments: [{code, title, n_sessions, status, sessions_done, unlocked}]}. With a consent
// version (or a consent) the server asks for the signature of a participant who has none of that version on file: {needs_consent: true},
// nothing issued. Without either, no consent is asked (a development build with no consent screen).
export function participantStart(db: Db, body: Body) {
  return guarded(async () => {
    const clean = build(body);
    const pid = str(body, 'prolific_pid', 64, false);
    if (pid !== null && !PID.test(pid)) bad('prolific_pid has unexpected characters');
    let consent = null;
    if (body.consent !== undefined && body.consent !== null) {
      const c = body.consent as Body;
      if (typeof c !== 'object' || Array.isArray(c)) bad('consent must be an object');
      const at = str(c, 'at', 40, false);
      if (at !== null && Number.isNaN(Date.parse(at))) bad('consent.at is not a time');
      consent = { version: str(c, 'version', 100), signature: str(c, 'signature', 200), at };
    }
    const version = consent ? consent.version : str(body, 'consent_version', 100, false);
    const token = newToken();
    const result = await db.call('server.start_participant', [await sha256Hex(token), clean, pid, version, consent]);
    return result.needs_consent ? result : { ...result, token };
  });
}

// {build, participant_id, participant_token, experiment, expected_sessions?} starts the participant's run of an experiment, or continues the unfinished one
// (the participant must satisfy its prerequisites). `expected_sessions` declares a reduced run (a development build playing fewer sessions, see
// docs/DECISIONS.md "Reduced runs"): how many sessions (practice, sessions, Interludes) it will have; only a build registered as a development release may
// send it (403 reduced_run_not_allowed). Returns {run_id, token, status, experiment, resume, has_resume}; a finished run has no token but the
// experiment's completion code.
export function runStart(db: Db, body: Body) {
  return guarded(async () => {
    const clean = build(body);
    const experiment = str(body, 'experiment', 32) as string;
    if (!/^[A-Za-z0-9]{1,32}$/.test(experiment)) bad('experiment has unexpected characters');
    const participantHash = await sha256Hex(str(body, 'participant_token', 100) as string);
    const expected = body.expected_sessions ?? null;
    if (expected !== null && (!Number.isInteger(expected) || (expected as number) < 1 || (expected as number) > 1000)) bad('expected_sessions must be an integer from 1 to 1000');
    const token = newToken();
    const result = await db.call('server.start_run', [await sha256Hex(token), participantId(body), participantHash, experiment, clean, expected]);
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

// {run_id, token} -> {ok, problems, completion_code, points}; ok marks the run finished. The completion code is null unless ok (decided in SQL).
export function runFinish(db: Db, body: Body) {
  return guarded(async () => {
    const hash = await sha256Hex(str(body, 'token', 100) as string);
    return await db.call('server.finish_run', [runId(body), hash]);
  });
}

// {run_id, token, text} -> {ok}; the participant's free-text feedback (one per run, a second one replaces it). Allowed after the run is finished.
// `token` is the run's token or the token of the participant the run belongs to.
export function saveFeedback(db: Db, body: Body) {
  return guarded(async () => {
    const text = str(body, 'text', MAX_FEEDBACK) as string;
    const hash = await sha256Hex(str(body, 'token', 100) as string);
    await db.call('server.save_feedback', [runId(body), hash, text]);
    return { ok: true };
  });
}
