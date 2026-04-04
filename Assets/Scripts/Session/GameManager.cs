using System.Collections.Generic;
using System.IO;
using UnityEngine;

[DefaultExecutionOrder(-20)]
public class GameManager : MonoBehaviour
{
    [SerializeField] public List<SessionConfig> sessionConfigs;

    [SerializeField] private SunController sunController;
    [SerializeField] private HarvestManager harvestManager;
    [SerializeField] private TerrainManager terrainManager;
    [SerializeField] private TreeGenerator treeGenerator;
    [SerializeField] private BorderWalls borderWalls;
    [SerializeField] private PlayerController playerController;
    [SerializeField] private CameraController cameraController;
    [SerializeField] private DataLogger dataLogger;
    [SerializeField] private SessionTimerUI sessionTimerUI;

    public static GameManager Instance { get; private set; }

    public static int CurrentSessionIndex = 0;
    public static List<SessionConfig> AllSessionConfigs;

    public static float LastSessionScore = 0f;
    public static bool HasCompletedSession = false;

    public static int TotalSessions => AllSessionConfigs?.Count ?? 0;
    public static bool IsLastSession => TotalSessions == 0 || CurrentSessionIndex >= TotalSessions - 1;

    public static void LogDiagnostic(string message)
    {
        string path = Path.Combine(
            Path.GetDirectoryName(Application.dataPath),
            "diagnostic.log");
        File.AppendAllText(path, $"{System.DateTime.Now}: {message}\n");
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

        if (sunController != null)
        {
            sunController.sessionConfig = activeConfig;
        }

        if (harvestManager != null)
        {
            harvestManager.sessionConfig = activeConfig;
        }

        if (terrainManager != null)
        {
            terrainManager.sessionConfig = activeConfig;
        }

        if (treeGenerator != null)
        {
            treeGenerator.sessionConfig = activeConfig;
        }

        if (borderWalls != null)
        {
            borderWalls.sessionConfig = activeConfig;
            borderWalls.terrainManager = terrainManager;
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

        FruitMaterialManager.SetSessionConfig(activeConfig);

        LogDiagnostic($"GameManager.Awake complete: activeConfig={activeConfig != null}, treeGenerator={treeGenerator != null}, terrainManager={terrainManager != null}");
    }

    public static void AdvanceSession()
    {
        CurrentSessionIndex++;
    }
}

