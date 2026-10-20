using UnityEngine;

[CreateAssetMenu(
    fileName = "SessionConfig",
    menuName = "Foraging/Session Config")]
public class SessionConfig : ScriptableObject
{
    [Header("Session")]
    [SerializeField] private float sessionDuration = 120f;
    [SerializeField] private int worldSeed;
    [Tooltip("Practice sessions are not part of the analyzed experiment: the end screen says 'Practice complete' and they are not counted in 'Session x/N'.")]
    [SerializeField] private bool isPractice;

    [Header("Instructions")]
    [Tooltip("File in StreamingAssets shown before this session. '{session}' and '{total}' are replaced by this session's number and the count of non-practice sessions.")]
    [SerializeField] private string instructionsFile = "instructions.txt";
    [Tooltip("Optional text kept on screen during the session (empty = none).")]
    [SerializeField] private string controlsReminder = "";
    [Tooltip("Optional message shown once, after the first harvest of the session ('{points}' = points earned in that harvest). The game pauses until Enter. Empty = none.")]
    [TextArea(2, 5)]
    [SerializeField] private string firstHarvestMessage = "";
    [Tooltip("Opacity (0-1) of the controls reminder.")]
    [SerializeField] [Range(0f, 1f)] private float controlsReminderOpacity = 0.35f;

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

    [Header("Harvest")]
    [Tooltip("Gradual glow starts this far (horizontal, from the canopy edge) and reaches full strength at the harvest range.")]
    [SerializeField] private float highlightRangeGap = 20f;
    [Tooltip("A bush within this bearing (degrees, yaw only, after subtracting its angular radius) of straight ahead glows fully; the glow fades to nothing at the fade angle.")]
    [SerializeField] private float highlightFullAngle = 25f;
    [SerializeField] private float highlightFadeAngle = 45f;
    [Tooltip("Harvest is available, and keeps progressing, only while the bush is within this bearing (degrees). Looking further away pauses the harvest.")]
    [SerializeField] private float harvestMaxAngle = 35f;
    [Tooltip("0 = off. 1 = while harvesting, mouse yaw slows to zero as you turn away from the bush between the full and fade angles (turning back is unaffected). Flat-screen only; changes effective sensitivity, so keep it off unless studying it.")]
    [Range(0f, 1f)]
    [SerializeField] private float harvestLookResistance = 0f;
    [SerializeField] private Color rimColor = new Color(1f, 0.96f, 0.82f);
    [Tooltip("Rim color on the selected (harvestable) bush, blended in from rimColor. A small shift from rimColor; also the harvest ring's color. Keep it pale and near-neutral so it does not read as a fruit hue.")]
    [SerializeField] private Color rimSelectedColor = new Color(1f, 0.9f, 0.6f);
    [Tooltip("Rim light, approach: wide soft glow. Intensity at glow level 1 and the fresnel exponent (higher = thinner).")]
    [SerializeField] private float rimApproachIntensity = 1.5f;
    [SerializeField] private float rimApproachPower = 2.5f;
    [Tooltip("Rim light, selected bush only: thin crisp edge line, added on top of the soft glow.")]
    [SerializeField] private float rimSelectedIntensity = 2.5f;
    [SerializeField] private float rimSelectedPower = 8f;
    [Tooltip("Apparent size of the harvest progress ring above a bush, in degrees of view (constant regardless of distance).")]
    [SerializeField] private float harvestRingSizeDeg = 7f;
    [Tooltip("An exhausted bush stays as a landmark and obstacle, easing into its 'spent' look over this long.")]
    [SerializeField] private float spentTransitionDuration = 0.6f;
    [Tooltip("Spent bush: uniform scale multiplier (uniform, so canopy aspect ratio - the shape channel - is preserved). The blocking collider shrinks to match.")]
    [SerializeField] private float spentScale = 0.7f;
    [Tooltip("Spent bush: color multiplied onto the canopy. A drab warm gray reads as dormant; keep it subtle.")]
    [SerializeField] private Color spentTint = new Color(0.55f, 0.5f, 0.42f);
    [SerializeField] private float fruitPopDuration = 0.15f;
    [SerializeField] private bool showHarvestHint = true;

    [Header("Feedback (HUD and audio)")]
    [Tooltip("Per-fruit reward at which popup size/brightness and sound pitch reach their maximum (about the top of the per-fruit reward range).")]
    [SerializeField] private float rewardFeedbackMax = 6f;
    [Tooltip("How strongly the +X popup's size and brightness follow the reward: 0 = every fruit gets an identical popup, 1 = full scaling. The number itself is always shown.")]
    [SerializeField] [Range(0f, 1f)] private float rewardSizeScaling = 1f;
    [Tooltip("+X popup size multiplier (relative to the prefab) at zero reward.")]
    [SerializeField] private float popupScale = 1.7f;
    [Tooltip("Extra popup size multiplier at rewardFeedbackMax (times rewardSizeScaling).")]
    [SerializeField] private float popupExtraScale = 0.9f;
    [Tooltip("Popup and score-flash color. Keep it pale and near-neutral: fruit hue runs blue to orange, and red/green are not used.")]
    [SerializeField] private Color popupColor = new Color(1f, 0.95f, 0.78f);
    [Tooltip("Pitch range of the fruit-pick sound, in semitones from zero reward to rewardFeedbackMax. 0 = the same pitch for every reward.")]
    [SerializeField] private float pitchSemitoneRange = 7f;
    [Tooltip("Master volume of feedback sounds (0-1).")]
    [SerializeField] [Range(0f, 1f)] private float sfxVolume = 0.5f;
    [Tooltip("Small spheres in the fruit's color that burst out when a fruit is picked. 0 disables.")]
    [SerializeField] private int burstCount = 7;
    [SerializeField] private float burstSpeed = 3.5f;
    [SerializeField] private float burstDuration = 0.35f;
    [Tooltip("Burst particle diameter (world units).")]
    [SerializeField] private float burstSize = 0.12f;

