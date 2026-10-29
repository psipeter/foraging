using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

// Uploads batches to the server's `append` function (docs/ONLINE_DATA_PLAN.md, section 3), one request at a time and in
// order. A batch leaves the queue only when the server answers 2xx, which means every row of it is stored; connection
// errors, timeouts and 5xx are retried with backoff; any other error is the client's or the study's problem (a bad token,
// an unknown world, a sequence gap) and stops uploading (OnFatal), because retrying cannot fix it.
public class HttpSink : IDataSink
{
    private class Item
    {
        public byte[] Body;
        public float SubmitTime;
    }

    [Serializable]
    private class ErrorReply
    {
        public string error;
        public string message;
    }

    private const int FramesPerChunk = 2000;
    private const float RequestTimeoutSeconds = 20f;

    private readonly MonoBehaviour _host;
    private readonly string _url, _apikey, _runId, _token;
    private readonly Queue<Item> _queue = new Queue<Item>();
    private bool _running;

    public event Action<string> OnFatal;
    public string LastError { get; private set; }
    public bool Failed { get; private set; }

    // Batches not yet acknowledged (including the one in flight), and how long the oldest has waited.
    public int Pending => _queue.Count;
    public float OldestAge => _queue.Count > 0 ? Time.realtimeSinceStartup - _queue.Peek().SubmitTime : 0f;

    public HttpSink(MonoBehaviour host, string url, string apikey, string runId, string token)
    {
        _host = host;
        _url = url.TrimEnd('/');
        _apikey = apikey;
        _runId = runId;
        _token = token;
    }

    public void Write(DataBatch batch)
    {
        if (Failed)
        {
            return;
        }

        _queue.Enqueue(new Item { Body = Encoding.UTF8.GetBytes(BuildBody(batch)), SubmitTime = batch.SubmitTime });
        if (!_running)
        {
            _running = true;
            _host.StartCoroutine(Upload());
        }
    }

    private string BuildBody(DataBatch b)
    {
        var sb = new StringBuilder(4096);
        sb.Append("{\"run_id\":").Append(Json.Quote(_runId)).Append(",\"token\":").Append(Json.Quote(_token));
        sb.Append(",\"session_index\":").Append(b.SessionIndex);
        if (b.SessionJson != null)
        {
            sb.Append(",\"session\":").Append(b.SessionJson);
        }

        sb.Append(",\"events\":[");
        for (int i = 0; i < b.Events.Count; i++)
        {
            sb.Append(i > 0 ? "," : "").Append(b.Events[i].ToJson());
        }

        sb.Append("],\"trajectory\":[");
        for (int start = 0; start < b.Frames.Count; start += FramesPerChunk)
        {
            int count = Math.Min(FramesPerChunk, b.Frames.Count - start);
            byte[] chunk = TrajectoryCodec.Encode(b.Frames, start, count, (uint)(b.FirstFrameSeq + start));
            sb.Append(start > 0 ? "," : "").Append('"').Append(Convert.ToBase64String(chunk)).Append('"');
        }

        sb.Append("],\"trials\":[");
        for (int i = 0; i < b.Trials.Count; i++)
        {
            sb.Append(i > 0 ? "," : "").Append(b.Trials[i].ToJson());
        }

        sb.Append(']');
        if (b.Plan != null)
        {
            sb.Append(",\"plan\":[").Append(string.Join(",", b.Plan)).Append(']');
        }

        return sb.Append('}').ToString();
    }

    private IEnumerator Upload()
    {
        float backoff = 0f;
        while (_queue.Count > 0)
        {
            if (backoff > 0f)
            {
                yield return new WaitForSecondsRealtime(backoff);
            }

            using (UnityWebRequest request = Post(_url, _apikey, "append", _queue.Peek().Body))
            {
                yield return Send(request, RequestTimeoutSeconds);
                if (request.result == UnityWebRequest.Result.Success)
                {
                    _queue.Dequeue();
                    backoff = 0f;
                    LastError = null;
                    continue;
                }

                LastError = Describe(request);
                Debug.LogWarning($"upload failed: {LastError}");
                if (!Retriable(request))
                {
                    Failed = true;
                    _queue.Clear();
                    OnFatal?.Invoke(LastError);
                    break;
                }

                backoff = backoff == 0f ? 1f : Mathf.Min(backoff * 2f, 8f);
            }
        }

        _running = false;
    }

    public static UnityWebRequest Post(string url, string apikey, string function, byte[] body)
    {
        var request = new UnityWebRequest(url.TrimEnd('/') + "/" + function, "POST")
        {
            uploadHandler = new UploadHandlerRaw(body),
            downloadHandler = new DownloadHandlerBuffer(),
        };
        request.SetRequestHeader("Content-Type", "application/json");
        request.SetRequestHeader("apikey", apikey);
        return request;
    }

    // Sends the request and waits for it, aborting after `timeoutSeconds` (a timeout that works in a browser too, where
    // UnityWebRequest.timeout is not honoured): an aborted request ends as a connection error, which is retried.
    public static IEnumerator Send(UnityWebRequest request, float timeoutSeconds)
    {
        UnityWebRequestAsyncOperation operation = request.SendWebRequest();
        float start = Time.realtimeSinceStartup;
        bool aborted = false;
        while (!operation.isDone)
        {
            if (!aborted && Time.realtimeSinceStartup - start > timeoutSeconds)
            {
                request.Abort();
                aborted = true;
            }

            yield return null;
        }
    }

    // Network trouble, a timeout or a server-side failure may pass; a 4xx (other than a timeout or rate limit) will not.
    public static bool Retriable(UnityWebRequest request)
    {
        if (request.result == UnityWebRequest.Result.ConnectionError)
        {
            return true;
        }

        long code = request.responseCode;
        return code == 0 || code >= 500 || code == 408 || code == 429;
    }

    public static string Describe(UnityWebRequest request)
    {
        string detail = request.error;
        try
        {
            ErrorReply reply = JsonUtility.FromJson<ErrorReply>(request.downloadHandler.text);
            if (!string.IsNullOrEmpty(reply?.error))
            {
                detail = reply.error + (string.IsNullOrEmpty(reply.message) ? "" : ": " + reply.message);
            }
        }
        catch { }

        return $"{request.responseCode} {detail}";
    }
}
