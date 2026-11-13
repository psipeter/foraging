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

    [Tooltip("Hold the sun still at solar noon.")]
    [SerializeField] private bool freezeSun;

    [Header("Ranking (a set of bushes played in place after patch switches, on the terrain the player stands on; the set file is read from scripts/ranking.py pool)")]
    [Tooltip("A ranking is due after this many patch switches (a settled crossing into another tile); 0 = no rankings.")]
    [SerializeField] private int rankingEvery = 0;
    [Tooltip("Ranking sets played in one ranking.")]
    [SerializeField] private int rankingSets = 1;
    [Tooltip("Seconds of the countdown of one ranking set (the main clock is frozen meanwhile).")]
    [SerializeField] private float rankingSeconds = 20f;
    [Tooltip("The fewest seconds of foraging between the end of one ranking and a patch switch that counts toward the next (a switch inside this time is ignored).")]
    [SerializeField] private float rankingCooldown = 10f;
    [Tooltip("A crossing into another tile counts as a patch switch once the player is this many units past the edge between the tiles (0 = at the edge itself, so the ranking starts as early as possible and the arc is farthest from the next cluster).")]
    [SerializeField] private float rankingSettleDepth = 0f;
    [Tooltip("Sets in the pool file (used in order, one after another). Read by scripts/ranking.py pool: regenerate the file after changing it.")]
    [SerializeField] private int rankingPoolSets = 12;
    [Tooltip("Seconds the ranking bushes take to grow and to shrink away again.")]
    [SerializeField] private float rankingFadeSeconds = 0.4f;
    [Tooltip("Seconds the world's bushes take to fade to grayscale when a ranking starts, and back to colour when it ends.")]
    [SerializeField] private float rankingGraySeconds = 0.25f;
    [Tooltip("Seconds per fruit while harvesting a ranking bush (a whole bush takes this times fruitCount): quick.")]
    [SerializeField] private float rankingFruitSeconds = 0.05f;
    [Tooltip("No ranking starts when this many seconds or fewer of the session are left.")]
    [SerializeField] private float rankingLastSeconds = 10f;
    [Tooltip("A patch switch counts toward a ranking only once the participant has harvested (taken a fruit from) at least this many different bushes in the session, so no ranking comes before they have seen what a bush pays.")]
    [SerializeField] private int rankingMinBushes = 1;
    [Tooltip("The line shown at the top of the screen during a ranking.")]
    [SerializeField] private string rankingText = "Rank these bushes: harvest them from most to least points";
    [Tooltip("Bushes per set. Read by scripts/ranking.py.")]
    [SerializeField] private int rankingSetSize = 5;
    [Tooltip("Degrees from the leftmost to the rightmost bush centre (the arc is symmetric about the heading). The outermost centres must stay inside the view of a 4:3 window, so at least half of each bush is on screen without turning: scripts/ranking.py checks. Read by scripts/ranking.py.")]
    [SerializeField] private float rankingArcSpan = 84f;
    [Tooltip("Distance from the player to the nearest point of each canopy (world units); the same for every bush. Read by scripts/ranking.py.")]
    [SerializeField] private float rankingDistance = 16f;
    [Tooltip("The smallest true reward difference (points per fruit) between two bushes of a set; pairs closer than this are ties and score nothing. Read by scripts/ranking.py.")]
    [SerializeField] private float rankingTieGap = 0.25f;
    [Tooltip("The halo of the bush being aimed at is a copy of its canopy this many times larger (the main task uses 1.03), so it shows at the ranking's distance.")]
    [SerializeField] private float rankingRimScale = 1.15f;
    [Tooltip("How many times brighter the rim of the bush being aimed at is than in the main task.")]
    [SerializeField] private float rankingRimBoost = 3f;
    [Tooltip("How far above the usual spot the progress ring and the rank number sit, in ring diameters, so they clear the canopy and its halo at the ranking's distance.")]
    [SerializeField] private float rankingMarkerLift = 0.75f;
    [Tooltip("Size of the rank number, as a multiple of the number's size in the main task's units (the digits are about this times 1.2 degrees tall).")]
    [SerializeField] private float rankingRankScale = 3f;
    [Tooltip("Hidden bonus points per correctly ordered pair (a set of k bushes implies k(k-1)/2 pairs; pairs whose true values are tied are not counted, and a pair with an unranked bush is never correct), shown only on the final screen. Practice sessions award none. Provisional: scoring is decided at analysis time.")]
    [SerializeField] private float rankingBonusPerPair = 4f;
    [Tooltip("Degrees beyond a canopy's edge at which the crosshair still selects it in a ranking when crosshairRadius is 0 (0 = the crosshair must be inside the canopy).")]
    [SerializeField] private float rankingAimTolerance = 1.5f;

    [Header("Instructions")]
    [Tooltip("File in StreamingAssets shown before this session. '{part}' and '{total}' are replaced by this session's number and the count of sessions.")]
    [SerializeField] private string instructionsFile = "instructions.txt";
    [Tooltip("Optional file in StreamingAssets of popup hints that appear as the participant acts (the first line of a block is its trigger: see UI/TutorialHints.cs). Empty = no hints.")]
    [SerializeField] private string hintsFile = "";
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

    [Header("Display")]
    [Tooltip("Frame rate cap (vsync is turned off so the cap applies). 120 matches common VR headset refresh rates and bounds the size of the per-frame trajectory log.")]
    [SerializeField] private int targetFrameRate = 120;

    [Header("Data upload")]
    [Tooltip("When online, seconds the server may leave recorded data unacknowledged before the game pauses behind a 'saving' message until it has been stored. Keep it above the server's normal response time (cold starts take about a second).")]
    [SerializeField] private float uploadGraceSeconds = 4f;

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
    [Tooltip("The crosshair's hidden hit circle (degrees of view angle around the centre of the screen): a bush can be harvested only while this circle touches its canopy (the canopy's real shape, above and below as well as to the sides), together with the harvest range. Used by main sessions and rankings alike. 0 = the old rule (a 35 degree cone of yaw, harvestMaxAngle; rankingAimTolerance). Read by scripts/replay.py from the log.")]
    [SerializeField] private float crosshairRadius = 7f;
    [Tooltip("A harvest in progress (main sessions) keeps going while the circle, grown by this factor, still touches the bush, so hand tremor at the edge does not pause it. Starting a harvest uses the plain circle.")]
    [SerializeField] private float crosshairReleaseScale = 2f;
    [Tooltip("Opacity of the thin grey crosshair drawn at the centre of the screen, always (0 = hidden, 1 = solid). It brightens on a bush that can be harvested.")]
    [Range(0f, 1f)]
    [SerializeField] private float crosshairAlpha = 0.25f;
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

    [Header("Music")]
    [Tooltip("Volume (0-1) of the menu and score-screen music (UI/Music.cs). 0 disables. It never plays during a session.")]
    [SerializeField] [Range(0f, 1f)] private float musicVolume = 0.15f;

    [Header("Ambient Audio")]
    [Tooltip("Volume (0-1) of footsteps while walking. 0 disables. Ambient audio is purely passive: it never depends on bush attributes, rewards, terrain or time of day.")]
    [SerializeField] [Range(0f, 1f)] private float footstepVolume = 0.06f;
    [Tooltip("Distance walked (world units) between footsteps. At the default speed 7.5 this is about 2 steps per second.")]
    [SerializeField] private float footstepStride = 3.6f;
    [Tooltip("Volume (0-1) of the quiet constant background bed (cicadas). 0 disables.")]
    [SerializeField] [Range(0f, 1f)] private float bedVolume = 0.0165f;
    [Tooltip("Volume (0-1) of occasional birdsong. 0 disables.")]
    [SerializeField] [Range(0f, 1f)] private float birdVolume = 0.03f;
    [Tooltip("Shortest and longest gap (seconds) between bird calls; each gap is drawn at random.")]
    [SerializeField] private float birdIntervalMin = 5f;
    [SerializeField] private float birdIntervalMax = 14f;

    [Header("Trees")]
    [SerializeField] private int fruitCount = 10;
    [SerializeField] private float fruitRadius = 0.15f;
    [Tooltip("Fruit color along the color attribute (0..1): evenly spaced stops, linearly interpolated. Generated by scripts/fruit_ramp.py (viridis re-spaced to equal perceptual steps); do not hand-edit. See docs/DECISIONS.md, \"Fruit colour ramp\". Fewer than two stops fall back to a blue to orange pair.")]
    [SerializeField] private Color[] fruitColorRamp = new Color[0];
    [SerializeField] private Vector2 shapeRange = new Vector2(0f, 1f);
    [SerializeField] private Vector2 canopyWidthRange = new Vector2(2.0f, 5.0f);
    [SerializeField] private Vector2 canopyHeightRange = new Vector2(1.2f, 2.8f);
    [Tooltip("Which world-generator stage lays out the bushes (scripts/world.py LAYOUTS). The only layout is \"tiles\". Read by scripts/world.py: regenerate the world after changing it.")]
    [SerializeField] private string layout = "";
    [Tooltip("Which stage gives each bush its attributes (scripts/world.py ASSIGNMENTS). The only assignment is \"tiles\".")]
    [SerializeField] private string assignment = "";
    [Tooltip("Which stage turns a bush's attributes into its reward (scripts/world.py REWARDS). Empty = the sum of the reward function's terms.")]
    [SerializeField] private string rewardStage = "";
    [Tooltip("What the experiment's design says about this instance (scripts/design/<code>.py): the instance id, its cell parameters and its hint arm, as JSON. Written by the experiment builder, logged with the rest of this config, read by no game code.")]
    [SerializeField] private string designJson = "";
    [Tooltip("False: every bush has the value shapeWhenFixed, so all canopies are identical; give the shape component weight 0. Read by scripts/world.py: regenerate the world after changing it.")]
    [SerializeField] private bool shapeVaries = true;
    [Tooltip("The shape value of every bush when shapeVaries is off (0..1; the canopy size then follows the shape axis). Read by scripts/world.py.")]
    [SerializeField] private float shapeWhenFixed = 0.5f;
    [Tooltip("False: every bush has the value colorWhenFixed, so all fruit have one color; give the color component weight 0. Read by scripts/world.py: regenerate the world after changing it.")]
    [SerializeField] private bool colorVaries = true;
    [Tooltip("The color value of every bush when colorVaries is off (0..1). Read by scripts/world.py.")]
    [SerializeField] private float colorWhenFixed = 0.5f;
    [Tooltip("False: the valley has one moisture value (moistureWhenFixed), so the ground is one colour and flat (elevation follows moisture), and moisture cannot pay. Read by scripts/world.py: regenerate the world after changing it.")]
    [SerializeField] private bool moistureVaries = true;
    [Tooltip("The moisture of the whole valley when moistureVaries is off (0..1).")]
    [SerializeField] private float moistureWhenFixed = 0.5f;
    [Tooltip("Declare moisture a feature of the task even though it pays nothing: it counts as a feature of the task. Moisture that pays is always counted; with this off and a zero weight it is decoration.")]
    [SerializeField] private bool moistureIsFeature = false;
    [Tooltip("A per-bush point value drawn uniformly from (min, max) and added to the reward function, independent of every attribute: the practice session's random reward. (0, 0) = off. Pre-drawn in the world file by scripts/world.py.")]
    [SerializeField] private Vector2 randomBushValueRange = Vector2.zero;
    [Tooltip("Harvest becomes available when the player is within gap(R) = base + perRadius * canopyRadius of the canopy EDGE (horizontal distance). ~7 shows the whole bush at the 5.1 eye height / 75 deg vertical FOV (the near foot is visible from 5.1 / tan(37.5 deg) = 6.6).")]
    [SerializeField] private float harvestRangeGapBase = 7f;
    [SerializeField] private float harvestRangeGapPerRadius = 0f;
    [SerializeField] private float fruitColorPreservation = 0.5f;
    [Tooltip("Brightness of a fruit's shaded side as a fraction of its lit side (0.3 = dark far side, 1 = flat). Higher keeps fruit colours near the palette's while the sphere shading stays readable.")]
    [SerializeField] [Range(0f, 1f)] private float fruitShadingFloor = 0.65f;
    [Tooltip("Multiplier on the fruit's final color (1 = as shaded). Above 1 brightens fruit toward the palette's brightness; tone mapping rolls the brightest values off.")]
    [SerializeField] private float fruitBrightness = 1.2f;
    [Tooltip("How much of the sun's post-exposure (it darkens the whole scene as the sun lowers) is undone on fruit, so a fruit keeps its brightness through the session: 1 = fully, 0 = not at all.")]
    [SerializeField] [Range(0f, 1f)] private float fruitExposureCompensation = 1f;
    [Tooltip("Canopy colour variation, purely decorative and independent of every attribute and reward: each bush draws one position u uniformly in [0, 1] from its own seed and multiplies the canopy material's colour by a tint running from this dark end (u = 0) through no change (u = 0.5) to the light end (u = 1). Same bush, same canopy in every run. Set both to white to switch it off.")]
    [SerializeField] private Color canopyTintDark = new Color(0.55f, 0.70f, 0.65f);
    [SerializeField] [ColorUsage(false, true)] private Color canopyTintLight = new Color(1.30f, 1.20f, 1.30f);

    [Header("Tiles (layout \"tiles\": hexagonal plateaus, each with a cluster of bushes in the middle; read by scripts/world.py and scripts/tiles.py: regenerate the world after changing any of them)")]
    [Tooltip("Circumradius of a hexagonal tile (world units; the distance between neighbouring tile centres is sqrt(3) times this). The walk from a tile's edge to its cluster is about this times 0.87 minus the cluster radius.")]
    [SerializeField] private float tileRadius = 70f;
    [Tooltip("Width (world units) of the ramp between neighbouring tiles' plateaus. The plateau is flat beyond half of it from the edge.")]
    [SerializeField] private float tileRampWidth = 14f;
    [Tooltip("Number of distinct ground levels (moisture values, evenly spaced 0 to 1: colour and height) the tiles take; neighbouring tiles differ whenever the number allows. 0 = every tile a continuous random level. The level never depends on the tile's value.")]
    [SerializeField] private int tileMoistureLevels = 4;
    [Tooltip("Bushes in each tile's cluster (the same in every tile).")]
    [SerializeField] private int tileBushes = 9;
    [Tooltip("Radius (world units) of the disc around a tile's centre that holds its bushes.")]
    [SerializeField] private float tileClusterRadius = 22f;
    [Tooltip("Smallest distance (world units) between two bushes of a cluster.")]
    [SerializeField] private float tileClusterSpacing = 12f;
    [Tooltip("Spread (standard deviation, feature units 0-1) of the bushes' shape and colour around their tile's centre in the feature plane: how alike the bushes of a tile are.")]
    [SerializeField] private float tileSpread = 0.12f;
    [Tooltip("How the bushes lie inside a tile (scripts/tiles.py ARRANGEMENTS). Empty = random.")]
    [SerializeField] private string tileArrangement = "";
    [Tooltip("The BETWEEN layer: how the tiles' centres in the feature plane, and so the tiles' values, are dealt (scripts/tiles.py BETWEEN_MODES: none, random, graded, bimodal). Empty = none (no difference between tiles).")]
    [SerializeField] private string tileValueMode = "";
    [Tooltip("The WITHIN layer: how a tile's bushes get their features from the tile's centre and their place in the cluster (scripts/tiles.py WITHIN_MODES: pool, scatter, gradient). Empty = pool (a stratified draw of the whole plane: much variation inside every tile).")]
    [SerializeField] private string tileWithinMode = "";
    [Tooltip("bimodal only: the share of the tiles that are good (centres where the reward is at least 70% of the best); the rest are poor.")]
    [SerializeField] [Range(0f, 1f)] private float tileGoodFraction = 0.25f;
    [Tooltip("graded and bimodal: passes of averaging with the neighbouring tiles applied to the random field that decides which tiles are richer, so neighbouring tiles have similar values (0 = independent).")]
    [SerializeField] private int tileSmoothness = 0;
    [Tooltip("gradient only: how far (feature units) the features move from one side of a cluster to the other.")]
    [SerializeField] private float tileGradient = 0.3f;
    [Tooltip("gradient only: the direction in the (shape, colour) plane in degrees; -1 = a random one per tile.")]
    [SerializeField] private float tileGradientAngle = -1f;
    [Tooltip("A tile together with its six neighbours must have bushes in at least this share of the feature plane (4 x 4 cells), for every tile with all six; the assignment is redrawn until it holds. 0 = off.")]
    [SerializeField] [Range(0f, 1f)] private float tileCoverageMin = 0f;
    [Tooltip("The tiles around the start must differ in mean reward by at least this share of the reward's range over the feature plane; the assignment is redrawn until it holds. 0 = off.")]
    [SerializeField] [Range(0f, 1f)] private float tileStartSpreadMin = 0f;

    [Header("Terrain")]
    [SerializeField] private float terrainMaxElevation = 3f;
    [SerializeField] private int terrainMeshResolution = 64;
    [SerializeField] private float worldHalfExtent = 50f;

    [Header("Lighting")]
    [Tooltip("Elevation (degrees above the horizon) of the sun when the session starts, on the morning side of noon (about 30 is mid-morning). The session then plays the sun's path from there to sunEndElevation on the afternoon side.")]
    [SerializeField] private float sunStartElevation = 30f;
    [Tooltip("Latitude (degrees) of the simulated sun. With the declination it sets the path: noon elevation = 90 - |latitude - declination|, and the sun rises and sets toward the east and west (more northerly in summer).")]
    [SerializeField] private float sunLatitude = 40f;
    [Tooltip("Solar declination (degrees; about +23 midsummer, 0 equinox, -23 midwinter): the time of year.")]
    [SerializeField] private float sunDeclination = 12f;
    [Tooltip("Elevation (degrees above the horizon) the sun has reached when the session ends. Seen from the valley the mountain skyline is about 3-22 degrees (median 9), so about 10 puts the sun just above the mountains at dusk; lower sinks it behind them.")]
    [SerializeField] private float sunEndElevation = 10f;
    [Tooltip("Rotates the whole sun path about the vertical axis (degrees). 0 = the sun sits at compass azimuth measured from world +Z toward +X (south at noon in the northern hemisphere = world -Z).")]
    [SerializeField] private float sunAzimuthOffset = 0f;
    [Tooltip("Distance fog on or off (the fog colour is the scene's Lighting > Fog colour). Off by default: fog limits how far bushes can be seen. The ladder's sessions turn it on lightly (scripts/ladder.py).")]
    [SerializeField] private bool fogEnabled = false;
    [Tooltip("Linear fog: the distance (world units) where fog begins. Nothing nearer is affected. Used when fogEnabled is on.")]
    [SerializeField] private float fogStartDistance = 50f;
    [Tooltip("Linear fog: the distance where fog is complete (everything beyond is the fog colour). Mountains take mountainFogStrength of the fog. The valley is 700 wide.")]
    [SerializeField] private float fogEndDistance = 200f;
    [Tooltip("optical depth of the atmosphere at the zenith for red, green and blue. The sun's colour is exp(-depth * air mass), which turns it from warm white at noon to orange near the horizon (blue is removed fastest).")]
    [SerializeField] private Vector3 sunExtinction = new Vector3(0.10f, 0.16f, 0.30f);
    [Tooltip("how much of the physical colour shift is applied (0 = constant warm white, 1 = fully physical). Lower it to keep ground and canopy hues easier to judge at dusk.")]
    [SerializeField] [Range(0f, 1f)] private float sunHueStrength = 0.8f;
    [Tooltip("constant Sky Tint of the procedural sky (grey = Unity's neutral); the sunset colours then come from the shader's scattering as the sun lowers.")]
    [SerializeField] private Color skyTintNeutral = new Color(0.5f, 0.5f, 0.5f);
    [Tooltip("constant Atmosphere Thickness of the procedural sky.")]
    [SerializeField] private float skyAtmosphereThickness = 1f;
    [Tooltip("x = sun elevation in degrees, y = directional light intensity. Acts on the canopy (standard lit shader) and fruit highlights; the terrain and fruit shaders ignore it.")]
    [SerializeField] private AnimationCurve sunIntensityByElevation = ElevationCurve(0f, 0.1f, 5f, 0.25f, 10f, 0.45f, 20f, 0.8f, 34f, 1.15f, 45f, 1.35f, 62f, 1.5f, 90f, 1.5f);
    [Tooltip("x = sun elevation in degrees, y = ambient intensity multiplier (Lighting > Environment > Intensity Multiplier). The ambient probe is rebuilt from the sky a few times a second, so it also reddens and dims with the sun.")]
    [SerializeField] private AnimationCurve ambientIntensityByElevation = ElevationCurve(0f, 0.2f, 10f, 0.35f, 20f, 0.6f, 34f, 0.85f, 45f, 1f, 90f, 1f);
    [Tooltip("minimum seconds between rebuilds of the ambient probe from the sky (DynamicGI.UpdateEnvironment re-renders the environment cubemap and can cause a frame spike). 0 = build it once at the start only.")]
    [SerializeField] private float ambientUpdateInterval = 1.5f;
    [Tooltip("the sun must also have moved at least this many degrees since the last rebuild of the ambient probe.")]
    [SerializeField] private float ambientUpdateMinDegrees = 2f;
    [Tooltip("x = sun elevation in degrees, y = the procedural sky's Exposure.")]
    [SerializeField] private AnimationCurve skyExposureByElevation = ElevationCurve(0f, 1f, 10f, 1.1f, 20f, 1.25f, 34f, 1.3f, 90f, 1.3f);
    [Tooltip("Multiplies the sun's intensity curve at every elevation (1 = the curve as it is). Acts on the canopy and fruit highlights only: the terrain ignores the sun's intensity (use postExposureOffset to brighten everything).")]
    [SerializeField] private float sunIntensityScale = 1f;
    [Tooltip("Stops (EV) added to the post-exposure curve at every elevation: positive brightens the whole screen (terrain, canopy, sky), 0 = the curve as it is. Fruit undo it through fruitExposureCompensation, so a fruit keeps its brightness.")]
    [SerializeField] private float postExposureOffset = 0f;
    [Tooltip("x = sun elevation in degrees, y = post-exposure in stops (EV) of the URP Color Adjustments override. 0 = unchanged; negative darkens everything on screen, including the fruit (hue unchanged, luminance lower).")]
    [SerializeField] private AnimationCurve postExposureByElevation = ElevationCurve(0f, -1f, 10f, -0.6f, 20f, -0.3f, 34f, 0f, 90f, 0f);
    [Tooltip("Optional floor (degrees) on the light's elevation. 0 = off (the sun follows the real path). Raise it if low-sun shadow artifacts appear; the earlier fixed arc used 25.")]
    [SerializeField] private float minSunElevation = 0f;

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

    // Piecewise-linear default curve from (x0, y0, x1, y1, ...) pairs, with tangents matching the segment slopes.
    private static AnimationCurve ElevationCurve(params float[] xy)
    {
        int n = xy.Length / 2;
        var keys = new Keyframe[n];
        for (int i = 0; i < n; i++)
        {
            float x = xy[2 * i], y = xy[2 * i + 1];
            float inSlope = i > 0 ? (y - xy[2 * i - 1]) / (x - xy[2 * i - 2]) : 0f;
            float outSlope = i < n - 1 ? (xy[2 * i + 3] - y) / (xy[2 * i + 2] - x) : 0f;
            if (i == 0) inSlope = outSlope;
            if (i == n - 1) outSlope = inSlope;
            keys[i] = new Keyframe(x, y, inSlope, outSlope);
        }

        return new AnimationCurve(keys);
    }

    public RewardFunction RewardFunction => rewardFunction;
    public float SessionDuration => sessionDuration;
    public int WorldSeed => worldSeed;
    public bool IsPractice => isPractice;
    public string ExperimentCode => name.Split('_')[0];
    public bool FreezeSun => freezeSun;
    public int RankingEvery => rankingEvery;
    public int RankingSets => rankingSets;
    public float RankingSeconds => rankingSeconds;
    public float RankingCooldown => rankingCooldown;
    public float RankingSettleDepth => rankingSettleDepth;
    public int RankingPoolSets => rankingPoolSets;
    public float RankingFadeSeconds => rankingFadeSeconds;
    public float RankingGraySeconds => rankingGraySeconds;
    public float RankingFruitSeconds => rankingFruitSeconds;
    public float RankingLastSeconds => rankingLastSeconds;
    public int RankingMinBushes => rankingMinBushes;
    public string RankingText => rankingText;
    public int RankingSetSize => rankingSetSize;
    public float RankingArcSpan => rankingArcSpan;
    public float RankingDistance => rankingDistance;
    public float RankingTieGap => rankingTieGap;
    public float RankingRimScale => rankingRimScale;
    public float RankingRimBoost => rankingRimBoost;
    public float RankingMarkerLift => rankingMarkerLift;
    public float RankingRankScale => rankingRankScale;
    public float RankingBonusPerPair => rankingBonusPerPair;
    public float RankingAimTolerance => rankingAimTolerance;
    public string HintsFile => hintsFile;

    // A copy for a reduced run (RunModes.Short; never the asset itself, which would be saved into the file): a session lasts `factor` of its length.
    // The copy keeps the asset's name, which names the world file.
    public SessionConfig ScaledCopy(float factor)
    {
        SessionConfig copy = Instantiate(this);
        copy.name = name;
        copy.sessionDuration = RunModes.SessionSeconds(this, factor);
        return copy;
    }
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
    public float FootstepVolume => footstepVolume;
    public float MusicVolume => musicVolume;
    public float FootstepStride => footstepStride;
    public float BedVolume => bedVolume;
    public float BirdVolume => birdVolume;
    public float BirdIntervalMin => birdIntervalMin;
    public float BirdIntervalMax => birdIntervalMax;
    public int BurstCount => burstCount;
    public float BurstSpeed => burstSpeed;
    public float BurstDuration => burstDuration;
    public float BurstSize => burstSize;
    public int FruitCount => fruitCount;
    public float FruitRadius => fruitRadius;
    public string Layout => layout;
    public string Assignment => assignment;
    public string RewardStage => rewardStage;
    public float TileRadius => tileRadius;
    public float TileRampWidth => tileRampWidth;
    public int TileMoistureLevels => tileMoistureLevels;
    public int TileBushes => tileBushes;
    public float TileClusterRadius => tileClusterRadius;
    public float TileClusterSpacing => tileClusterSpacing;
    public float TileSpread => tileSpread;
    public string TileArrangement => tileArrangement;
    public string TileValueMode => tileValueMode;
    public string TileWithinMode => tileWithinMode;
    public float TileGoodFraction => tileGoodFraction;
    public int TileSmoothness => tileSmoothness;
    public float TileGradient => tileGradient;
    public float TileGradientAngle => tileGradientAngle;
    public float TileCoverageMin => tileCoverageMin;
    public float TileStartSpreadMin => tileStartSpreadMin;
    public string DesignJson => designJson;
    public bool ShapeVaries => shapeVaries;
    public float ShapeWhenFixed => shapeWhenFixed;
    public float ColorWhenFixed => colorWhenFixed;
    public bool ColorVaries => colorVaries;
    public bool MoistureVaries => moistureVaries;
    public float MoistureWhenFixed => moistureWhenFixed;
    public bool MoistureIsFeature => moistureIsFeature;
    public Vector2 RandomBushValueRange => randomBushValueRange;

    public int TargetFrameRate => targetFrameRate;
    public float UploadGraceSeconds => uploadGraceSeconds;
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
    public float CrosshairRadius => crosshairRadius;
    public float CrosshairReleaseScale => crosshairReleaseScale;
    public float CrosshairAlpha => crosshairAlpha;
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
    // The fruit color for a color attribute value in 0..1.
    public Color FruitColor(float t)
    {
        if (fruitColorRamp == null || fruitColorRamp.Length < 2)
        {
            return Color.Lerp(new Color(0.2f, 0.4f, 1.0f), new Color(1.0f, 0.5f, 0.1f), t);
        }

        float position = Mathf.Clamp01(t) * (fruitColorRamp.Length - 1);
        int low = Mathf.Min((int)position, fruitColorRamp.Length - 2);
        return Color.Lerp(fruitColorRamp[low], fruitColorRamp[low + 1], position - low);
    }

    public float FruitColorPreservation => fruitColorPreservation;
    public float FruitShadingFloor => fruitShadingFloor;
    public float FruitBrightness => fruitBrightness;
    public float FruitExposureCompensation => fruitExposureCompensation;
    public float SunIntensityScale => sunIntensityScale;
    public float PostExposureOffset => postExposureOffset;
    public Color CanopyTintDark => canopyTintDark;
    public Color CanopyTintLight => canopyTintLight;

    /// <summary>The canopy tint of a bush at position u in [0, 1] of the tint range (dark end, none, light end).</summary>
    public Color CanopyTint(float u)
    {
        return u < 0.5f ? Color.Lerp(canopyTintDark, Color.white, 2f * u) : Color.Lerp(Color.white, canopyTintLight, 2f * u - 1f);
    }
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
    public float FogStartDistance => fogStartDistance;
    public float FogEndDistance => fogEndDistance;
    public float SunStartElevation => sunStartElevation;
    public float AmbientUpdateInterval => ambientUpdateInterval;
    public float AmbientUpdateMinDegrees => ambientUpdateMinDegrees;
    public Vector3 SunExtinction => sunExtinction;
    public float SunHueStrength => sunHueStrength;
    public Color SkyTintNeutral => skyTintNeutral;
    public float SkyAtmosphereThickness => skyAtmosphereThickness;
    public AnimationCurve SunIntensityByElevation => sunIntensityByElevation;
    public AnimationCurve AmbientIntensityByElevation => ambientIntensityByElevation;
    public AnimationCurve SkyExposureByElevation => skyExposureByElevation;
    public AnimationCurve PostExposureByElevation => postExposureByElevation;
    public float SunLatitude => sunLatitude;
    public float SunDeclination => sunDeclination;
    public float SunEndElevation => sunEndElevation;
    public float SunAzimuthOffset => sunAzimuthOffset;
    public float MinSunElevation => minSunElevation;
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
