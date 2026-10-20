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
    [SerializeField] private InstructionsPanel instructionsPanel;

    public static GameManager Instance { get; private set; }

    public static int CurrentSessionIndex = 0;
    public static List<SessionConfig> AllSessionConfigs;

    public static float LastSessionScore = 0f;

    public static int TotalSessions => AllSessionConfigs?.Count ?? 0;
    public static bool IsLastSession => TotalSessions == 0 || CurrentSessionIndex >= TotalSessions - 1;

    // Practice sessions are excluded from the "Session x/N" numbering.
    public static int ExperimentSessionCount
    {
        get
        {
            int count = 0;
            if (AllSessionConfigs != null)
            {
                foreach (SessionConfig config in AllSessionConfigs)
                {
                    if (config != null && !config.IsPractice) count++;
                }
            }
            return count;
        }
    }

    // 1-based number of the config at `index` among non-practice sessions; 0 for a practice session.
    public static int ExperimentSessionNumber(int index)
    {
        if (AllSessionConfigs == null || index < 0 || index >= AllSessionConfigs.Count) return 0;
        if (AllSessionConfigs[index] != null && AllSessionConfigs[index].IsPractice) return 0;
        int number = 0;
        for (int i = 0; i <= index; i++)
        {
            if (AllSessionConfigs[i] != null && !AllSessionConfigs[i].IsPractice) number++;
        }
        return number;
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

        if (instructionsPanel != null)
        {
            instructionsPanel.sessionConfig = activeConfig;
        }

        FruitMaterialManager.SetSessionConfig(activeConfig);
    }

    public static void AdvanceSession()
    {
        CurrentSessionIndex++;
    }
}

