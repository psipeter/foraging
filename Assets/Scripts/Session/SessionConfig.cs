using UnityEngine;

[CreateAssetMenu(
    fileName = "SessionConfig",
    menuName = "Foraging/Session Config")]
public class SessionConfig : ScriptableObject
{
    [SerializeField] private SessionConfig baseConfig;

    [SerializeField] private RewardFunction rewardFunction = new RewardFunction();
    [SerializeField] private float sessionDuration = 120f;
    [SerializeField] private int worldSeed;
    [SerializeField] private int treeCount = 50;
    [SerializeField] private int fruitCount = 10;
    [SerializeField] private float fruitRadius = 0.15f;
    [SerializeField] private float playerMoveSpeed = 5f;
    [SerializeField] private float fruitHarvestDuration = 0.8f;
    [SerializeField] private float rewardStd = 1.0f;

    // Shape range
    [SerializeField] private Vector2 shapeRange = new Vector2(0f, 1f);
    // Maps attribute 0..1 to canopy scale range
    [SerializeField] private Vector2 canopyWidthRange = new Vector2(2.0f, 5.0f);
    [SerializeField] private Vector2 canopyHeightRange = new Vector2(1.2f, 2.8f);
    [SerializeField] private float highlightRadiusPadding = 1.2f;

    // Fruit color range
    [SerializeField] private Color fruitColorLow = new Color(0.2f, 0.4f, 1.0f);
    [SerializeField] private Color fruitColorHigh = new Color(1.0f, 0.5f, 0.1f);
    [SerializeField] private float fruitColorPreservation = 0.5f;

    // Terrain noise
    [SerializeField] private float terrainNoiseFrequency = 4f;
    [SerializeField] private int terrainNoiseOctaves = 1;

    [SerializeField] private float terrainMaxElevation = 3f;
    [SerializeField] private int terrainMeshResolution = 64;
    [SerializeField] private float worldHalfExtent = 50f;
    [SerializeField] private float borderWallHeight = 20f;
    [SerializeField] private Color borderWallColor = new Color(0.25f, 0.20f, 0.15f, 1.0f);

    // Sun arc
    [SerializeField] private float sunArcHeight = 60f;
    [SerializeField] private float minSunElevation = 5f;
    [SerializeField] private float sunIntensityDawn = 0.4f;
    [SerializeField] private float sunIntensityNoon = 1.2f;

    // Sky color (dawn ↔ noon; ambient derived in SunController)
    [SerializeField] private Color skyColorDawn = new Color(0.8f, 0.4f, 0.2f);
    [SerializeField] private Color skyColorNoon = new Color(0.3f, 0.6f, 1.0f);

    [SerializeField] private CameraMode cameraMode = CameraMode.Isometric;
    [SerializeField] private float mouseSensitivity = 120f;
    [SerializeField] private float cameraSmoothing = 8f;
    [SerializeField] private Vector3 isometricCameraPosition = new Vector3(0f, 20f, -15f);
    [SerializeField] private Vector3 isometricCameraRotation = new Vector3(50f, 0f, 0f);
    [SerializeField] private Vector3 explorationCameraPosition = new Vector3(0f, 12f, -18f);
    [SerializeField] private Vector3 explorationCameraRotation = new Vector3(30f, 0f, 0f);

    public SessionConfig BaseConfig => baseConfig;

