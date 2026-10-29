using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using UnityEngine;

// Records everything needed to replay the participant's actions in their exact world (docs/ONLINE_DATA_PLAN.md):
//   trajectory   one row per rendered frame: t, x, z, yaw, pitch, keys (the state HarvestManager reads that frame), quantized
//   events       sparse discrete events (pause, harvest press/release, every fruit, teleports, Interlude trials, ...)
//   session row  the full SessionConfig, the world file's hash, build info, display and frame statistics
//   Interlude    the shuffled trial order (logged when the Interlude starts) and one row per trial
// Rows are batched (events within a second, trajectory every five seconds online, every second offline) and handed to the
// DataPipeline, which writes the local copy under ForagingData/<run id>/<session>/ and uploads when online. The clock `t`
// is unpaused session seconds since the logger started (it stands still while a screen or the data gate holds
// Time.timeScale at 0). World files are archived once by content hash under ForagingData/_worlds/.
[DefaultExecutionOrder(20)]
public class DataLogger : MonoBehaviour
{
    public SessionConfig sessionConfig;
    [SerializeField] private SunController sunController;
    [SerializeField] private PlayerController playerController;
    [SerializeField] private HarvestManager harvestManager;
    [SerializeField] private Camera mainCamera;

    // trajectory.csv `keys` bitfield.
    private const int KeyForward = 1;
    private const int KeyBack = 2;
    private const int KeyHarvest = 4;

    private const float EventFlushSeconds = 1f;
    private const float OnlineTrajectoryFlushSeconds = 5f;
    private const float OfflineTrajectoryFlushSeconds = 1f;

    private int _sessionIndex;
    private CameraController _cameraController;

    private double _t;
    private int _lastRowFrame = -1;
    private float _realStart;
    private float _lastFlush;
    private float _lastFrameFlush;
    private bool _paused;
    private bool _finalized;
    private string _startedAtUtc;

    private int _harvestIndex;
    private float _lastRunningTotal;

    private int _frames;
    private double _dtSum;
    private float _dtMax;

    private string _worldHash;
    private string _interludeHash;

    // Rows since the last flush; the sequence numbers run on across flushes (a frame's is its index in the session).
    private readonly List<EventRow> _events = new List<EventRow>();
    private readonly List<FrameQ> _pendingFrames = new List<FrameQ>();
    private readonly List<TrialRow> _trials = new List<TrialRow>();
    private int _eventSeq, _frameSeq, _trialSeq;
    private int[] _plan;
    private string _sessionJson;
    private ResumeReply _resume;        // the server's state when this session continues an interrupted one

    // Session clock now: this frame's value whether or not this frame's trajectory row has been written yet.
    private double Now => _lastRowFrame == Time.frameCount ? _t : _t + Time.deltaTime;

    private void OnEnable()
    {
        HarvestManager.OnHarvestBoutStarted += HandleBoutStarted;
        HarvestManager.OnHarvestBoutEnded += HandleBoutEnded;
        HarvestManager.OnFruitRewarded += HandleFruitRewarded;
        HarvestManager.OnHarvestConeChanged += HandleConeChanged;
        SunController.OnSessionEnd += HandleSessionEnd;
    }

    private void OnDisable()
    {
        HarvestManager.OnHarvestBoutStarted -= HandleBoutStarted;
        HarvestManager.OnHarvestBoutEnded -= HandleBoutEnded;
        HarvestManager.OnFruitRewarded -= HandleFruitRewarded;
        HarvestManager.OnHarvestConeChanged -= HandleConeChanged;
        SunController.OnSessionEnd -= HandleSessionEnd;
        FinalizeLog();
    }

    private void Start()
    {
        _sessionIndex = GameManager.CurrentSessionIndex;
        DataPipeline.SceneSuperseded = false;
        _startedAtUtc = DateTime.UtcNow.ToString("O");
        _realStart = Time.realtimeSinceStartup;
        _lastFlush = _lastFrameFlush = Time.realtimeSinceStartup;
        DataPipeline.Configure(sessionConfig != null ? sessionConfig.UploadGraceSeconds : 4f);

        if (playerController != null)
        {
            _cameraController = playerController.GetComponent<CameraController>();
        }

        HashAndArchiveWorldFiles();
        bool newRunStage = ResumeInfo.Pending != null && ResumeInfo.Pending.completed;      // the run continues at a session boundary
        if (newRunStage)
        {
            ResumeInfo.Pending = null;
        }

        if (ResumeInfo.MidSession(_sessionIndex))
        {
            BeginResumed(ResumeInfo.Pending);
        }
        else
        {
            _sessionJson = SessionJson(false);
            LogEvent("session_start", payload: newRunStage ? Json.Obj(("resumed_run", true)) : PosePayload());
        }

        Flush();
    }

