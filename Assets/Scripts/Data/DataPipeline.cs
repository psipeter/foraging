using System;
using System.Collections;
using System.IO;
using TMPro;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.SceneManagement;

// Owns where recorded data goes, across the scene reloads between sessions: the local copy (FileSink) always, and the
// server (HttpSink) when online.json says so. It starts the run on the server, holds the game still behind a message
// while the server is unreachable or has not yet acknowledged data older than the grace window (docs/ONLINE_DATA_PLAN.md,
// "pause until acknowledged"), and delays leaving a session or quitting until everything is acknowledged.
public class DataPipeline : MonoBehaviour
{
    [Serializable]
    private class StartReply
    {
        public string run_id;
        public string token;
        public string status;
        public bool has_resume;           // `resume` is a nested object, which JsonUtility cannot leave null: this says whether it was sent
        public ResumeReply resume;
        public string completion_code;
    }

    [Serializable]
    private class FinishReply
    {
        public bool ok;
        public string[] problems;
        public string completion_code;
    }

    private static DataPipeline _instance;
    private static float _graceSeconds = 4f;
    private const string ProlificCompletionUrl = "https://app.prolific.com/submissions/complete?cc=";

    private OnlineSettings _settings;
    private BuildInfo _build;
    private FileSink _file;
    private HttpSink _http;
    private bool _online;
    private bool _ready;
    private string _fatal;
    private bool _leaving;
    private string _token;
    private string _notice;
    private string _completionCode;
    private bool _redirecting;
    private FeedbackScreen _feedback;
    private bool _finishing;
    private bool _finished;
    private bool _quitRequested;
    private float _quitRequestedAt;
    private GameObject _overlay;
    private TextMeshProUGUI _message;

    public static bool IsOnline => Instance._online;
    public static bool IsReady => Instance._ready;
    public static string RunId { get; private set; }

    // True from the moment the pipeline decides the loaded scene is not the one to record (it reloads the scene to continue an
    // interrupted run, or the run is already complete) until a new scene's logger starts: the old scene's logger must not send
    // what it recorded for the wrong session.
    public static bool SceneSuperseded { get; set; }

    private static DataPipeline Instance
    {
        get
        {
            if (_instance == null)
            {
                var go = new GameObject("DataPipeline");
                DontDestroyOnLoad(go);
                _instance = go.AddComponent<DataPipeline>();
            }

            return _instance;
        }
    }

    // Seconds the server may leave data unacknowledged before the game pauses (SessionConfig.UploadGraceSeconds).
    public static void Configure(float graceSeconds)
    {
        _graceSeconds = Mathf.Max(0f, graceSeconds);
        _ = Instance;
    }

    public static void Submit(DataBatch batch)
    {
        batch.SubmitTime = Time.realtimeSinceStartup;
        Instance.Dispatch(batch);
    }

    // Called when the participant asks to move on from a session's end screen: true when everything is stored; otherwise
    // the game shows "saving" until it is, and the participant asks again.
    public static bool TryLeave()
    {
        DataPipeline p = Instance;
        if (p.Drained)
        {
            return true;
        }

        p._leaving = true;
        return false;
    }

    // The study is finished and its data stored: a browser page cannot be closed by the game, so it says so and stays still.
    public static void ShowStudyComplete() => Instance.ShowComplete();

    // The final message: the completion code and, for a participant who arrived from Prolific (the address carries PROLIFIC_PID), a way
    // back to Prolific's completion page. A run this page holds the token of also gets the optional feedback box, and then the
    // participant returns by a button (typing takes longer than a timer); otherwise Prolific is opened a few seconds later.
    private void ShowComplete()
    {
        SceneSuperseded = true;
        bool fromProlific = _completionCode != null && OnlineSettings.UrlParameter("PROLIFIC_PID") != null;
        bool feedback = _token != null && _online;
        _notice = "Thank you! The study is complete." +
            (_completionCode != null ? $"\n\nYour completion code is {_completionCode}" : "") +
            (fromProlific && !feedback ? "\n\n<size=65%>You will be returned to Prolific in a few seconds.</size>" : "") +
            (fromProlific && feedback ? "\n\n<size=65%>Press \"Return to Prolific\" when you are done.</size>" : "") +
            (!fromProlific ? "\n\n<size=65%>You can close this page.</size>" : "");
        if (feedback && _feedback == null)
        {
            PointerLockGuard.Suspended = true;
            _feedback = FeedbackScreen.Show(_overlay.transform, _message, fromProlific, text => StartCoroutine(SendFeedback(text)), RedirectToProlificNow);
        }
        else if (fromProlific && !feedback && !_redirecting)
        {
            _redirecting = true;
            StartCoroutine(RedirectToProlific());
        }
    }

