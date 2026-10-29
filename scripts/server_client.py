"""Reference client of the online data server (docs/ONLINE_DATA_PLAN.md, section 3): the protocol the Unity client will
speak, in Python, so the server can be tested end to end and a stored session can be uploaded by hand.

    client = Client(url, apikey, build={"commit": "abc123", "dirty": False, "platform": "Test", "unity_version": "6000"})
    started = client.start()                       # {"run_id", "token", "status", "resume"}
    client.append(0, session=row, events=[...], frames=array, first_seq=0)
    client.finish()                                # {"ok", "problems"}

`url` is the functions' base ("https://<ref>.supabase.co/functions/v1" deployed; "http://127.0.0.1:54399" for local/serve.ts).
`upload_session` sends a session of the local layout (rundata.read_session) in batches, the way a recorder would.
"""

import base64
import json
import urllib.error
import urllib.request

import numpy as np

import trajectory_codec as codec


class ServerError(Exception):
    def __init__(self, status, code, message=""):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message = status, code, message


class Client:
    def __init__(self, url, apikey, build, timeout=15.0):
        self.url, self.apikey, self.build, self.timeout = url.rstrip("/"), apikey, build, timeout
        self.run_id = self.token = None

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

    def _take(self, result):
        self.run_id = result.get("run_id", self.run_id)
        self.token = result.get("token", self.token)
        return result

    def start(self, prolific_pid=None):
        """A new run, or the continuation of the Prolific ID's run."""
        body = {"build": self.build}
        if prolific_pid is not None:
            body["prolific_pid"] = prolific_pid
        return self._take(self._post("run-start", body))

    def resume(self, run_id=None, token=None):
        """Continue an anonymous run with its token (the old token stops working)."""
        return self._take(self._post("run-start", {"build": self.build, "run_id": run_id or self.run_id, "token": token or self.token}))

    def append(self, session_index, session=None, events=(), frames=None, first_seq=0, plan=None, trials=()):
        """One upload. `frames` is an (n, 6) array whose first frame has sequence number `first_seq`."""
        chunks = []
        if frames is not None and len(frames):
            chunks.append(base64.b64encode(codec.encode(frames, first_seq)).decode())
        return self.append_chunks(session_index, session, events, chunks, plan, trials)

    def append_chunks(self, session_index, session=None, events=(), chunks=(), plan=None, trials=()):
        body = {"run_id": self.run_id, "token": self.token, "session_index": session_index, "events": list(events),
                "trajectory": list(chunks), "trials": list(trials)}
        if session is not None:
            body["session"] = session
        if plan is not None:
            body["plan"] = list(plan)
        return self._post("append", body)

    def finish(self):
        return self._post("run-finish", {"run_id": self.run_id, "token": self.token})


def event_rows(events, first_seq=0):
    """rundata-style event dicts as upload rows (JSON has no NaN: missing numbers are null)."""
    def number(v):
        return None if v is None or (isinstance(v, float) and np.isnan(v)) else v
    return [{"seq": first_seq + i, "t": e["t"], "real": number(e.get("real")), "type": e["type"],
             "tree_id": e["tree_id"] if e.get("tree_id", -1) >= 0 else None, "k": e["k"] if e.get("k", -1) >= 0 else None,
             "reward": number(e.get("reward")), "running_total": number(e.get("running_total")), "payload": e.get("payload") or None}
            for i, e in enumerate(events)]


def upload_session(client, session_index, data, frames_per_chunk=600, events_per_batch=200):
    """Upload `rundata.read_session(...)`'s dict (session, traj, events, plan, trials) in batches, trajectory chunks of
    `frames_per_chunk` frames. The first batch carries the session row as it stands at the start, the last one its
    final fields (ended_at, completed, final_score, frame_stats) and the Interlude trials. Returns the last ack."""
    final = {k: v for k, v in data["session"].items() if k not in ("run_id", "session_index")}
    start = {**final, "ended_at": None, "completed": False, "final_score": None, "frame_stats": None}
    rows, traj = event_rows(data["events"]), data["traj"]
    n_batches = max(1, -(-len(traj) // frames_per_chunk), -(-len(rows) // events_per_batch))
    ack = None
    for b in range(n_batches):
        last = b == n_batches - 1
        ack = client.append(
            session_index, session=final if last and b > 0 else (start if b == 0 else None),
            events=rows[b * events_per_batch:(b + 1) * events_per_batch],
            frames=traj[b * frames_per_chunk:(b + 1) * frames_per_chunk], first_seq=b * frames_per_chunk,
            plan=data["plan"] if b == 0 else None, trials=(data["trials"] or []) if last else ())
    if n_batches == 1:       # the only batch carried the starting row: send the final fields too
        ack = client.append(session_index, session=final)
    return ack
