using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using Unity.Profiling;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

// Development builds only (a release build does nothing, so a link cannot change what a participant sees). Measures the frame time of the game scene and can
// change graphics settings from the address, so that scripts/perf_browser.mjs can compare settings in a real browser without a rebuild.
//   ?perf=1             record every frame of the game scene (time held by a screen or an unreleased mouse is left out) and print one line to the console:
//                       PERF_JSON {...} (settings applied, the machine, summary, one-second series, every frame's milliseconds)
//   ?perfSeconds=60     how long to record before printing (default 60); PerfProbe.Mark("label") tags the frames that follow (the benchmark autopilot uses it)
// Settings (each only with perf=1; ignored in the Editor, where they would be saved into the shared assets):
//   renderScale=0.8  shadows=0  shadowDistance=60  shadowCascades=1  shadowRes=1024  softShadows=0  msaa=1|2|4  hdr=0
//   ssao=0  bloom=0  vignette=0  post=0 (all post-processing)  fruitShadows=1|0 (fruits cast shadows or not; the game now has them off)  fps=-1|0|60|120 (Application.targetFrameRate; -1 = the
//   browser's own refresh rate, 0 is not "uncapped" in a browser)  quality=<n> (also LightingDebug)
public class PerfProbe : MonoBehaviour
{
    private const string GameScene = "SampleScene";
    private const float Warmup = 2f;                  // seconds after the game scene's first frame that are not recorded (shader compiles, first allocations)

    private static PerfProbe _instance;
    private readonly List<float> _frameMs = new List<float>();
    private readonly List<int> _frameMark = new List<int>();
    private readonly List<string> _marks = new List<string>();
    private readonly List<string> _applied = new List<string>();
    private readonly List<SecondSample> _seconds = new List<SecondSample>();

    private ProfilerRecorder _draw, _batches, _tris, _setPass, _casters, _mainThread;
    private float _sceneStart;
    private float _recorded;
    private float _target = 60f;
    private bool _delayedDone;
    private bool _reported;
    private int _gc0;
    private int _currentMark;
    private int? _fps;

    private struct SecondSample
    {
        public float fps, p99Ms, maxMs, draws, batches, tris, setPass, casters, mainMs;
    }

    private readonly List<float> _secFrames = new List<float>();
    private double _secDraws, _secBatches, _secTris, _secSetPass, _secCasters, _secMain;
    private int _secN;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
    private static void Begin()
    {
        if (!Debug.isDebugBuild || OnlineSettings.UrlParameter("perf") == null)
        {
            return;
        }

        var host = new GameObject("PerfProbe");
        DontDestroyOnLoad(host);
        _instance = host.AddComponent<PerfProbe>();
    }

    // Tags the frames that follow (a phase of the benchmark route). No-op without ?perf=1.
    public static void Mark(string label)
    {
        if (_instance != null && !_instance._reported)
        {
            Debug.Log("PERF_MARK " + label);
            _instance._marks.Add(label + "@" + _instance._frameMs.Count);
            _instance._currentMark = _instance._marks.Count;
        }
    }

    public static bool Recording => _instance != null && !_instance._reported;

    // Recorded seconds so far and the length of the run (the benchmark autopilot's clock).
    public static float Elapsed => _instance != null ? _instance._recorded : 0f;
    public static float Duration => _instance != null ? _instance._target : 0f;

    private static string Param(string name) => OnlineSettings.UrlParameter(name);

