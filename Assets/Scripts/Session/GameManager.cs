using System.Collections.Generic;
using UnityEngine;

[DefaultExecutionOrder(-20)]
public class GameManager : MonoBehaviour
{
    [SerializeField] public List<SessionConfig> sessionConfigs;

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

    public static GameManager Instance { get; private set; }

    public static int CurrentSessionIndex = 0;
    public static List<SessionConfig> AllSessionConfigs;

    public static float LastSessionScore = 0f;

    // Running totals for the final screen. Practice sessions and practice Interludes are excluded.
    public static float SessionScoreTotal = 0f;
    public static int InterludeTrialsScored = 0;
    public static int InterludeCorrectCount = 0;
    public static float InterludeBonus = 0f;

    // Tally for the Interlude currently being played (shown on its end screen); reset when it starts.
    public static int ThisInterludeTrials = 0;
    public static int ThisInterludeCorrect = 0;
    public static float ThisInterludeBonus = 0f;

    public static void BeginInterludeTally()
    {
        ThisInterludeTrials = 0;
        ThisInterludeCorrect = 0;
        ThisInterludeBonus = 0f;
    }

    public static void RecordInterludeTrial(bool correct, float bonus)
    {
        InterludeTrialsScored++;
        ThisInterludeTrials++;
        if (correct)
        {
            InterludeCorrectCount++;
            ThisInterludeCorrect++;
        }

        InterludeBonus += bonus;
        ThisInterludeBonus += bonus;
    }

    public static int TotalSessions => AllSessionConfigs?.Count ?? 0;
    public static bool IsLastSession => TotalSessions == 0 || CurrentSessionIndex >= TotalSessions - 1;

    // Practice sessions and Interludes are excluded from the "Session x/N" numbering.
    private static bool IsAnalyzedSession(SessionConfig config)
    {
        return config != null && !config.IsPractice && !config.IsInterlude;
    }

    public static int ExperimentSessionCount
    {
        get
        {
            int count = 0;
            if (AllSessionConfigs != null)
            {
                foreach (SessionConfig config in AllSessionConfigs)
                {
                    if (IsAnalyzedSession(config)) count++;
                }
            }
            return count;
        }
    }

    // 1-based number of the config at `index` among analyzed sessions; 0 for a practice session or an Interlude.
    public static int ExperimentSessionNumber(int index)
    {
        if (AllSessionConfigs == null || index < 0 || index >= AllSessionConfigs.Count) return 0;
        if (!IsAnalyzedSession(AllSessionConfigs[index])) return 0;
        int number = 0;
        for (int i = 0; i <= index; i++)
        {
            if (IsAnalyzedSession(AllSessionConfigs[i])) number++;
        }
        return number;
    }

    // Number of an Interlude: how many analyzed sessions come before it (so the Interlude after S1 is 1).
    public static int InterludeNumber(int index)
    {
        if (AllSessionConfigs == null || index < 0 || index >= AllSessionConfigs.Count) return 0;
        int number = 0;
        for (int i = 0; i < index; i++)
        {
            if (IsAnalyzedSession(AllSessionConfigs[i])) number++;
        }
        return number;
    }

    // Name of the stage after the current one, for the end-screen prompt ("Session 2/4", "Interlude 1/4").
    public static string NextStageLabel()
    {
        int next = CurrentSessionIndex + 1;
        if (AllSessionConfigs == null || next < 0 || next >= AllSessionConfigs.Count || AllSessionConfigs[next] == null)
        {
            return "the next stage";
        }

        SessionConfig config = AllSessionConfigs[next];
        if (config.IsInterlude)
        {
            return config.IsPractice ? "the Interlude" : $"Interlude {InterludeNumber(next)}/{ExperimentSessionCount}";
        }

        return config.IsPractice ? "the practice session" : $"Session {ExperimentSessionNumber(next)}/{ExperimentSessionCount}";
    }

    private void Awake()
    {
        Instance = this;

        if (AllSessionConfigs == null || AllSessionConfigs.Count == 0)
        {
            AllSessionConfigs = sessionConfigs != null
                ? new List<SessionConfig>(sessionConfigs)
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

        RenderSettings.fog = activeConfig.FogEnabled;
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
    }

    public static void AdvanceSession()
    {
        CurrentSessionIndex++;
    }
}

