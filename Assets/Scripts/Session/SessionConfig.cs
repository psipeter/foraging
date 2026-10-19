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

    [Header("First-Person Camera")]
    [Tooltip("Eye height above the terrain surface (world units).")]
    [SerializeField] private float eyeHeight = 5.1f;
    [Tooltip("VERTICAL field of view in degrees (Unity's default axis). 75 vertical is about 105 horizontal at 16:9. Applies to the flat-screen camera only; a VR headset supplies its own projection.")]
    [SerializeField] private float cameraFieldOfView = 75f;
    [SerializeField] private float cameraNearClip = 0.3f;
    [Tooltip("Degrees turned per raw mouse count at sensitivity 1. Effective turn rate = this * lookSensitivity. Applied per frame with no deltaTime (mouse deltas are already displacements).")]
    [SerializeField] private float lookDegreesPerCount = 0.022f;
    [Tooltip("Player-facing sensitivity multiplier (the value a settings slider will eventually edit).")]
    [SerializeField] private float lookSensitivity = 2f;
    [SerializeField] private float lookPitchLimit = 85f;

    [Header("Trees")]
    [SerializeField] private int fruitCount = 10;
    [SerializeField] private float fruitRadius = 0.15f;
    [SerializeField] private Color fruitColorLow = new Color(0.2f, 0.4f, 1.0f);
    [SerializeField] private Color fruitColorHigh = new Color(1.0f, 0.5f, 0.1f);
    [SerializeField] private Vector2 shapeRange = new Vector2(0f, 1f);
    [SerializeField] private Vector2 canopyWidthRange = new Vector2(2.0f, 5.0f);
    [SerializeField] private Vector2 canopyHeightRange = new Vector2(1.2f, 2.8f);
    [Tooltip("Harvest/highlight range beyond the canopy edge = base + perRadius * canopyRadius (world units). Base 1.5 and per-radius 0 reproduces the old constant 1.5 padding.")]
    [SerializeField] private float harvestRangeGapBase = 0.8f;
    [SerializeField] private float harvestRangeGapPerRadius = 0.3f;
    [SerializeField] private float fruitColorPreservation = 0.5f;

    [Header("Terrain")]
    [SerializeField] private float terrainNoiseFrequency = 4f;
    [SerializeField] private int terrainNoiseOctaves = 1;
    [SerializeField] private float terrainMaxElevation = 3f;
    [SerializeField] private int terrainMeshResolution = 64;
    [SerializeField] private float worldHalfExtent = 50f;

    [Header("Lighting")]
    [Tooltip("Fraction (0-1) of the sunrise-to-sunset day already elapsed when the session starts. 0 = dawn; 0.5 = noon; the session still ends at sunset.")]
    [SerializeField] private float dayStartFraction = 0.3f;
    [Tooltip("Distance fog on or off. Distances and color are the scene's Lighting > Fog settings (linear). Off by default: fog limits how far bushes can be seen.")]
    [SerializeField] private bool fogEnabled = false;
    [SerializeField] private float sunArcHeight = 60f;
    [SerializeField] private float minSunElevation = 5f;
    [SerializeField] private float sunIntensityDawn = 0.4f;
    [SerializeField] private float sunIntensityNoon = 1.2f;
    [SerializeField] private Color skyColorDawn = new Color(0.8f, 0.4f, 0.2f);
    [SerializeField] private Color skyColorNoon = new Color(0.3f, 0.6f, 1.0f);

    [Header("Mountains (map border)")]
    [Tooltip("Width of the unclimbable mountain band at the map edge (world units). 0 disables mountains.")]
    [SerializeField] private float mountainBandWidth = 60f;
    [Tooltip("Random +/- variation of the band's inner boundary, so the foot of the mountains is irregular.")]
    [SerializeField] private float mountainBoundaryJitter = 15f;
    [Tooltip("Mountain height above the valley at the map edge (before ridge-noise scaling, which keeps the crest between 55% and 100% of this). Must put the crest well above eye level so the mesh edge is never visible.")]
    [SerializeField] private float mountainHeight = 70f;
    [Tooltip("Size (world units) of the largest ridge features. Varies with worldSeed, so each seed has its own skyline.")]
    [SerializeField] private float mountainNoiseScale = 60f;
    [Tooltip("Movement is blocked once the mountain ramp (0 at the foot, 1 at the edge) exceeds this.")]
    [SerializeField] private float mountainBlockThreshold = 0.15f;
    [Tooltip("Trees are kept this far (world units) back from the mountain foot.")]
    [SerializeField] private float treeEdgeMargin = 8f;
    [Tooltip("Snow begins at terrainMaxElevation + this fraction of mountainHeight.")]
    [SerializeField] private float snowLineFraction = 0.45f;
    [Tooltip("How much of the normal distance fog applies to mountains (0 = none, 1 = same as the valley). Below 1 keeps the skyline visible past the fog distance; trees are unaffected.")]
    [SerializeField] [Range(0f, 1f)] private float mountainFogStrength = 0.3f;
    [SerializeField] private Color mountainRockColor = new Color(0.42f, 0.40f, 0.38f);
    [SerializeField] private Color mountainSnowColor = new Color(0.93f, 0.95f, 0.98f);

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
    public float HarvestRangeGapBase => harvestRangeGapBase;
    public float HarvestRangeGapPerRadius => harvestRangeGapPerRadius;
    public Color FruitColorLow => fruitColorLow;
    public Color FruitColorHigh => fruitColorHigh;
    public float FruitColorPreservation => fruitColorPreservation;
    public float TerrainNoiseFrequency => terrainNoiseFrequency;
    public int TerrainNoiseOctaves => terrainNoiseOctaves;
    public float TerrainMaxElevation => terrainMaxElevation;
    public int TerrainMeshResolution => terrainMeshResolution;
    public float WorldHalfExtent => worldHalfExtent;
    public float MountainBandWidth => mountainBandWidth;
    public float MountainBoundaryJitter => mountainBoundaryJitter;
    public float MountainHeight => mountainHeight;
    public float MountainNoiseScale => mountainNoiseScale;
    public float MountainBlockThreshold => mountainBlockThreshold;
    public float TreeEdgeMargin => treeEdgeMargin;
    public float SnowLineFraction => snowLineFraction;
    public float MountainFogStrength => mountainFogStrength;
    public Color MountainRockColor => mountainRockColor;
    public Color MountainSnowColor => mountainSnowColor;
    public bool FogEnabled => fogEnabled;
    public float DayStartFraction => dayStartFraction;
    public float SunArcHeight => sunArcHeight;
    public float MinSunElevation => minSunElevation;
    public float SunIntensityDawn => sunIntensityDawn;
    public float SunIntensityNoon => sunIntensityNoon;
    public Color SkyColorDawn => skyColorDawn;
    public Color SkyColorNoon => skyColorNoon;
    public float EyeHeight => eyeHeight;
    public float CameraFieldOfView => cameraFieldOfView;
    public float CameraNearClip => cameraNearClip;
    public float LookDegreesPerCount => lookDegreesPerCount;
    public float LookSensitivity => lookSensitivity;
    public float LookPitchLimit => lookPitchLimit;

    public float HarvestRangeGap(float canopyRadius)
    {
        return harvestRangeGapBase + harvestRangeGapPerRadius * canopyRadius;
    }

    public float EvaluateReward(TreeAttributes attributes)
    {
        return rewardFunction.Evaluate(attributes);
    }
}