    // This session continues one the participant left: sequence numbers and the clock carry on from what the server holds, and
    // the game's state is restored once the scene's trees exist. Rows logged while the scene was starting (the Interlude's first
    // trial) are moved to the resume, after the session_resume event.
    private void BeginResumed(ResumeReply r)
    {
        _resume = r;
        _eventSeq = r.events_next;
        _frameSeq = r.trajectory_next;
        _trialSeq = r.trials_next;
        _t = r.clock;
        _lastRunningTotal = r.running_total;
        if (!string.IsNullOrEmpty(r.started_at))
        {
            _startedAtUtc = r.started_at;
        }

        foreach (EventRow e in _events)
        {
            e.T = _t;
        }

        _events.Insert(0, new EventRow
        {
            T = _t, Real = Time.realtimeSinceStartup - _realStart, Type = "session_resume",
            Payload = Json.Obj(("gap_s", r.gap_seconds), ("stale_s", r.clock - r.pose.t), ("open_bout_tree", r.open_bout_tree),
                ("frames_held", r.trajectory_next), ("has_pose", r.has_pose)),
        });
        StartCoroutine(ApplyResume());
    }

    // Puts the player, the bushes' fruit, the score and the sun back where the server's data says they were.
    private IEnumerator ApplyResume()
    {
        yield return null;
        yield return null;          // the trees are generated and found by now
        ResumeReply r = _resume;
        if (sessionConfig != null && !sessionConfig.IsInterlude)
        {
            if (r.has_pose && playerController != null)
            {
                playerController.TeleportTo(r.pose.x, r.pose.z);
                _cameraController?.SetView(r.pose.yaw, r.pose.pitch);
            }

            harvestManager?.RestoreState(r.fruits_taken, r.running_total);
            sunController?.SetSessionTime((float)r.clock);
        }

        ResumeInfo.Pending = null;
    }

    private string PosePayload()
    {
        if (playerController == null)
        {
            return null;
        }

        Vector3 p = playerController.transform.position;
        float yaw = _cameraController != null ? _cameraController.Yaw : 0f;
        float pitch = _cameraController != null ? _cameraController.Pitch : 0f;
        return Json.Obj(("x", p.x), ("z", p.z), ("yaw", yaw), ("pitch", pitch));
    }

    private void Update()
    {
        if (_finalized)
        {
            return;
        }

        // Whether this frame has a row depends on the time it was given at its start (deltaTime), not on timeScale now:
        // a screen that opens mid-frame (during HarvestManager.Update) leaves this frame's events stamped at its end, so
        // its row must still be written, before the pause event; and the frame in which a screen closes has dt 0.
        float dt = Time.deltaTime;
        if (dt > 0f && playerController != null && _cameraController != null)
        {
            _t += dt;
            _lastRowFrame = Time.frameCount;
            _frames++;
            _dtSum += dt;
            _dtMax = Mathf.Max(_dtMax, dt);

            Vector3 p = playerController.transform.position;
            Vector2 move = playerController.MoveInput;
            int keys = (move.y > 0.01f ? KeyForward : 0) | (move.y < -0.01f ? KeyBack : 0) | (playerController.HarvestHeld ? KeyHarvest : 0);

            _pendingFrames.Add(FrameQ.From(_t, p.x, p.z, _cameraController.Yaw, _cameraController.Pitch, keys));
        }

        bool paused = Time.timeScale <= 0f;
        if (paused != _paused)
        {
            _paused = paused;
            LogEvent(paused ? "pause" : "resume", payload: paused ? Json.Obj(("reason", PauseGate.Reason)) : null);
        }

        float now = Time.realtimeSinceStartup;
        float frameInterval = DataPipeline.IsOnline ? OnlineTrajectoryFlushSeconds : OfflineTrajectoryFlushSeconds;
        bool eventsDue = (_events.Count > 0 || _trials.Count > 0) && now - _lastFlush >= EventFlushSeconds;
        if (eventsDue || (_pendingFrames.Count > 0 && now - _lastFrameFlush >= frameInterval))
        {
            Flush();
        }
    }

