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

    // Terrain color range
    [SerializeField] private Color terrainArid = new Color(0.76f, 0.65f, 0.42f);
    [SerializeField] private Color terrainGrassland = new Color(0.44f, 0.56f, 0.24f);
    [SerializeField] private Color terrainSwampy = new Color(0.22f, 0.29f, 0.18f);

    // Terrain noise
    [SerializeField] private float terrainNoiseFrequency = 4f;
    [SerializeField] private int terrainNoiseOctaves = 1;

    [SerializeField] private float terrainMaxElevation = 3f;
    [SerializeField] private int terrainMeshResolution = 64;
    [SerializeField] private float worldHalfExtent = 50f;
    [SerializeField] private float colorContrast = 1.5f;

    // Sun arc
    [SerializeField] private float sunArcHeight = 60f;
    [SerializeField] private Vector3 sunRiseDirection = new Vector3(0f, 0f, 1f);

    // Sun color gradient (sunrise/set → midday)
    [SerializeField] private Color sunColorDawn = new Color(1.0f, 0.4f, 0.1f);
    [SerializeField] private Color sunColorNoon = new Color(1.0f, 0.95f, 0.8f);
    [SerializeField] private float sunIntensityDawn = 0.4f;
    [SerializeField] private float sunIntensityNoon = 1.2f;

    // Sky color gradient
    [SerializeField] private Color skyColorDawn = new Color(0.8f, 0.4f, 0.2f);
    [SerializeField] private Color skyColorNoon = new Color(0.3f, 0.6f, 1.0f);
    [SerializeField] private Color skyColorDusk = new Color(0.6f, 0.2f, 0.1f);

    // Ambient light gradient
    [SerializeField] private Color ambientDawn = new Color(0.15f, 0.1f, 0.08f);
    [SerializeField] private Color ambientNoon = new Color(0.2f, 0.2f, 0.25f);
    [SerializeField] private Color ambientDusk = new Color(0.12f, 0.08f, 0.06f);

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
    public Color TerrainArid => baseConfig != null ? baseConfig.TerrainArid : terrainArid;
    public Color TerrainGrassland => baseConfig != null ? baseConfig.TerrainGrassland : terrainGrassland;
    public Color TerrainSwampy => baseConfig != null ? baseConfig.TerrainSwampy : terrainSwampy;
    public float TerrainNoiseFrequency => baseConfig != null ? baseConfig.TerrainNoiseFrequency : terrainNoiseFrequency;
    public int TerrainNoiseOctaves => baseConfig != null ? baseConfig.TerrainNoiseOctaves : terrainNoiseOctaves;
    public float TerrainMaxElevation => baseConfig != null ? baseConfig.TerrainMaxElevation : terrainMaxElevation;
    public int TerrainMeshResolution => baseConfig != null ? baseConfig.TerrainMeshResolution : terrainMeshResolution;
    public float WorldHalfExtent => baseConfig != null ? baseConfig.WorldHalfExtent : worldHalfExtent;
    public float ColorContrast => baseConfig != null ? baseConfig.ColorContrast : colorContrast;
    public float SunArcHeight => baseConfig != null ? baseConfig.SunArcHeight : sunArcHeight;
    public Vector3 SunRiseDirection => baseConfig != null ? baseConfig.SunRiseDirection : sunRiseDirection;
    public Color SunColorDawn => baseConfig != null ? baseConfig.SunColorDawn : sunColorDawn;
    public Color SunColorNoon => baseConfig != null ? baseConfig.SunColorNoon : sunColorNoon;
    public float SunIntensityDawn => baseConfig != null ? baseConfig.SunIntensityDawn : sunIntensityDawn;
    public float SunIntensityNoon => baseConfig != null ? baseConfig.SunIntensityNoon : sunIntensityNoon;
    public Color SkyColorDawn => baseConfig != null ? baseConfig.SkyColorDawn : skyColorDawn;
    public Color SkyColorNoon => baseConfig != null ? baseConfig.SkyColorNoon : skyColorNoon;
    public Color SkyColorDusk => baseConfig != null ? baseConfig.SkyColorDusk : skyColorDusk;
    public Color AmbientDawn => baseConfig != null ? baseConfig.AmbientDawn : ambientDawn;
    public Color AmbientNoon => baseConfig != null ? baseConfig.AmbientNoon : ambientNoon;
    public Color AmbientDusk => baseConfig != null ? baseConfig.AmbientDusk : ambientDusk;

    public float EvaluateReward(TreeAttributes attributes)
    {
        return rewardFunction.Evaluate(attributes);
    }
}