    [Header("Trees")]
    [Tooltip("Bush placement: a hexagonal lattice with this nearest-neighbour distance (world units) sets bush density (about 2/(sqrt(3)*spacing^2) per square unit); the bush count follows from the valley area. Walk time between neighbouring bushes is roughly spacing / playerMoveSpeed.")]
    [SerializeField] private float treeSpacing = 23f;
    [Tooltip("Random displacement of each bush from its lattice site, as a fraction of treeSpacing (0 = strict lattice). Each bush moves within a disc of radius jitter * spacing / 2, so any two bushes stay at least spacing * (1 - jitter) apart. ~0.5 looks natural with no clusters; above ~0.7 near-pairs begin to form.")]
    [SerializeField] [Range(0f, 1f)] private float placementJitter = 0.5f;
    [Tooltip("No bushes within this distance (world units) of the player's start (the map center). The lattice is anchored so a site sits at the start, so the clearing removes whole hex rings: the first ring (6 sites at ~spacing, up to spacing * (1 + jitter / 2)) needs > 29 at spacing 23 / jitter 0.5; the second ring (at ~1.7x spacing, at least 1.73 * spacing - jitter * spacing / 2) must stay outside it. 12 clears only the center site, 31 clears the first ring too.")]
    [SerializeField] private float startClearingRadius = 31f;
    [SerializeField] private int fruitCount = 10;
    [SerializeField] private float fruitRadius = 0.15f;
    [SerializeField] private Color fruitColorLow = new Color(0.2f, 0.4f, 1.0f);
    [SerializeField] private Color fruitColorHigh = new Color(1.0f, 0.5f, 0.1f);
    [SerializeField] private Vector2 shapeRange = new Vector2(0f, 1f);
    [SerializeField] private Vector2 canopyWidthRange = new Vector2(2.0f, 5.0f);
    [SerializeField] private Vector2 canopyHeightRange = new Vector2(1.2f, 2.8f);
    [Tooltip("Harvest becomes available when the player is within gap(R) = base + perRadius * canopyRadius of the canopy EDGE (horizontal distance). ~7 shows the whole bush at the 5.1 eye height / 75 deg vertical FOV (the near foot is visible from 5.1 / tan(37.5 deg) = 6.6).")]
    [SerializeField] private float harvestRangeGapBase = 7f;
    [SerializeField] private float harvestRangeGapPerRadius = 0f;
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
    public bool IsPractice => isPractice;
    public string InstructionsFile => instructionsFile;
    public string ControlsReminder => controlsReminder;
    public string FirstHarvestMessage => firstHarvestMessage;
    public float ControlsReminderOpacity => controlsReminderOpacity;
    public float RewardFeedbackMax => rewardFeedbackMax;
    public float RewardSizeScaling => rewardSizeScaling;
    public float PopupScale => popupScale;
    public float PopupExtraScale => popupExtraScale;
    public Color PopupColor => popupColor;
    public float PitchSemitoneRange => pitchSemitoneRange;
    public float SfxVolume => sfxVolume;
    public int BurstCount => burstCount;
    public float BurstSpeed => burstSpeed;
    public float BurstDuration => burstDuration;
    public float BurstSize => burstSize;
    public float TreeSpacing => treeSpacing;
    public float PlacementJitter => placementJitter;
    public float StartClearingRadius => startClearingRadius;
    public int FruitCount => fruitCount;
    public float FruitRadius => fruitRadius;
    public float PlayerMoveSpeed => playerMoveSpeed;
    public float FruitHarvestDuration => fruitHarvestDuration;
    public float RewardStd => rewardStd;
    public Vector2 ShapeRange => shapeRange;
    public Vector2 CanopyWidthRange => canopyWidthRange;
    public Vector2 CanopyHeightRange => canopyHeightRange;
    public float HighlightRangeGap => highlightRangeGap;
    public float HighlightFullAngle => highlightFullAngle;
    public float HighlightFadeAngle => highlightFadeAngle;
    public float HarvestMaxAngle => harvestMaxAngle;
    public float HarvestLookResistance => harvestLookResistance;
    public Color RimColor => rimColor;
    public Color RimSelectedColor => rimSelectedColor;
    public float HarvestRingSizeDeg => harvestRingSizeDeg;
    public float SpentTransitionDuration => spentTransitionDuration;
    public float SpentScale => spentScale;
    public Color SpentTint => spentTint;
    public float RimApproachIntensity => rimApproachIntensity;
    public float RimApproachPower => rimApproachPower;
    public float RimSelectedIntensity => rimSelectedIntensity;
    public float RimSelectedPower => rimSelectedPower;
    public float FruitPopDuration => fruitPopDuration;
    public bool ShowHarvestHint => showHarvestHint;
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