    public RewardFunction RewardFunction => rewardFunction;
    public float SessionDuration => baseConfig != null ? baseConfig.SessionDuration : sessionDuration;
    public int WorldSeed => baseConfig != null ? baseConfig.WorldSeed : worldSeed;
    public int TreeCount => baseConfig != null ? baseConfig.TreeCount : treeCount;
    public int FruitCount => baseConfig != null ? baseConfig.FruitCount : fruitCount;
    public float FruitRadius => baseConfig != null ? baseConfig.FruitRadius : fruitRadius;
    public float PlayerMoveSpeed => baseConfig != null ? baseConfig.PlayerMoveSpeed : playerMoveSpeed;
    public float FruitHarvestDuration => baseConfig != null ? baseConfig.FruitHarvestDuration : fruitHarvestDuration;
    public float HarvestDuration => baseConfig != null ? baseConfig.HarvestDuration : fruitHarvestDuration * Mathf.Max(1, fruitCount);
    public float RewardStd => baseConfig != null ? baseConfig.RewardStd : rewardStd;
    public Vector2 ShapeRange => baseConfig != null ? baseConfig.ShapeRange : shapeRange;
    public Vector2 CanopyWidthRange => baseConfig != null ? baseConfig.CanopyWidthRange : canopyWidthRange;
    public Vector2 CanopyHeightRange => baseConfig != null ? baseConfig.CanopyHeightRange : canopyHeightRange;
    public float HighlightRadiusPadding => baseConfig != null ? baseConfig.HighlightRadiusPadding : highlightRadiusPadding;
    public Color FruitColorLow => baseConfig != null ? baseConfig.FruitColorLow : fruitColorLow;
    public Color FruitColorHigh => baseConfig != null ? baseConfig.FruitColorHigh : fruitColorHigh;
    public float FruitColorPreservation => baseConfig != null ? baseConfig.FruitColorPreservation : fruitColorPreservation;
    public float TerrainNoiseFrequency => baseConfig != null ? baseConfig.TerrainNoiseFrequency : terrainNoiseFrequency;
    public int TerrainNoiseOctaves => baseConfig != null ? baseConfig.TerrainNoiseOctaves : terrainNoiseOctaves;
    public float TerrainMaxElevation => baseConfig != null ? baseConfig.TerrainMaxElevation : terrainMaxElevation;
    public int TerrainMeshResolution => baseConfig != null ? baseConfig.TerrainMeshResolution : terrainMeshResolution;
    public float WorldHalfExtent => baseConfig != null ? baseConfig.WorldHalfExtent : worldHalfExtent;
    public float BorderWallHeight => baseConfig != null ? baseConfig.BorderWallHeight : borderWallHeight;
    public Color BorderWallColor => baseConfig != null ? baseConfig.BorderWallColor : borderWallColor;
    public float SunArcHeight => baseConfig != null ? baseConfig.SunArcHeight : sunArcHeight;
    public float MinSunElevation => baseConfig != null ? baseConfig.MinSunElevation : minSunElevation;
    public float SunIntensityDawn => baseConfig != null ? baseConfig.SunIntensityDawn : sunIntensityDawn;
    public float SunIntensityNoon => baseConfig != null ? baseConfig.SunIntensityNoon : sunIntensityNoon;
    public Color SkyColorDawn => baseConfig != null ? baseConfig.SkyColorDawn : skyColorDawn;
    public Color SkyColorNoon => baseConfig != null ? baseConfig.SkyColorNoon : skyColorNoon;
    public CameraMode CameraMode => baseConfig != null ? baseConfig.CameraMode : cameraMode;
    public float MouseSensitivity => baseConfig != null ? baseConfig.MouseSensitivity : mouseSensitivity;
    public float CameraSmoothing => baseConfig != null ? baseConfig.CameraSmoothing : cameraSmoothing;
    public Vector3 IsometricCameraPosition => baseConfig != null ? baseConfig.IsometricCameraPosition : isometricCameraPosition;
    public Vector3 IsometricCameraRotation => baseConfig != null ? baseConfig.IsometricCameraRotation : isometricCameraRotation;
    public Vector3 ExplorationCameraPosition => baseConfig != null ? baseConfig.ExplorationCameraPosition : explorationCameraPosition;
    public Vector3 ExplorationCameraRotation => baseConfig != null ? baseConfig.ExplorationCameraRotation : explorationCameraRotation;

    public float EvaluateReward(TreeAttributes attributes)
    {
        return rewardFunction.Evaluate(attributes);
    }
}
