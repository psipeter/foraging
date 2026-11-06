using System.Collections.Generic;
using UnityEngine;

[DefaultExecutionOrder(-20)]
public class GameManager : MonoBehaviour
{
    [Tooltip("The experiment played when the game starts from this scene without the menu (the Editor, a build without the menu): its session list becomes AllSessionConfigs.")]
    [SerializeField] private ExperimentConfig defaultExperiment;
    [SerializeField] private SunController sunController;
    [SerializeField] private HarvestManager harvestManager;
    [SerializeField] private TerrainManager terrainManager;
    [SerializeField] private TreeGenerator treeGenerator;
    [SerializeField] private PlayerController playerController;
    [SerializeField] private CameraController cameraController;
    [SerializeField] private DataLogger dataLogger;
    [SerializeField] private SessionTimerUI sessionTimerUI;
    [SerializeField] private HarvestUI harvestUI;
    [SerializeField] private FeedbackAudio feedbackAudio;
    [SerializeField] private AmbientAudio ambientAudio;
    [SerializeField] private InstructionsPanel instructionsPanel;
    [SerializeField] private InterludeManager interludeManager;

    [Tooltip("Local quick testing (the Foraging > Quick test menu item in the Editor, or -quick on a standalone build): a practice session lasts this long, ...")]
    [SerializeField] private float quickPracticeSeconds = 15f;
    [Tooltip("... any other session this long, and an Interlude plays at most this many of its trials. Used on a copy of the session asset; the assets are never changed.")]
    [SerializeField] private float quickSessionSeconds = 30f;
    [SerializeField] private int quickInterludeTrials = 5;

    public static int CurrentSessionIndex = 0;
    public static List<SessionConfig> AllSessionConfigs;

    // The experiment chosen in the menu (null: defaultExperiment). Set it through BeginExperiment, before the game scene loads.
    public static ExperimentConfig ActiveExperiment;

    // Starts `experiment` from its first session with fresh totals (the menu calls this; scene reloads between sessions keep the statics).
    public static void BeginExperiment(ExperimentConfig experiment)
    {
        ActiveExperiment = experiment;
        AllSessionConfigs = null;
        CurrentSessionIndex = 0;
        SessionScoreTotal = 0f;
        InterludeBonus = 0f;
    }

    // Running totals for the final screen. Practice sessions and practice Interludes are excluded.
    public static float SessionScoreTotal = 0f;
    public static float InterludeBonus = 0f;

    // Continuing an interrupted run: the running totals of the sessions already finished (as the end screens add them up).
    public static void RestoreTotals(ResumeReply resume)
    {
        SessionScoreTotal = 0f;
        foreach (PreviousSession s in resume.previous)
        {
            if (!s.is_practice && !s.is_interlude)
            {
                SessionScoreTotal += s.score;
            }
        }

        InterludeBonus = resume.previous_interlude.bonus;
    }

    public static int TotalSessions => AllSessionConfigs?.Count ?? 0;
    public static bool IsLastSession => TotalSessions == 0 || CurrentSessionIndex >= TotalSessions - 1;

    // "Session x of N" and "Interlude x of N" count only analyzed sessions (not practice, not Interludes).
    private static bool IsAnalyzed(int index)
    {
        SessionConfig config = AllSessionConfigs[index];
        return config != null && !config.IsPractice && !config.IsInterlude;
    }

    private static int AnalyzedBefore(int index)
    {
        int count = 0;
        for (int i = 0; i < index; i++)
        {
            if (IsAnalyzed(i)) count++;
        }
        return count;
    }

    public static int ExperimentSessionCount => AnalyzedBefore(TotalSessions);

    // 1-based number of the session at `index`; 0 for a practice session or an Interlude.
    public static int ExperimentSessionNumber(int index) =>
        index >= 0 && index < TotalSessions && IsAnalyzed(index) ? AnalyzedBefore(index) + 1 : 0;

    // Number of the Interlude at `index`: the analyzed sessions before it (so the Interlude after S1 is 1).
    public static int InterludeNumber(int index) => index >= 0 && index < TotalSessions ? AnalyzedBefore(index) : 0;