    private void OnApplicationFocus(bool focused)
    {
        LogEvent(focused ? "focus_gained" : "focus_lost");
    }

    // Records one event; `payload` is a JSON object (Json.Obj) with the event's extra fields, or null.
    public void LogEvent(string type, int treeId = -1, int k = -1, float reward = float.NaN, float runningTotal = float.NaN, string payload = null)
    {
        if (_finalized && type != "session_end")
        {
            return;
        }

        _events.Add(new EventRow
        {
            T = Now, Real = Time.realtimeSinceStartup - _realStart, Type = type, TreeId = treeId, K = k,
            Reward = reward, RunningTotal = runningTotal, Payload = payload,
        });
    }

    // The Interlude's shuffled trial order (the trial indices in presentation order), logged once when it starts.
    public void LogInterludePlan(int[] trialOrder)
    {
        _plan = trialOrder;
    }

    // One Interlude trial: its cells in TrialRow.Columns order, formatted, '' for a missing value.
    public void LogTrial(string[] cells)
    {
        _trials.Add(new TrialRow { Cells = cells });
    }

    // Hands everything recorded since the last flush to the pipeline.
    private void Flush()
    {
        // Nothing is sent before the run exists (online) and the pipeline has decided which session this scene plays.
        if (!DataPipeline.IsReady || DataPipeline.SceneSuperseded)
        {
            return;
        }

        foreach (EventRow e in _events)
        {
            e.Seq = _eventSeq++;
        }

        foreach (TrialRow t in _trials)
        {
            t.Seq = _trialSeq++;
        }

        var batch = new DataBatch
        {
            SessionIndex = _sessionIndex, SessionJson = _sessionJson, Plan = _plan, FirstFrameSeq = _frameSeq,
            Events = new List<EventRow>(_events), Frames = new List<FrameQ>(_pendingFrames), Trials = new List<TrialRow>(_trials),
        };
        _events.Clear();
        _trials.Clear();
        _frameSeq += _pendingFrames.Count;
        _pendingFrames.Clear();
        _sessionJson = null;
        _plan = null;
        _lastFlush = _lastFrameFlush = Time.realtimeSinceStartup;
        if (!batch.IsEmpty)
        {
            DataPipeline.Submit(batch);
        }
    }

    private void HandleBoutStarted(Tree tree)
    {
        LogEvent("harvest_press", tree.treeId, runningTotal: _lastRunningTotal);
    }

    private void HandleConeChanged(Tree tree, bool inCone)
    {
        LogEvent(inCone ? "harvest_resume" : "harvest_pause", tree.treeId);
    }

    private void HandleFruitRewarded(Tree tree, int k, float reward, float runningTotal)
    {
        _lastRunningTotal = runningTotal;
        LogEvent("fruit", tree.treeId, k, reward, runningTotal);
    }

    // The bout's summary is no longer stored: it is derived from the events and the world file.
    private void HandleBoutEnded(HarvestBout bout)
    {
        if (sessionConfig == null || bout == null || bout.tree == null)
        {
            return;
        }

        Tree tree = bout.tree;
        LogEvent("harvest_release", tree.treeId, runningTotal: bout.runningTotal,
            payload: Json.Obj(("fruits", bout.fruitRewards.Count), ("remaining", bout.fruitsRemaining), ("exhausted", bout.exhausted ? 1 : 0)));
        _lastRunningTotal = bout.runningTotal;
        _harvestIndex++;
    }
    // HarvestManager's own session-end handler closes the open bout; finish after it has run (end of frame).
    private void HandleSessionEnd()
    {
        StartCoroutine(FinalizeAtEndOfFrame());
    }

    private IEnumerator FinalizeAtEndOfFrame()
    {
        yield return new WaitForEndOfFrame();
        FinalizeLog();
    }

    private void OnApplicationQuit()
    {
        FinalizeLog();
    }

    private void FinalizeLog()
    {
        if (_finalized || _startedAtUtc == null)
        {
            return;
        }

        if (DataPipeline.SceneSuperseded)
        {
            _finalized = true;          // the scene is being replaced to continue another session: this one's rows are discarded
            return;
        }

        LogEvent("session_end", runningTotal: _lastRunningTotal);
        _finalized = true;
        try
        {
            _sessionJson = SessionJson(true);
        }
        catch (Exception e)
        {
            Debug.LogError($"DataLogger failed to build the final session row: {e}");
        }

        Flush();
    }