    private static bool TryFloat(string name, out float value)
    {
        value = 0f;
        string s = Param(name);
        return s != null && float.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out value);
    }

    private void Awake()
    {
        if (TryFloat("perfSeconds", out float seconds) && seconds > 0f)
        {
            _target = seconds;
        }

        _draw = ProfilerRecorder.StartNew(ProfilerCategory.Render, "Draw Calls Count");
        _batches = ProfilerRecorder.StartNew(ProfilerCategory.Render, "Batches Count");
        _tris = ProfilerRecorder.StartNew(ProfilerCategory.Render, "Triangles Count");
        _setPass = ProfilerRecorder.StartNew(ProfilerCategory.Render, "SetPass Calls Count");
        _casters = ProfilerRecorder.StartNew(ProfilerCategory.Render, "Shadow Casters Count");
        _mainThread = ProfilerRecorder.StartNew(ProfilerCategory.Internal, "Main Thread", 1);

        if (Application.isEditor)
        {
            _applied.Add("editor: settings not applied");
        }
        else
        {
            ApplyPipelineSettings();
            if (TryFloat("fps", out float fps))
            {
                _fps = (int)fps;
                _applied.Add("fps=" + _fps);
            }
        }

        SceneManager.sceneLoaded += OnSceneLoaded;
    }

    private void OnDestroy()
    {
        SceneManager.sceneLoaded -= OnSceneLoaded;
        _draw.Dispose();
        _batches.Dispose();
        _tris.Dispose();
        _setPass.Dispose();
        _casters.Dispose();
        _mainThread.Dispose();
    }

    private void OnSceneLoaded(Scene scene, LoadSceneMode mode)
    {
        if (scene.name == GameScene)
        {
            _sceneStart = Time.unscaledTime;
            _delayedDone = false;
        }
    }

    // The pipeline asset and the renderer's features (the player's own copies: nothing is saved).
    private void ApplyPipelineSettings()
    {
        if (!(GraphicsSettings.currentRenderPipeline is UniversalRenderPipelineAsset urp))
        {
            _applied.Add("no URP asset");
            return;
        }

        if (TryFloat("renderScale", out float rs)) { urp.renderScale = rs; _applied.Add("renderScale=" + rs); }
        if (TryFloat("shadows", out float sh)) { SetField(urp, "m_MainLightShadowsSupported", sh > 0f); _applied.Add("shadows=" + sh); }
        if (TryFloat("shadowDistance", out float sd)) { urp.shadowDistance = sd; _applied.Add("shadowDistance=" + sd); }
        if (TryFloat("shadowCascades", out float sc)) { urp.shadowCascadeCount = (int)sc; _applied.Add("shadowCascades=" + (int)sc); }
        if (TryFloat("shadowRes", out float sr)) { urp.mainLightShadowmapResolution = (int)sr; _applied.Add("shadowRes=" + (int)sr); }
        if (TryFloat("softShadows", out float ss)) { SetField(urp, "m_SoftShadowsSupported", ss > 0f); _applied.Add("softShadows=" + ss); }
        if (TryFloat("msaa", out float ms)) { urp.msaaSampleCount = (int)ms; _applied.Add("msaa=" + (int)ms); }
        if (TryFloat("hdr", out float hdr)) { urp.supportsHDR = hdr > 0f; _applied.Add("hdr=" + hdr); }

        if (TryFloat("ssao", out float ssao) && ssao <= 0f)
        {
            int off = 0;
            foreach (ScriptableRendererData data in urp.rendererDataList)
            {
                foreach (ScriptableRendererFeature feature in data.rendererFeatures)
                {
                    if (feature != null && feature.name.Contains("AmbientOcclusion"))
                    {
                        feature.SetActive(false);
                        off++;
                    }
                }
            }

            _applied.Add("ssao=0 (" + off + " feature)");
        }
    }

    // The asset's serialized field, for the few settings without a public setter.
    private static void SetField(UniversalRenderPipelineAsset urp, string field, object value)
    {
        System.Reflection.FieldInfo f = typeof(UniversalRenderPipelineAsset).GetField(field, System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
        if (f != null)
        {
            f.SetValue(urp, value);
        }
    }

    // Things that exist only once the game scene has built its world.
    private void ApplySceneSettings()
    {
        if (Application.isEditor)
        {
            return;
        }

        if (TryFloat("fruitShadows", out float fs))
        {
            int n = 0;
            foreach (Tree tree in FindObjectsByType<Tree>(FindObjectsSortMode.None))
            {
                foreach (MeshRenderer r in tree.GetComponentsInChildren<MeshRenderer>(true))
                {
                    if (r.name.StartsWith("Fruit_"))
                    {
                        r.shadowCastingMode = fs > 0f ? ShadowCastingMode.On : ShadowCastingMode.Off;
                        n++;
                    }
                }
            }

            _applied.Add("fruitShadows=" + fs + " (" + n + " renderers)");
        }

        bool bloomOff = TryFloat("bloom", out float b) && b <= 0f;
        bool vignetteOff = TryFloat("vignette", out float v) && v <= 0f;
        if (bloomOff || vignetteOff)
        {
            foreach (Volume volume in FindObjectsByType<Volume>(FindObjectsSortMode.None))
            {
                VolumeProfile profile = volume.profile;
                if (bloomOff && profile.TryGet(out Bloom bloom)) { bloom.active = false; }
                if (vignetteOff && profile.TryGet(out Vignette vignette)) { vignette.active = false; }
            }

            _applied.Add((bloomOff ? "bloom=0 " : "") + (vignetteOff ? "vignette=0" : ""));
        }

        if (TryFloat("post", out float post) && post <= 0f && Camera.main != null)
        {
            Camera.main.GetUniversalAdditionalCameraData().renderPostProcessing = false;
            _applied.Add("post=0");
        }
    }

    private void Update()
    {
        if (_fps.HasValue && Application.targetFrameRate != _fps.Value)
        {
            Application.targetFrameRate = _fps.Value;       // GameManager sets the config's rate at every session start
        }

        if (_reported || SceneManager.GetActiveScene().name != GameScene)
        {
            return;
        }

        float sinceStart = Time.unscaledTime - _sceneStart;
        if (!_delayedDone && sinceStart > 1f)
        {
            _delayedDone = true;
            ApplySceneSettings();
        }

        // Only frames in which the game runs count: not an instruction screen, not a released mouse, not the warm-up.
        if (Time.timeScale <= 0f || sinceStart < Warmup)
        {
            return;
        }

        if (_frameMs.Count == 0)
        {
            Debug.Log("PERF_START");
            _gc0 = GC.CollectionCount(0);
        }

        float dt = Time.unscaledDeltaTime;
        _frameMs.Add(dt * 1000f);
        _frameMark.Add(_currentMark);
        _recorded += dt;

        _secFrames.Add(dt * 1000f);
        _secDraws += Last(_draw);
        _secBatches += Last(_batches);
        _secTris += Last(_tris);
        _secSetPass += Last(_setPass);
        _secCasters += Last(_casters);
        _secMain += Last(_mainThread) / 1e6;
        _secN++;
        if (_secFrames.Count > 0 && SecondsSum(_secFrames) >= 1000f)
        {
            FlushSecond();
        }

        if (_recorded >= _target)
        {
            Report();
        }
    }

    private static double Last(ProfilerRecorder r) => r.Valid && r.Count > 0 ? r.LastValue : 0.0;

    private static float SecondsSum(List<float> ms)
    {
        float s = 0f;
        foreach (float m in ms) { s += m; }
        return s;
    }

    private void FlushSecond()
    {
        var sorted = new List<float>(_secFrames);
        sorted.Sort();
        float sum = SecondsSum(_secFrames);
        _seconds.Add(new SecondSample
        {
            fps = _secFrames.Count * 1000f / sum,
            p99Ms = sorted[Mathf.Min(sorted.Count - 1, (int)(sorted.Count * 0.99f))],
            maxMs = sorted[sorted.Count - 1],
            draws = (float)(_secDraws / _secN), batches = (float)(_secBatches / _secN), tris = (float)(_secTris / _secN),
            setPass = (float)(_secSetPass / _secN), casters = (float)(_secCasters / _secN), mainMs = (float)(_secMain / _secN)
        });
        _secFrames.Clear();
        _secDraws = _secBatches = _secTris = _secSetPass = _secCasters = _secMain = 0.0;
        _secN = 0;
    }

    private static string F(float v) => v.ToString("0.##", CultureInfo.InvariantCulture);

    private static float Percentile(List<float> sorted, float q) => sorted.Count == 0 ? 0f : sorted[Mathf.Min(sorted.Count - 1, (int)(sorted.Count * q))];

    private void Report()
    {
        _reported = true;
        var sorted = new List<float>(_frameMs);
        sorted.Sort();
        float mean = _frameMs.Count > 0 ? SecondsSum(_frameMs) / _frameMs.Count : 0f;
        int over16 = 0, over33 = 0, over50 = 0;
        foreach (float m in _frameMs)
        {
            if (m > 16.7f) { over16++; }
            if (m > 33.4f) { over33++; }
            if (m > 50f) { over50++; }
        }

        BuildInfo build = BuildInfo.Read();
        var sb = new StringBuilder(64 * 1024);
        sb.Append("{\"settings\":[");
        for (int i = 0; i < _applied.Count; i++) { sb.Append(i > 0 ? "," : "").Append('"').Append(_applied[i].Replace("\"", "'")).Append('"'); }
        sb.Append("],\"env\":{");
        sb.Append("\"gpu\":\"").Append(SystemInfo.graphicsDeviceName.Replace("\"", "'")).Append("\",");
        sb.Append("\"api\":\"").Append(SystemInfo.graphicsDeviceType).Append("\",");
        sb.Append("\"width\":").Append(Screen.width).Append(",\"height\":").Append(Screen.height).Append(',');
        sb.Append("\"quality\":\"").Append(QualitySettings.names[QualitySettings.GetQualityLevel()]).Append("\",");
        sb.Append("\"targetFrameRate\":").Append(Application.targetFrameRate).Append(',');
        sb.Append("\"commit\":\"").Append(build != null ? build.commit : "").Append("\",\"dirty\":").Append(build != null && build.dirty ? "true" : "false").Append("},");
        sb.Append("\"summary\":{\"frames\":").Append(_frameMs.Count).Append(",\"seconds\":").Append(F(_recorded));
        sb.Append(",\"meanMs\":").Append(F(mean)).Append(",\"p50Ms\":").Append(F(Percentile(sorted, 0.5f)));
        sb.Append(",\"p95Ms\":").Append(F(Percentile(sorted, 0.95f))).Append(",\"p99Ms\":").Append(F(Percentile(sorted, 0.99f)));
        sb.Append(",\"maxMs\":").Append(F(sorted.Count > 0 ? sorted[sorted.Count - 1] : 0f));
        sb.Append(",\"over16\":").Append(over16).Append(",\"over33\":").Append(over33).Append(",\"over50\":").Append(over50);
        sb.Append(",\"gcCollections\":").Append(GC.CollectionCount(0) - _gc0);
        sb.Append(",\"managedMB\":").Append(F(GC.GetTotalMemory(false) / 1048576f)).Append("},");
        sb.Append("\"marks\":[");
        for (int i = 0; i < _marks.Count; i++) { sb.Append(i > 0 ? "," : "").Append('"').Append(_marks[i]).Append('"'); }
        sb.Append("],\"seconds\":[");
        for (int i = 0; i < _seconds.Count; i++)
        {
            SecondSample s = _seconds[i];
            sb.Append(i > 0 ? "," : "").Append('[').Append(F(s.fps)).Append(',').Append(F(s.p99Ms)).Append(',').Append(F(s.maxMs)).Append(',')
              .Append(F(s.draws)).Append(',').Append(F(s.batches)).Append(',').Append(F(s.tris)).Append(',').Append(F(s.setPass)).Append(',')
              .Append(F(s.casters)).Append(',').Append(F(s.mainMs)).Append(']');
        }

        sb.Append("],\"secondsColumns\":\"fps,p99Ms,maxMs,draws,batches,tris,setPass,shadowCasters,mainThreadMs\",\"frames\":[");
        for (int i = 0; i < _frameMs.Count; i++) { sb.Append(i > 0 ? "," : "").Append(F(_frameMs[i])); }
        sb.Append("]}");
        // A browser's console line is cut at about 8 KB: send the result in pieces ("PERF_PART i n text"), which perf_browser.mjs joins.
        string all = sb.ToString();
        const int piece = 3000;
        int parts = (all.Length + piece - 1) / piece;
        for (int i = 0; i < parts; i++)
        {
            Debug.Log("PERF_PART " + i + " " + parts + " " + all.Substring(i * piece, Mathf.Min(piece, all.Length - i * piece)));
        }
    }
}
