using UnityEngine;

[CreateAssetMenu(
    fileName = "SessionConfig",
    menuName = "Foraging/Session Config")]
public class SessionConfig : ScriptableObject
{
    [Header("Session")]
    [SerializeField] private float sessionDuration = 120f;
    [SerializeField] private int worldSeed;
    [SerializeField] private int treeCount = 50;

    [Header("Reward")]
    [SerializeField] private RewardFunction rewardFunction = new RewardFunction();
    [SerializeField] private float rewardStd = 1.0f;

    [Header("Player")]
    [SerializeField] private float playerMoveSpeed = 5f;
    [SerializeField] private float fruitHarvestDuration = 0.8f;
    [SerializeField] private CameraMode cameraMode = CameraMode.Isometric;
    [SerializeField] private float mouseSensitivity = 120f;
    [SerializeField] private float cameraSmoothing = 8f;
    [SerializeField] private Vector3 isometricCameraPosition = new Vector3(0f, 20f, -15f);
    [SerializeField] private Vector3 isometricCameraRotation = new Vector3(50f, 0f, 0f);
    [SerializeField] private Vector3 explorationCameraPosition = new Vector3(0f, 12f, -18f);
    [SerializeField] private Vector3 explorationCameraRotation = new Vector3(30f, 0f, 0f);

    [Header("Trees")]
    [SerializeField] private int fruitCount = 10;
    [SerializeField] private float fruitRadius = 0.15f;
    [SerializeField] private Color fruitColorLow = new Color(0.2f, 0.4f, 1.0f);
    [SerializeField] private Color fruitColorHigh = new Color(1.0f, 0.5f, 0.1f);
    [SerializeField] private Vector2 shapeRange = new Vector2(0f, 1f);
    [SerializeField] private Vector2 canopyWidthRange = new Vector2(2.0f, 5.0f);
    [SerializeField] private Vector2 canopyHeightRange = new Vector2(1.2f, 2.8f);
    [SerializeField] private float highlightRadiusPadding = 1.2f;
    [SerializeField] private float fruitColorPreservation = 0.5f;

    [Header("Terrain")]
    [SerializeField] private float terrainNoiseFrequency = 4f;
    [SerializeField] private int terrainNoiseOctaves = 1;
    [SerializeField] private float terrainMaxElevation = 3f;
    [SerializeField] private int terrainMeshResolution = 64;
    [SerializeField] private float worldHalfExtent = 50f;

    [Header("Lighting")]
    [SerializeField] private float sunArcHeight = 60f;
    [SerializeField] private float minSunElevation = 5f;
    [SerializeField] private float sunIntensityDawn = 0.4f;
    [SerializeField] private float sunIntensityNoon = 1.2f;
    [SerializeField] private Color skyColorDawn = new Color(0.8f, 0.4f, 0.2f);
    [SerializeField] private Color skyColorNoon = new Color(0.3f, 0.6f, 1.0f);

    [Header("Border")]
    [SerializeField] private float borderWallHeight = 20f;
    [SerializeField] private Color borderWallColor = new Color(0.25f, 0.20f, 0.15f, 1.0f);

    public RewardFunction RewardFunction => rewardFunction;
    public float SessionDuration => sessionDuration;
    public int WorldSeed => worldSeed;
    public int TreeCount => treeCount;
    public int FruitCount => fruitCount;
    public float FruitRadius => fruitRadius;
    public float PlayerMoveSpeed => playerMoveSpeed;
    public float FruitHarvestDuration => fruitHarvestDuration;
    public float HarvestDuration => fruitHarvestDuration * Mathf.Max(1, fruitCount);
    public float RewardStd => rewardStd;
    public Vector2 ShapeRange => shapeRange;
    public Vector2 CanopyWidthRange => canopyWidthRange;
    public Vector2 CanopyHeightRange => canopyHeightRange;
    public float HighlightRadiusPadding => highlightRadiusPadding;
    public Color FruitColorLow => fruitColorLow;
    public Color FruitColorHigh => fruitColorHigh;
    public float FruitColorPreservation => fruitColorPreservation;
    public float TerrainNoiseFrequency => terrainNoiseFrequency;
    public int TerrainNoiseOctaves => terrainNoiseOctaves;
    public float TerrainMaxElevation => terrainMaxElevation;
    public int TerrainMeshResolution => terrainMeshResolution;
    public float WorldHalfExtent => worldHalfExtent;
    public float BorderWallHeight => borderWallHeight;
    public Color BorderWallColor => borderWallColor;
    public float SunArcHeight => sunArcHeight;
    public float MinSunElevation => minSunElevation;
    public float SunIntensityDawn => sunIntensityDawn;
    public float SunIntensityNoon => sunIntensityNoon;
    public Color SkyColorDawn => skyColorDawn;
    public Color SkyColorNoon => skyColorNoon;
    public CameraMode CameraMode => cameraMode;
    public float MouseSensitivity => mouseSensitivity;
    public float CameraSmoothing => cameraSmoothing;
    public Vector3 IsometricCameraPosition => isometricCameraPosition;
    public Vector3 IsometricCameraRotation => isometricCameraRotation;
    public Vector3 ExplorationCameraPosition => explorationCameraPosition;
    public Vector3 ExplorationCameraRotation => explorationCameraRotation;

    public float EvaluateReward(TreeAttributes attributes)
    {
        return rewardFunction.Evaluate(attributes);
    }
}
