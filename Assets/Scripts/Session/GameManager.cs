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

    // The study's screens count sessions: "Session 3 of 4".
    public static int SessionCount => AllSessionConfigs?.Count ?? 0;

    public static int SessionNumber => Mathf.Max(1, CurrentSessionIndex + 1);

    public static string PartLabel
    {
        get
        {
            bool inRange = AllSessionConfigs != null && CurrentSessionIndex >= 0 && CurrentSessionIndex < AllSessionConfigs.Count;
            string label = inRange && AllSessionConfigs[CurrentSessionIndex] != null ? AllSessionConfigs[CurrentSessionIndex].SessionLabel : "";
            return string.IsNullOrEmpty(label) ? $"Session {SessionNumber} of {SessionCount}" : label;
        }
    }

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
                ? RunModes.Apply(chosen)
                : new List<SessionConfig>();
            CurrentSessionIndex = 0;
#if UNITY_EDITOR
            // Foraging > Experiments > "Start at part": the Editor plays an experiment from a later part (1 = the first). Never in a build.
            if (!string.IsNullOrEmpty(UnityEditor.EditorPrefs.GetString("Foraging.Experiment", "")))
            {
                CurrentSessionIndex = Mathf.Clamp(UnityEditor.EditorPrefs.GetInt("Foraging.StartPart", 1) - 1, 0, Mathf.Max(0, AllSessionConfigs.Count - 1));
            }
#endif
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

        if (RunModes.Short < 1f)
        {
            Debug.LogWarning($"GameManager: reduced run, sessions at {RunModes.Short:0.##} of their length.");
            activeConfig = activeConfig.ScaledCopy(RunModes.Short);
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

        AimCrosshair.Build(harvestUI != null ? harvestUI.GetComponent<Canvas>() : null, harvestManager, activeConfig);
        RankingBreak.Create(activeConfig, world, treeGenerator, playerController, cameraController, harvestManager, sunController, harvestUI, dataLogger, sessionTimerUI);     // none unless the session has breaks

        TutorialHints.Create(activeConfig, world, playerController, sunController, dataLogger);     // none unless the session has a hints file

        FruitMaterialManager.SetSessionConfig(activeConfig);
        Music.Volume = activeConfig.MusicVolume;
        Music.Stop();                                                    // the score screen's music ended with the last scene; none plays during a session
    }

    public static void AdvanceSession()
    {
        CurrentSessionIndex++;
    }
}

