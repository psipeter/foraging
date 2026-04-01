using UnityEngine;

[DefaultExecutionOrder(-20)]
public class GameManager : MonoBehaviour
{
    [SerializeField] public SessionConfig sessionConfig;

    [SerializeField] private SunController sunController;
    [SerializeField] private HarvestManager harvestManager;
    [SerializeField] private TerrainManager terrainManager;
    [SerializeField] private TreeGenerator treeGenerator;
    [SerializeField] private PlayerController playerController;
    [SerializeField] private DataLogger dataLogger;
    [SerializeField] private SessionTimerUI sessionTimerUI;

    public static GameManager Instance { get; private set; }

    private void Awake()
    {
        Instance = this;

        if (sessionConfig == null)
        {
            Debug.LogWarning("GameManager: SessionConfig is not assigned.");
            return;
        }

        if (sunController != null)
        {
            sunController.sessionConfig = sessionConfig;
        }

        if (harvestManager != null)
        {
            harvestManager.sessionConfig = sessionConfig;
        }

        if (terrainManager != null)
        {
            terrainManager.sessionConfig = sessionConfig;
        }

        if (treeGenerator != null)
        {
            treeGenerator.sessionConfig = sessionConfig;
        }

        if (dataLogger != null)
        {
            dataLogger.sessionConfig = sessionConfig;
        }

        if (sessionTimerUI != null)
        {
            sessionTimerUI.sessionConfig = sessionConfig;
        }
    }
}

