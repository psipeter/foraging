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
    [SerializeField] private Color terrainArid = new Color(0.85f, 0.72f, 0.35f);
    [SerializeField] private Color terrainGrassland = new Color(0.35f, 0.55f, 0.15f);
    [SerializeField] private Color terrainSwampy = new Color(0.1f, 0.2f, 0.08f);

    // Terrain noise
    [SerializeField] private float terrainNoiseFrequency = 4f;
    [SerializeField] private int terrainNoiseOctaves = 1;

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

    public float EvaluateReward(TreeAttributes attributes)
    {
        return rewardFunction.Evaluate(attributes);
    }
}
