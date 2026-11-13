"""Reference client of the online data server (docs/ONLINE_DATA_PLAN.md, section 3): the protocol the Unity client will
speak, in Python, so the server can be tested end to end and a stored session can be uploaded by hand.

    client = Client(url, apikey, build={"commit": "abc123", "dirty": False, "platform": "Test", "unity_version": "6000"})
    menu = client.login(prolific_pid="...", consent={"version": "v1", "signature": "...", "at": "..."})   # {"participant_id", "token", "experiments": [...]}
    started = client.start("CF")                   # {"run_id", "token", "status", "experiment", "resume"}: the run of an experiment
    client.append(0, session=row, events=[...], frames=array, first_seq=0)
    client.finish()                                # {"ok", "problems", "completion_code"}
    client.feedback("text")                        # {"ok"}

`url` is the functions' base ("https://<ref>.supabase.co/functions/v1" deployed; "http://127.0.0.1:54399" for local/serve.ts).
`upload_session` sends a session of the local layout (rundata.read_session) in batches, the way a recorder would.
"""

import base64
import json
import urllib.error
import urllib.request

import numpy as np

import trajectory_codec as codec


EXPERIMENT = "TEST"      # the experiment `Client.start` plays by default (the tests register it)


class ServerError(Exception):
    def __init__(self, status, code, message=""):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message = status, code, message


class Client:
    def __init__(self, url, apikey, build, timeout=15.0):
        self.url, self.apikey, self.build, self.timeout = url.rstrip("/"), apikey, build, timeout
        self.run_id = self.token = None
        self.participant_id = self.participant_token = None

    def _post(self, name, body):
        request = urllib.request.Request(f"{self.url}/{name}", json.dumps(body).encode(),
                                         {"Content-Type": "application/json", "apikey": self.apikey})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read())
            except ValueError:
                detail = {}
            raise ServerError(e.code, detail.get("error", "http"), detail.get("message", "")) from None

    def login(self, prolific_pid=None, consent=None, consent_version=None):
        """Log a participant in (a returning Prolific ID gets a fresh participant token) and return the menu: {"participant_id", "token",
        "experiments": [...]}, or {"needs_consent": True} when `consent_version` (or `consent`'s) is not on file for that ID and no `consent`
        {version, signature, at} was given. Without a version no consent is asked. The result's `token` is kept as the participant token."""
        body = {"build": self.build}
        if prolific_pid is not None:
            body["prolific_pid"] = prolific_pid
        if consent is not None:
            body["consent"] = consent
        if consent_version is not None:
            body["consent_version"] = consent_version
        result = self._post("participant-start", body)
        if not result.get("needs_consent"):
            self.participant_id, self.participant_token = result["participant_id"], result["token"]
        return result

    def start(self, experiment=EXPERIMENT, prolific_pid=None, consent=None, login=True, expected_sessions=None):
        """The run of `experiment`: a new one, or the continuation of the participant's unfinished one (a finished one answers with its
        status and completion code). Logs in first (a new participant unless `prolific_pid` names a known one) unless `login` is False.
        `expected_sessions` declares a reduced run (only a development release accepts it): the number of sessions it will have."""
        if login:
            self.login(prolific_pid, consent)
        body = {"build": self.build, "participant_id": self.participant_id, "participant_token": self.participant_token, "experiment": experiment}
        if expected_sessions is not None:
            body["expected_sessions"] = expected_sessions
        result = self._post("run-start", body)
        self.run_id = result.get("run_id", self.run_id)
        self.token = result.get("token", self.token)
        return result

    def append(self, session_index, session=None, events=(), frames=None, first_seq=0, sets=()):
        """One upload. `frames` is an (n, 6) array whose first frame has sequence number `first_seq`."""
        chunks = []
        if frames is not None and len(frames):
            chunks.append(base64.b64encode(codec.encode(frames, first_seq)).decode())
        return self.append_chunks(session_index, session, events, chunks, sets)

    def append_chunks(self, session_index, session=None, events=(), chunks=(), sets=()):
        body = {"run_id": self.run_id, "token": self.token, "session_index": session_index, "events": list(events),
                "trajectory": list(chunks), "sets": list(sets)}
        if session is not None:
            body["session"] = session
        return self._post("append", body)

    def finish(self):
        return self._post("run-finish", {"run_id": self.run_id, "token": self.token})

    def feedback(self, text):
        """The participant's free-text feedback (one per run; a second call replaces it). Allowed after finish()."""
        return self._post("feedback", {"run_id": self.run_id, "token": self.token, "text": text})


def event_rows(events, first_seq=0):
    """rundata-style event dicts as upload rows (JSON has no NaN: missing numbers are null)."""
    def number(v):
        return None if v is None or (isinstance(v, float) and np.isnan(v)) else v
    return [{"seq": first_seq + i, "t": e["t"], "real": number(e.get("real")), "type": e["type"],
             "tree_id": e["tree_id"] if e.get("tree_id", -1) >= 0 else None, "k": e["k"] if e.get("k", -1) >= 0 else None,
             "reward": number(e.get("reward")), "running_total": number(e.get("running_total")), "payload": e.get("payload") or None}
            for i, e in enumerate(events)]


def upload_session(client, session_index, data, frames_per_chunk=600, events_per_batch=200):
    """Upload `rundata.read_session(...)`'s dict (session, traj, events, sets) in batches, trajectory chunks of
    `frames_per_chunk` frames. The first batch carries the session row as it stands at the start, the last one the ranking
    sets, and a final request the row's final fields (ended_at, completed, foraging_points, ranking_points, frame_stats). Returns its ack."""
    final = {k: v for k, v in data["session"].items() if k not in ("run_id", "session_index")}
    start = {**final, "ended_at": None, "completed": False, "foraging_points": None, "ranking_points": None, "frame_stats": None}
    rows, traj = event_rows(data["events"]), data["traj"]
    n_batches = max(1, -(-len(traj) // frames_per_chunk), -(-len(rows) // events_per_batch))
    for b in range(n_batches):
        client.append(session_index, session=start if b == 0 else None, events=rows[b * events_per_batch:(b + 1) * events_per_batch],
                      frames=traj[b * frames_per_chunk:(b + 1) * frames_per_chunk], first_seq=b * frames_per_chunk,
                      sets=(data["sets"] or []) if b == n_batches - 1 else ())
    return client.append(session_index, session=final)