    private IEnumerator SendFeedback(string text)
    {
        byte[] body = System.Text.Encoding.UTF8.GetBytes(Json.Obj(("run_id", RunId), ("token", _token), ("text", text)));
        yield return HttpSink.Call(_settings.url, _settings.apikey, "feedback", body, request =>
            _feedback.SetStatus(request.result == UnityWebRequest.Result.Success
                ? "Thank you, your feedback was saved."
                : "Your feedback could not be sent. You can try again.", false));
    }

    private IEnumerator RedirectToProlific()
    {
        yield return new WaitForSecondsRealtime(6f);
        RedirectToProlificNow();
    }

    private void RedirectToProlificNow()
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        RedirectTo(ProlificCompletionUrl + System.Uri.EscapeDataString(_completionCode));
#endif
    }

#if UNITY_WEBGL && !UNITY_EDITOR
    [System.Runtime.InteropServices.DllImport("__Internal")]
    private static extern void RedirectTo(string url);
#endif

    // Called when the participant asks to leave the last session's end screen: true when the run is closed on the server
    // (everything stored, then run-finish answered); until then the game shows "saving" / "finishing up".
    public static bool TryFinish()
    {
        DataPipeline p = Instance;
        if (!p._online || p._finished || p._fatal != null)
        {
            return true;
        }

        if (TryLeave() && !p._finishing)
        {
            p._finishing = true;
            p.StartCoroutine(p.FinishRun());
        }

        return false;
    }

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    private static void Reset()
    {
        _instance = null;
        RunId = null;
        SceneSuperseded = false;
    }

    private bool Drained => _http == null || _http.Pending == 0;

    // Touch Instance first in the game scene: its resume path reloads the active scene.
    private void Awake()
    {
        _settings = OnlineSettings.Load();
        _build = BuildInfo.Read();
        _online = _settings.Active;
        _message = UiStyle.MessageScreen("DataGate", transform, 5000, true);
        _overlay = _message.canvas.gameObject;
        _overlay.SetActive(false);
        Application.wantsToQuit += OnWantsToQuit;
        if (StreamingData.NeedsPreload && !_online)
        {
            // A browser has no file to keep the data in: without a server it would be lost.
            _fatal = "This version of the game is not connected to a data server.";
        }

        if (_online)
        {
            StartCoroutine(StartRun());
        }
        else
        {
            BecomeReady(Guid.NewGuid().ToString(), null);
        }
    }

    private void OnDestroy()
    {
        Application.wantsToQuit -= OnWantsToQuit;
        _file?.Dispose();
    }

    private void Dispatch(DataBatch batch)
    {
        try
        {
            _file?.Write(batch);       // no local copy in a browser
        }
        catch (Exception e)
        {
            Debug.LogError($"Local data copy failed: {e.Message}");
        }

        _http?.Write(batch);
    }

    private void BecomeReady(string runId, string token, ResumeReply resume = null)
    {
        RunId = runId;
        _token = token;
        string root = Path.Combine(Application.dataPath, "..", "ForagingData");
        string runJson = Json.Obj(("platform", Application.platform.ToString()), ("build_commit", _build?.commit),
            ("build_dirty", _build != null ? (object)_build.dirty : null), ("unity_version", Application.unityVersion),
            ("started_at", DateTime.UtcNow.ToString("O")), ("online", token != null));
        try
        {
            _file = StreamingData.NeedsPreload ? null : new FileSink(root, runId, runJson);      // a browser has no file system
        }
        catch (Exception e)
        {
            Debug.LogError($"Cannot create the data folder: {e.Message}");
            _fatal = "The game cannot save its data on this computer.";
        }

        if (token != null)
        {
            _http = new HttpSink(this, _settings.url, _settings.apikey, runId, token);
            _http.OnFatal += error => _fatal = "The server refused the data (" + error + ").";
        }

        _ready = true;
        if (resume != null)
        {
            // Continue the interrupted run: what the scene recorded so far belongs to the wrong session, so drop it and
            // reload the scene for the session to continue (the logger and InterludeManager restore the state).
            if (!resume.completed)
            {
                _file?.PrepareResume(resume.session_index, resume.events_next, resume.trajectory_next, resume.trials_next);
            }

            ResumeInfo.Pending = resume;
            GameManager.RestoreTotals(resume);
            int target = resume.completed ? resume.session_index + 1 : resume.session_index;
            if (target >= GameManager.TotalSessions)
            {
                SceneSuperseded = true;
                _finishing = true;
                _notice = "You have already completed every session. Thank you!";
                StartCoroutine(FinishRun(true));
            }
            else
            {
                GameManager.CurrentSessionIndex = target;
                SceneSuperseded = true;
                SceneManager.LoadScene(SceneManager.GetActiveScene().name);
            }

        }
    }

    // run-finish: the server checks that every session is there and complete and closes the run. Retried on network errors; any
    // other answer ends the attempt (the participant must not be trapped on a screen for a problem retrying cannot fix).
    private IEnumerator FinishRun(bool showComplete = false)
    {
        byte[] body = System.Text.Encoding.UTF8.GetBytes(Json.Obj(("run_id", RunId), ("token", _token)));
        yield return HttpSink.Call(_settings.url, _settings.apikey, "run-finish", body, request =>
        {
            if (request.result == UnityWebRequest.Result.Success)
            {
                FinishReply reply = JsonUtility.FromJson<FinishReply>(request.downloadHandler.text);
                _completionCode = reply.completion_code;
                if (!reply.ok)
                {
                    Debug.LogWarning("run-finish found problems: " + string.Join("; ", reply.problems));
                }
            }
        });

        _finishing = false;
        _finished = true;
        if (showComplete)
        {
            ShowComplete();
        }
    }

    private IEnumerator StartRun()
    {
        string body = Json.Obj(("build", new Json.Raw(Json.Obj(("commit", _build?.commit), ("dirty", _build != null ? (object)_build.dirty : false),
            ("platform", Application.platform.ToString()), ("unity_version", Application.unityVersion)))),
            ("prolific_pid", _settings.prolificPid),
            ("consent", _settings.consent != null ? new Json.Raw(Json.Obj(("version", _settings.consent.version),
                ("signature", _settings.consent.signature), ("at", _settings.consent.at))) : null));
        yield return HttpSink.Call(_settings.url, _settings.apikey, "run-start", System.Text.Encoding.UTF8.GetBytes(body), request =>
        {
            if (request.result != UnityWebRequest.Result.Success)
            {
                _fatal = "The server did not accept this version of the game (" + HttpSink.Describe(request) + ").";
                return;
            }

            StartReply reply = JsonUtility.FromJson<StartReply>(request.downloadHandler.text);
            if (reply.status == "in_progress" && !string.IsNullOrEmpty(reply.token))
            {
                BecomeReady(reply.run_id, reply.token, reply.has_resume ? reply.resume : null);
            }
            else
            {
                _completionCode = reply.completion_code;
                ShowComplete();
            }
        });
    }

    private bool OnWantsToQuit()
    {
        if (Drained || _fatal != null || (_quitRequested && Time.realtimeSinceStartup - _quitRequestedAt > 15f))
        {
            return true;
        }

        if (!_quitRequested)
        {
            _quitRequested = true;
            _quitRequestedAt = Time.realtimeSinceStartup;
        }

        _leaving = true;
        return false;
    }

    private void Update()
    {
        string text = null;
        if (_fatal != null)
        {
            text = _fatal + "\n\nPlease contact the researcher.";
        }
        else if (_notice != null)
        {
            text = _notice;
        }
        else if (_online && !_ready)
        {
            text = "Connecting to the server...";
        }
        else if (_finishing)
        {
            text = "Finishing up...";
        }
        else if (_http != null && _http.Pending > 0 && (_http.OldestAge > _graceSeconds || _leaving))
        {
            text = _http.LastError != null ? "Saving your data... the connection is slow or lost; the game continues when it is back." : "Saving your data...";
        }

        if (_leaving && Drained)
        {
            _leaving = false;
            if (_quitRequested)
            {
                Application.Quit();
            }
        }

        PauseGate.Upload = text != null;
        _overlay.SetActive(text != null);

        if (text != null)
        {
            _message.text = text;
        }
    }
}
