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
    }

    public static int TotalSessions => AllSessionConfigs?.Count ?? 0;
    public static bool IsLastSession => TotalSessions == 0 || CurrentSessionIndex >= TotalSessions - 1;

    // A session and an Interlude are both just parts in the study's screens: "Part 3 of 14".
    public static int PartNumber => CurrentSessionIndex + 1;
    public static int PartCount => TotalSessions;

    private void Awake()
    {
        if (AllSessionConfigs == null || AllSessionConfigs.Count == 0)
        {
            ExperimentConfig experiment = ActiveExperiment;
#if UNITY_EDITOR
            if (experiment == null)
            {
                // Playing this scene directly from the Editor's Foraging > Experiments window.
                string code = Bootstrap.DirectExperiment();
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
        Music.Volume = activeConfig.MusicVolume;
        Music.Stop();                                                    // the score screen's music ended with the last scene; none plays during a session
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

    public static void AdvanceSession()
    {
        CurrentSessionIndex++;
    }
}

