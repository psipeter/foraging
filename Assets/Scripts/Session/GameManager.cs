using System.Collections.Generic;
using UnityEngine;

[DefaultExecutionOrder(-20)]
public class GameManager : MonoBehaviour
{
    [Tooltip("The default design: the ordered session list (P, its Interlude, S1, its Interlude, ...).")]
    [SerializeField] private List<SessionConfig> sessionConfigs;
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
            List<SessionConfig> chosen = sessionConfigs;
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

    // The Editor's Foraging > Quick test toggle (an EditorPref, so it never reaches a build) or -quick on the command line of a standalone build.
    private static bool QuickTestRequested()
    {
#if UNITY_EDITOR
        if (UnityEditor.EditorPrefs.GetBool("Foraging.QuickTest", false))
        {
            return true;
        }
#endif
        return Application.platform != RuntimePlatform.WebGLPlayer && System.Array.IndexOf(System.Environment.GetCommandLineArgs(), "-quick") >= 0;
    }

    public static void AdvanceSession()
    {
        CurrentSessionIndex++;
    }
}

