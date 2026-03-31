using UnityEngine;

[CreateAssetMenu(
    fileName = "SessionConfig",
    menuName = "Foraging/Session Config")]
public class SessionConfig : ScriptableObject
{
    [SerializeField] private RewardFunction rewardFunction = new RewardFunction();
    [SerializeField] private float sessionDuration = 120f;
    [SerializeField] private int worldSeed;
    [SerializeField] private int treeCount = 50;
    [SerializeField] private int fruitCount = 12;
    [SerializeField] private float fruitRadius = 0.15f;
    [SerializeField] private float playerMoveSpeed = 5f;
    [SerializeField] private float harvestDuration = 2f;

    // Shape range
    [SerializeField] private Vector2 shapeRange = new Vector2(0f, 1f);
    // Maps attribute 0..1 to canopy scale range
    [SerializeField] private Vector2 canopyWidthRange = new Vector2(1.0f, 2.5f);
    [SerializeField] private Vector2 canopyHeightRange = new Vector2(0.6f, 1.4f);

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

    // Sky color gradient
    [SerializeField] private Color skyColorDawn = new Color(0.8f, 0.4f, 0.2f);
    [SerializeField] private Color skyColorNoon = new Color(0.3f, 0.6f, 1.0f);
    [SerializeField] private Color skyColorDusk = new Color(0.6f, 0.2f, 0.1f);

    // Ambient light gradient
    [SerializeField] private Color ambientDawn = new Color(0.15f, 0.1f, 0.08f);
    [SerializeField] private Color ambientNoon = new Color(0.2f, 0.2f, 0.25f);
    [SerializeField] private Color ambientDusk = new Color(0.12f, 0.08f, 0.06f);

    public RewardFunction RewardFunction => rewardFunction;
    public float SessionDuration => sessionDuration;
    public int WorldSeed => worldSeed;
    public int TreeCount => treeCount;
    public int FruitCount => fruitCount;
    public float FruitRadius => fruitRadius;
    public float PlayerMoveSpeed => playerMoveSpeed;
    public float HarvestDuration => harvestDuration;
    public Vector2 ShapeRange => shapeRange;
    public Vector2 CanopyWidthRange => canopyWidthRange;
    public Vector2 CanopyHeightRange => canopyHeightRange;
    public Color FruitColorLow => fruitColorLow;
    public Color FruitColorHigh => fruitColorHigh;
    public Color TerrainArid => terrainArid;
    public Color TerrainGrassland => terrainGrassland;
    public Color TerrainSwampy => terrainSwampy;
    public float TerrainNoiseFrequency => terrainNoiseFrequency;
    public int TerrainNoiseOctaves => terrainNoiseOctaves;
    public float TerrainMaxElevation => terrainMaxElevation;
    public int TerrainMeshResolution => terrainMeshResolution;
    public float WorldHalfExtent => worldHalfExtent;
    public float ColorContrast => colorContrast;
    public float SunArcHeight => sunArcHeight;
    public Vector3 SunRiseDirection => sunRiseDirection;
    public Color SunColorDawn => sunColorDawn;
    public Color SunColorNoon => sunColorNoon;
    public Color SkyColorDawn => skyColorDawn;
    public Color SkyColorNoon => skyColorNoon;
    public Color SkyColorDusk => skyColorDusk;
    public Color AmbientDawn => ambientDawn;
    public Color AmbientNoon => ambientNoon;
    public Color AmbientDusk => ambientDusk;

    public float EvaluateReward(TreeAttributes attributes)
    {
        return rewardFunction.Evaluate(attributes);
    }
}