    // Hashes the world file(s) this session plays and, where there is a file system, copies each to
    // ForagingData/_worlds/<hash8>_<name> once, so the session row's hash pins the log to the exact terrain, bushes and per-fruit
    // rewards even after the files are regenerated.
    private void HashAndArchiveWorldFiles()
    {
        if (sessionConfig == null)
        {
            return;
        }

        string archive = StreamingData.NeedsPreload ? null : Path.Combine(Application.dataPath, "..", "ForagingData", "_worlds");
        _worldHash = HashAndArchive(WorldData.PathFor(sessionConfig), archive);
        _interludeHash = sessionConfig.IsInterlude ? HashAndArchive(WorldData.InterludePathFor(sessionConfig), archive) : null;
    }

    private static string HashAndArchive(string relativePath, string archive)
    {
        try
        {
            byte[] bytes = StreamingData.ReadBytes(relativePath);
            if (bytes == null)
            {
                return null;
            }

            string hash = Sha256Hex(bytes);
            if (archive == null)
            {
                return hash;
            }

            Directory.CreateDirectory(archive);
            string copy = Path.Combine(archive, hash.Substring(0, 8) + "_" + Path.GetFileName(relativePath));

            // An archive copy that is missing, or whose content no longer matches its name (a write cut short by a crash),
            // is replaced. The copy is written under a temporary name and moved into place, so a crash never leaves a
            // partial file at the final name for a later session to trust.
            if (!File.Exists(copy) || Sha256Hex(File.ReadAllBytes(copy)) != hash)
            {
                string temp = copy + "." + Guid.NewGuid().ToString("N").Substring(0, 8) + ".tmp";
                File.WriteAllBytes(temp, bytes);
                if (File.Exists(copy))
                {
                    File.Delete(copy);
                }

                File.Move(temp, copy);
            }

            return hash;
        }
        catch (Exception e)
        {
            Debug.LogError($"DataLogger could not hash/archive {relativePath}: {e}");
            return null;
        }
    }

    private static string Sha256Hex(byte[] bytes)
    {
        using (SHA256 sha = SHA256.Create())
        {
            return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
        }
    }

    // The `sessions` row: the full SessionConfig, the world hashes, build, display and frame statistics. Sent when the
    // session starts and again, with the end fields filled in, when it ends.
    private string SessionJson(bool final)
    {
        if (sessionConfig == null || mainCamera == null)
        {
            return null;
        }

        BuildInfo build = BuildInfo.Read();
        string camera = Json.Obj(("fieldOfView", mainCamera.fieldOfView), ("localHeight", mainCamera.transform.localPosition.y),
            ("nearClipPlane", mainCamera.nearClipPlane), ("farClipPlane", mainCamera.farClipPlane));
        string display = Json.Obj(("width", Screen.width), ("height", Screen.height), ("fullscreen", Screen.fullScreen),
            ("targetFrameRate", Application.targetFrameRate), ("vSyncCount", QualitySettings.vSyncCount),
            ("platform", Application.platform.ToString()), ("unityVersion", Application.unityVersion),
            ("buildCommit", build?.commit), ("buildDirty", build != null ? (object)build.dirty : null));
        string frameStats = Json.Obj(("count", _frames), ("meanMs", _frames > 0 ? _dtSum / _frames * 1000.0 : 0.0), ("maxMs", _dtMax * 1000f),
            ("fixedDeltaTime", Time.fixedDeltaTime));
        return Json.Obj(
            ("session_index", _sessionIndex),
            ("name", sessionConfig.name),
            ("is_practice", sessionConfig.IsPractice),
            ("is_interlude", sessionConfig.IsInterlude),
            ("world_seed", sessionConfig.WorldSeed),
            ("world_file", Path.GetFileName(WorldData.PathFor(sessionConfig))),
            ("world_sha256", _worldHash),
            ("interlude_file", sessionConfig.IsInterlude ? Path.GetFileName(WorldData.InterludePathFor(sessionConfig)) : null),
            ("interlude_sha256", _interludeHash),
            ("config", new Json.Raw(JsonUtility.ToJson(sessionConfig))),
            ("camera", new Json.Raw(camera)),
            ("display", new Json.Raw(display)),
            ("frame_stats", final ? new Json.Raw(frameStats) : null),
            ("started_at", _startedAtUtc),
            ("ended_at", final ? DateTime.UtcNow.ToString("O") : null),
            ("completed", final && sunController != null && sunController.SessionComplete),
            ("final_score", final ? (object)_lastRunningTotal : null));
    }
}