    private void Awake()
    {
        if (AllSessionConfigs == null || AllSessionConfigs.Count == 0)
        {
            ExperimentConfig experiment = ActiveExperiment;
#if UNITY_EDITOR
            if (experiment == null)
            {
                // Playing this scene directly from the Editor's Foraging > Experiments window.
                string code = UnityEditor.EditorPrefs.GetString("Foraging.Experiment", "");
                experiment = string.IsNullOrEmpty(code) ? null : ExperimentCatalog.Load()?.Find(code);
            }
#endif
            if (experiment == null)
            {
                experiment = defaultExperiment;
            }

            List<SessionConfig> chosen = experiment != null ? experiment.Sessions : null;
            AllSessionConfigs = chosen != null
                ? new List<SessionConfig>(chosen)
                : new List<SessionConfig>();
            CurrentSessionIndex = 0;
        }

        if (AllSessionConfigs == null || AllSessionConfigs.Count == 0)
        {
            Debug.LogWarning("GameManager: No SessionConfigs assigned.");
            return;
        }

        if (CurrentSessionIndex < 0 || CurrentSessionIndex >= AllSessionConfigs.Count)
        {
            CurrentSessionIndex = 0;
        }

        SessionConfig activeConfig = AllSessionConfigs[CurrentSessionIndex];
        if (activeConfig == null)
        {
            Debug.LogWarning("GameManager: Active SessionConfig is null.");
            return;
        }

        if (QuickTestRequested())
        {
            Debug.LogWarning($"GameManager: quick test mode ({quickPracticeSeconds} s practice, {quickSessionSeconds} s sessions, {quickInterludeTrials} Interlude trials).");
            activeConfig = activeConfig.QuickCopy(quickPracticeSeconds, quickSessionSeconds, quickInterludeTrials);
        }

        RenderSettings.fog = activeConfig.FogEnabled;
        if (activeConfig.FogEnabled)
        {
            RenderSettings.fogMode = FogMode.Linear;
            RenderSettings.fogStartDistance = activeConfig.FogStartDistance;
            RenderSettings.fogEndDistance = Mathf.Max(activeConfig.FogEndDistance, activeConfig.FogStartDistance + 1f);
        }
        QualitySettings.vSyncCount = 0;
        Application.targetFrameRate = activeConfig.TargetFrameRate;

        if (sunController != null)
        {
            sunController.sessionConfig = activeConfig;
        }

        if (harvestManager != null)
        {
            harvestManager.sessionConfig = activeConfig;
        }

        WorldData world = WorldData.Load(activeConfig);
        if (world != null)
        {
            foreach (string name in world.FindMismatches(activeConfig))
            {
                Debug.LogWarning($"World file {world.Path} was generated with a different '{name}' than {activeConfig.name} now has; re-run scripts/world.py.");
            }
        }

        if (terrainManager != null)
        {
            terrainManager.sessionConfig = activeConfig;
            terrainManager.world = world;
        }

        if (treeGenerator != null)
        {
            treeGenerator.sessionConfig = activeConfig;
            treeGenerator.world = world;
        }

        if (playerController != null)
        {
            playerController.sessionConfig = activeConfig;
            playerController.moveSpeed = activeConfig.PlayerMoveSpeed;
        }

        if (cameraController != null)
        {
            cameraController.sessionConfig = activeConfig;
        }

        if (dataLogger != null)
        {
            dataLogger.sessionConfig = activeConfig;
        }

        if (sessionTimerUI != null)
        {
            sessionTimerUI.sessionConfig = activeConfig;
            sessionTimerUI.interludeManager = interludeManager;
        }

        if (harvestUI != null)
        {
            harvestUI.sessionConfig = activeConfig;
        }

        if (feedbackAudio != null)
        {
            feedbackAudio.sessionConfig = activeConfig;
        }

        if (ambientAudio != null)
        {
            ambientAudio.sessionConfig = activeConfig;
        }

        if (instructionsPanel != null)
        {
            instructionsPanel.sessionConfig = activeConfig;
        }

        if (interludeManager != null)
        {
            interludeManager.sessionConfig = activeConfig;
            interludeManager.harvestUI = harvestUI;
            interludeManager.dataLogger = dataLogger;
        }

        FruitMaterialManager.SetSessionConfig(activeConfig);
        _current = this;
        FetchNextSession();
    }

    // The Editor's Foraging > Quick test toggle (an EditorPref, so it never reaches a build), -quick on the command line of a standalone build, or ?quick=1 in the
    // address of a browser development build (a release build ignores it: a link must not be able to shorten a participant's sessions).
    private static bool QuickTestRequested()
    {
#if UNITY_EDITOR
        if (UnityEditor.EditorPrefs.GetBool("Foraging.QuickTest", false))
        {
            return true;
        }
#endif
        if (Application.platform == RuntimePlatform.WebGLPlayer)
        {
            return Debug.isDebugBuild && OnlineSettings.UrlParameter("quick") != null;
        }

        return System.Array.IndexOf(System.Environment.GetCommandLineArgs(), "-quick") >= 0;
    }

    // The next session's files, fetched while this one runs (a browser; with the experiment's files already loaded this finds nothing to do). The end
    // screen waits for them (NextSessionReady) rather than load a session whose world is not there.
    private bool _fetching;
    private static GameManager _current;

    // The end screen's call while it waits: fetches the next session's files again if the first try failed.
    public static void EnsureNextSession()
    {
        if (_current != null)
        {
            _current.FetchNextSession();
        }
    }

    public static bool NextSessionReady
    {
        get
        {
            int next = CurrentSessionIndex + 1;
            return AllSessionConfigs == null || next >= AllSessionConfigs.Count || StreamingData.AllLoaded(ExperimentConfig.FilesOf(AllSessionConfigs[next]));
        }
    }

    // Starts (or, after a failure, restarts) the fetch of the next session's files.
    public void FetchNextSession()
    {
        if (!_fetching && !NextSessionReady)
        {
            StartCoroutine(FetchNext());
        }
    }

    private System.Collections.IEnumerator FetchNext()
    {
        _fetching = true;
        yield return StreamingData.Fetch(ExperimentConfig.FilesOf(AllSessionConfigs[CurrentSessionIndex + 1]), null,
            reason => Debug.LogWarning("GameManager: " + reason));
        _fetching = false;
    }

    public static void AdvanceSession()
    {
        CurrentSessionIndex++;
    }
}

