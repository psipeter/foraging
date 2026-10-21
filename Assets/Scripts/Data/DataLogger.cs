using System;
using System.Collections;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using UnityEngine;

// Writes one folder per session under <project root>/ForagingData/<sessionId>/ with everything needed to replay the
// participant's actions in their exact world (see docs/SCIENCE.md, "Data"):
//   trajectory.csv    one row per rendered frame: t, x, z, yaw, pitch, keys (the state HarvestManager reads that frame)
//   events.csv        sparse discrete events (pause, harvest press/release, every fruit, teleports, Interlude trials, ...)
//   harvests.csv      one row per harvest bout (a derived summary of events.csv, with the bush's attributes)
//   manifest.json     the full SessionConfig, the world file's hash, build info, display and frame statistics
// The clock `t` is unpaused session seconds since the logger started (it stands still while an instruction screen holds
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

    private const float TrajectoryFlushSeconds = 1f;

    [Serializable]
    private class BuildInfo
    {
        public string commit;
        public bool dirty;
        public string unityVersion;
    }

    private string _sessionId;
    private string _sessionDataPath;
    private StreamWriter _trajectoryWriter;
    private StreamWriter _eventWriter;
    private StreamWriter _harvestWriter;
    private CameraController _cameraController;

    private double _t;
    private int _lastRowFrame = -1;
    private float _realStart;
    private float _lastFlush;
    private bool _paused;
    private bool _finalized;
    private string _startedAtUtc;

    private int _harvestIndex;
    private double _boutStartT;
    private float _lastRunningTotal;

    private int _frames;
    private double _dtSum;
    private float _dtMax;

    private string _worldHash;
    private string _interludeHash;

    // Folder of this session's files (set in Start); the Interlude writes interlude.csv next to them.
    public string SessionDataPath => _sessionDataPath;

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
        _sessionId = Guid.NewGuid().ToString("N").Substring(0, 8);
        string root = Path.Combine(Application.dataPath, "..", "ForagingData");
        _sessionDataPath = Path.Combine(root, _sessionId);
        _startedAtUtc = DateTime.UtcNow.ToString("O");
        _realStart = Time.realtimeSinceStartup;
        _lastFlush = Time.realtimeSinceStartup;

        if (playerController != null)
        {
            _cameraController = playerController.GetComponent<CameraController>();
        }

        try
        {
            Directory.CreateDirectory(_sessionDataPath);

            _trajectoryWriter = OpenWriter("trajectory.csv", "t,x,z,yaw,pitch,keys");
            _eventWriter = OpenWriter("events.csv", "t,real,type,tree_id,k,reward,running_total,note");
            _harvestWriter = OpenWriter("harvests.csv",
                "harvest_index,t_start,t_end,tree_id,tree_x,tree_y,tree_z,shape,color,moisture,true_reward,total_received,running_total,fruit_rewards,fruits_collected,fruits_remaining,tree_exhausted");

            HashAndArchiveWorldFiles();
            WriteManifest(false);
        }
        catch (Exception e)
        {
            Debug.LogError($"DataLogger failed to initialize IO: {e}");
        }

        LogEvent("session_start", note: PoseNote());
    }

    private StreamWriter OpenWriter(string fileName, string header)
    {
        var writer = new StreamWriter(Path.Combine(_sessionDataPath, fileName), false, new UTF8Encoding(false), 1 << 16);
        writer.WriteLine(header);
        writer.Flush();
        return writer;
    }

    private string PoseNote()
    {
        if (playerController == null)
        {
            return "";
        }

        Vector3 p = playerController.transform.position;
        float yaw = _cameraController != null ? _cameraController.Yaw : 0f;
        float pitch = _cameraController != null ? _cameraController.Pitch : 0f;
        return string.Format(CultureInfo.InvariantCulture, "x={0:F3};z={1:F3};yaw={2:F3};pitch={3:F3}", p.x, p.z, yaw, pitch);
    }

    private void Update()
    {
        if (_finalized || _trajectoryWriter == null)
        {
            return;
        }

        bool paused = Time.timeScale <= 0f;
        if (paused != _paused)
        {
            _paused = paused;
            LogEvent(paused ? "pause" : "resume");
        }

        if (paused || playerController == null || _cameraController == null)
        {
            return;
        }

        float dt = Time.deltaTime;
        _t += dt;
        _lastRowFrame = Time.frameCount;
        _frames++;
        _dtSum += dt;
        _dtMax = Mathf.Max(_dtMax, dt);

        Vector3 p = playerController.transform.position;
        Vector2 move = playerController.MoveInput;
        int keys = (move.y > 0.01f ? KeyForward : 0) | (move.y < -0.01f ? KeyBack : 0) | (playerController.HarvestHeld ? KeyHarvest : 0);

        _trajectoryWriter.WriteLine(string.Format(CultureInfo.InvariantCulture,
            "{0:F6},{1:F4},{2:F4},{3:F4},{4:F3},{5}",
            _t, p.x, p.z, _cameraController.Yaw, _cameraController.Pitch, keys));

        if (Time.realtimeSinceStartup - _lastFlush >= TrajectoryFlushSeconds)
        {
            _trajectoryWriter.Flush();
            _lastFlush = Time.realtimeSinceStartup;
        }
    }

    private void OnApplicationFocus(bool focused)
    {
        LogEvent(focused ? "focus_gained" : "focus_lost");
    }

    // Appends one row to events.csv (flushed at once; events are rare). Missing numbers are left empty.
    public void LogEvent(string type, int treeId = -1, int k = -1, float reward = float.NaN, float runningTotal = float.NaN, string note = "")
    {
        if (_eventWriter == null)
        {
            return;
        }

        var sb = new StringBuilder();
        sb.Append(Now.ToString("F6", CultureInfo.InvariantCulture)).Append(',');
        sb.Append((Time.realtimeSinceStartup - _realStart).ToString("F3", CultureInfo.InvariantCulture)).Append(',');
        sb.Append(type).Append(',');
        sb.Append(treeId >= 0 ? treeId.ToString(CultureInfo.InvariantCulture) : "").Append(',');
        sb.Append(k >= 0 ? k.ToString(CultureInfo.InvariantCulture) : "").Append(',');
        sb.Append(float.IsNaN(reward) ? "" : reward.ToString("F0", CultureInfo.InvariantCulture)).Append(',');
        sb.Append(float.IsNaN(runningTotal) ? "" : runningTotal.ToString("F0", CultureInfo.InvariantCulture)).Append(',');
        sb.Append(note);
        _eventWriter.WriteLine(sb.ToString());
        _eventWriter.Flush();
    }

    private void HandleBoutStarted(Tree tree)
    {
        _boutStartT = Now;
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

    // harvests.csv: total_received is this bout's reward; running_total is the session total after the bout;
    // fruit_rewards lists this bout's fruits only.
    private void HandleBoutEnded(HarvestBout bout)
    {
        if (_harvestWriter == null || sessionConfig == null || bout == null || bout.tree == null)
        {
            return;
        }

        Tree tree = bout.tree;
        double endT = Now;
        LogEvent("harvest_release", tree.treeId, runningTotal: bout.runningTotal,
            note: $"fruits={bout.fruitRewards.Count};remaining={bout.fruitsRemaining};exhausted={(bout.exhausted ? 1 : 0)}");

        Vector3 treePos = tree.GetWorldCenter();
        float trueReward = sessionConfig.EvaluateReward(tree.attributes);
        string fruitRewards = string.Join(";", bout.fruitRewards.ConvertAll(v => v.ToString("F0", CultureInfo.InvariantCulture)));

        string line = string.Format(CultureInfo.InvariantCulture,
            "{0},{1:F6},{2:F6},{3},{4:F3},{5:F3},{6:F3},{7:F3},{8:F3},{9:F3},{10:F3},{11:F3},{12:F3},\"{13}\",{14},{15},{16}",
            _harvestIndex,
            _boutStartT,
            endT,
            tree.treeId,
            treePos.x, treePos.y, treePos.z,
            tree.attributes.shape,
            tree.attributes.color,
            tree.attributes.moisture,
            trueReward,
            bout.boutTotal,
            bout.runningTotal,
            fruitRewards,
            bout.fruitRewards.Count,
            bout.fruitsRemaining,
            bout.exhausted ? 1 : 0);

        _harvestWriter.WriteLine(line);
        _harvestWriter.Flush();
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
        if (_finalized || _sessionDataPath == null)
        {
            return;
        }

        _finalized = true;
        LogEvent("session_end", runningTotal: _lastRunningTotal);

        try
        {
            WriteManifest(true);
        }
        catch (Exception e)
        {
            Debug.LogError($"DataLogger failed to write the final manifest: {e}");
        }

        CloseWriter(ref _trajectoryWriter);
        CloseWriter(ref _eventWriter);
        CloseWriter(ref _harvestWriter);
    }

    private static void CloseWriter(ref StreamWriter writer)
    {
        try
        {
            writer?.Flush();
            writer?.Close();
        }
        catch { }

        writer = null;
    }

    // Hashes the world file(s) this session plays and copies each to ForagingData/_worlds/<hash8>_<name> once, so the
    // manifest hash pins the log to the exact terrain, bushes and per-fruit rewards even after the files are regenerated.
    private void HashAndArchiveWorldFiles()
    {
        if (sessionConfig == null)
        {
            return;
        }

        string archive = Path.Combine(Application.dataPath, "..", "ForagingData", "_worlds");
        _worldHash = HashAndArchive(WorldData.PathFor(sessionConfig), archive);
        _interludeHash = sessionConfig.IsInterlude ? HashAndArchive(WorldData.InterludePathFor(sessionConfig), archive) : null;
    }

    private static string HashAndArchive(string path, string archive)
    {
        try
        {
            if (!File.Exists(path))
            {
                return null;
            }

            byte[] bytes = File.ReadAllBytes(path);
            string hash;
            using (SHA256 sha = SHA256.Create())
            {
                hash = BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
            }

            Directory.CreateDirectory(archive);
            string copy = Path.Combine(archive, hash.Substring(0, 8) + "_" + Path.GetFileName(path));
            if (!File.Exists(copy))
            {
                File.WriteAllBytes(copy, bytes);
            }

            return hash;
        }
        catch (Exception e)
        {
            Debug.LogError($"DataLogger could not hash/archive {path}: {e}");
            return null;
        }
    }

    private static BuildInfo ReadBuildInfo()
    {
        try
        {
            string path = Path.Combine(Application.streamingAssetsPath, "build_info.json");
            if (File.Exists(path))
            {
                return JsonUtility.FromJson<BuildInfo>(File.ReadAllText(path));
            }
        }
        catch { }

        return null;
    }

    private static string Q(string value)
    {
        return value == null ? "null" : "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
    }

    private static string N(float value)
    {
        return value.ToString("R", CultureInfo.InvariantCulture);
    }

    // Written at the start and rewritten at the end (adds endedAtUtc, completed, frame statistics, finalScore).
    private void WriteManifest(bool final)
    {
        if (sessionConfig == null || mainCamera == null)
        {
            return;
        }

        BuildInfo build = ReadBuildInfo();
        var sb = new StringBuilder();
        sb.AppendLine("{");
        sb.AppendLine($"  \"sessionId\": {Q(_sessionId)},");
        sb.AppendLine("  \"participantId\": null,");
        sb.AppendLine($"  \"sessionName\": {Q(sessionConfig.name)},");
        sb.AppendLine($"  \"sessionIndex\": {GameManager.CurrentSessionIndex},");
        sb.AppendLine($"  \"isPractice\": {(sessionConfig.IsPractice ? "true" : "false")},");
        sb.AppendLine($"  \"isInterlude\": {(sessionConfig.IsInterlude ? "true" : "false")},");
        sb.AppendLine($"  \"startedAtUtc\": {Q(_startedAtUtc)},");
        sb.AppendLine($"  \"endedAtUtc\": {(final ? Q(DateTime.UtcNow.ToString("O")) : "null")},");
        sb.AppendLine($"  \"completed\": {(final && sunController != null && sunController.SessionComplete ? "true" : "false")},");
        sb.AppendLine($"  \"finalScore\": {(final ? N(_lastRunningTotal) : "null")},");
        sb.AppendLine("  \"build\": {");
        sb.AppendLine($"    \"commit\": {Q(build?.commit)},");
        sb.AppendLine($"    \"dirty\": {(build == null ? "null" : (build.dirty ? "true" : "false"))},");
        sb.AppendLine($"    \"unityVersion\": {Q(Application.unityVersion)},");
        sb.AppendLine($"    \"platform\": {Q(Application.platform.ToString())},");
        sb.AppendLine($"    \"editor\": {(Application.isEditor ? "true" : "false")}");
        sb.AppendLine("  },");
        sb.AppendLine("  \"world\": {");
        sb.AppendLine($"    \"seed\": {sessionConfig.WorldSeed},");
        sb.AppendLine($"    \"file\": {Q(Path.GetFileName(WorldData.PathFor(sessionConfig)))},");
        sb.AppendLine($"    \"sha256\": {Q(_worldHash)},");
        sb.AppendLine($"    \"interludeFile\": {(sessionConfig.IsInterlude ? Q(Path.GetFileName(WorldData.InterludePathFor(sessionConfig))) : "null")},");
        sb.AppendLine($"    \"interludeSha256\": {Q(_interludeHash)}");
        sb.AppendLine("  },");
        sb.AppendLine("  \"display\": {");
        sb.AppendLine($"    \"width\": {Screen.width},");
        sb.AppendLine($"    \"height\": {Screen.height},");
        sb.AppendLine($"    \"fullscreen\": {(Screen.fullScreen ? "true" : "false")},");
        sb.AppendLine($"    \"targetFrameRate\": {Application.targetFrameRate},");
        sb.AppendLine($"    \"vSyncCount\": {QualitySettings.vSyncCount}");
        sb.AppendLine("  },");
        sb.AppendLine("  \"frames\": {");
        sb.AppendLine($"    \"count\": {_frames},");
        sb.AppendLine($"    \"meanMs\": {N(_frames > 0 ? (float)(_dtSum / _frames * 1000.0) : 0f)},");
        sb.AppendLine($"    \"maxMs\": {N(_dtMax * 1000f)},");
        sb.AppendLine($"    \"fixedDeltaTime\": {N(Time.fixedDeltaTime)}");
        sb.AppendLine("  },");
        sb.AppendLine("  \"camera\": {");
        sb.AppendLine($"    \"fieldOfView\": {N(mainCamera.fieldOfView)},");
        sb.AppendLine($"    \"localHeight\": {N(mainCamera.transform.localPosition.y)},");
        sb.AppendLine($"    \"nearClipPlane\": {N(mainCamera.nearClipPlane)},");
        sb.AppendLine($"    \"farClipPlane\": {N(mainCamera.farClipPlane)}");
        sb.AppendLine("  },");
        // Every serialized SessionConfig field (reward function, look, harvest and sun parameters, ...), so nothing is forgotten.
        sb.AppendLine($"  \"config\": {JsonUtility.ToJson(sessionConfig, true)}");
        sb.AppendLine("}");

        File.WriteAllText(Path.Combine(_sessionDataPath, "manifest.json"), sb.ToString());
    }
}
