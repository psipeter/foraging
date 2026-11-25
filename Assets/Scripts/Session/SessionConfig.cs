using UnityEngine;
using UnityEngine.Serialization;

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

    [Header("Selection (a set of bushes played in place after patch switches, on the terrain the player stands on; the set file is read from scripts/selection.py pool)")]
    [Tooltip("A selection is due after this many patch switches (a settled crossing into another tile); 0 = no selections.")]
    [FormerlySerializedAs("rankingEvery")] [SerializeField] private int selectionEvery = 0;
    [Tooltip("The patch leavings (numbered from 1: a qualifying switch, see selectionCooldown / selectionMinBushes / selectionLastSeconds) after which a selection is due, for example 1, 2, 4, 8. Empty = every 'selectionEvery'-th leaving. selectionEvery must still be above 0 to turn selections on.")]
    [FormerlySerializedAs("rankingLeavings")] [SerializeField] private int[] selectionLeavings = new int[0];
    [Tooltip("Selection sets played in one selection.")]
    [FormerlySerializedAs("rankingSets")] [SerializeField] private int selectionSets = 1;
    [Tooltip("Seconds of the countdown of one selection set (the main clock is frozen meanwhile).")]
    [FormerlySerializedAs("rankingSeconds")] [SerializeField] private float selectionSeconds = 20f;
    [Tooltip("The fewest seconds of foraging between the end of one selection and a patch switch that counts toward the next (a switch inside this time is ignored; 0 in FOR and TUT: the harvest rule alone spaces the selections).")]
    [FormerlySerializedAs("rankingCooldown")] [SerializeField] private float selectionCooldown = 10f;
    [Tooltip("A crossing into another tile counts as a patch switch once the player is this many units past the edge between the tiles (0 = at the edge itself, so the selection starts as early as possible and the arc is farthest from the next cluster).")]
    [FormerlySerializedAs("rankingSettleDepth")] [SerializeField] private float selectionSettleDepth = 0f;
    [Tooltip("Sets in the pool file (used in order, one after another). Read by scripts/selection.py pool: regenerate the file after changing it.")]
    [FormerlySerializedAs("rankingPoolSets")] [SerializeField] private int selectionPoolSets = 12;
    [Tooltip("Seconds the selection bushes take to grow and to shrink away again.")]
    [FormerlySerializedAs("rankingFadeSeconds")] [SerializeField] private float selectionFadeSeconds = 0.4f;
    [Tooltip("Seconds the world's bushes take to fade to grayscale when a selection starts, and back to colour when it ends.")]
    [FormerlySerializedAs("rankingGraySeconds")] [SerializeField] private float selectionGraySeconds = 0.25f;
    [Tooltip("Seconds per fruit while harvesting a selection bush (a whole bush takes this times fruitCount): quick.")]
    [FormerlySerializedAs("rankingFruitSeconds")] [SerializeField] private float selectionFruitSeconds = 0.05f;
    [Tooltip("No selection starts when this many seconds or fewer of the session are left.")]
    [FormerlySerializedAs("rankingLastSeconds")] [SerializeField] private float selectionLastSeconds = 10f;
    [Tooltip("A patch switch counts toward a selection only once the participant has harvested (taken a fruit from) at least this many different bushes since the last selection ended (since the session began, before the first), so no selection comes before they have seen what a bush pays and none follows another without foraging in between.")]
    [FormerlySerializedAs("rankingMinBushes")] [SerializeField] private int selectionMinBushes = 1;
    [Tooltip("The line shown at the top of the screen during a selection.")]
    [FormerlySerializedAs("rankingText")] [SerializeField] private string selectionText = "Select the 5 most valuable bushes. 100 points available.";
    [Tooltip("Bushes per set. Read by scripts/selection.py.")]
    [FormerlySerializedAs("rankingSetSize")] [SerializeField] private int selectionSetSize = 5;
    [Tooltip("Degrees from the leftmost to the rightmost bush centre (the arc is symmetric about the heading). The outermost centres must stay inside the view of a 4:3 window, so at least half of each bush is on screen without turning: scripts/selection.py checks. Read by scripts/selection.py.")]
    [FormerlySerializedAs("rankingArcSpan")] [SerializeField] private float selectionArcSpan = 84f;
    [Tooltip("Distance from the player to the nearest point of each canopy (world units); the same for every bush. Read by scripts/selection.py.")]
    [FormerlySerializedAs("rankingDistance")] [SerializeField] private float selectionDistance = 16f;
    [Tooltip("The smallest true reward difference (points per fruit) between two bushes of a set; pairs closer than this are ties and score nothing. Read by scripts/selection.py.")]
    [FormerlySerializedAs("rankingTieGap")] [SerializeField] private float selectionTieGap = 0.25f;
    [Tooltip("How the pool's sets are chosen: \"ladder\" (or empty) = five bushes whose true values form a ladder spread over the feature plane (the first design); \"plus\" = five bushes in a plus shape in the (shape, color) plane around the value map's peak. Read by scripts/selection.py.")]
    [FormerlySerializedAs("rankingDesign")] [SerializeField] private string selectionDesign = "ladder";
    [Tooltip("Plus design: the plus's two axes. \"aligned\" = the shape and color axes; \"bump\" = the global-maximum bump's own axes (turned and stretched like it); \"random\" = a random turn and stretch; \"mixed\" = the sets take aligned, random, random in turn. A plus that would leave the map is shrunk and turned to fit. Read by scripts/selection.py.")]
    [FormerlySerializedAs("rankingPlusAxes")] [SerializeField] private string selectionPlusAxes = "mixed";
    [Tooltip("Plus design: the centre bushes lie evenly spread (a sunflower spiral per axes mode) over an ellipse around the peak of this radius, in spreads (sigma) of the peak's bump along each of its axes. Read by scripts/selection.py.")]
    [FormerlySerializedAs("rankingPlusJitter")] [SerializeField] private float selectionPlusJitter = 1f;
    [Tooltip("Plus design: the arms reach this many spreads (sigma) from the centre along the plus's axes (each arm draws its own length between 0.7 and 1.3 times this). Read by scripts/selection.py.")]
    [FormerlySerializedAs("rankingPlusArm")] [SerializeField] private float selectionPlusArm = 1f;
    [Tooltip("Plus design, random axes: the second axis is this many times (at most) longer or shorter than the first, drawn log-uniformly. Read by scripts/selection.py.")]
    [FormerlySerializedAs("rankingPlusArmRatio")] [SerializeField] private float selectionPlusArmRatio = 2f;
    [Tooltip("Plus design: where the three pluses of a selection go: \"spiral\" (each axes mode on a sunflower spiral around the peak), \"ring\" (a triangle around the peak per selection, rotating and widening) \"tile\" (greedy space filling of the rewarding region) or \"cover\" (centres anywhere in the rewarding region, each selection tiling it between its three pluses). Read by scripts/selection.py and plus_plans.py.")]
    [FormerlySerializedAs("rankingPlusPlan")] [SerializeField] private string selectionPlusPlan = "spiral";
    [Tooltip("Plus design: the spread of values in a set: \"free\" (whatever the fit gives), \"easy\", \"medium\", \"hard\" (a ladder of values a fixed step apart, wide to narrow), a number (the step as a share of the peak) or \"mixed\" (easy, medium, hard over the selections). Read by scripts/plus_plans.py.")]
    [FormerlySerializedAs("rankingPlusDifficulty")] [SerializeField] private string selectionPlusDifficulty = "free";
    [Tooltip("Plus design: the smallest distance in the unit (shape, color) plane between two bushes of a set, so they look different. Read by scripts/selection.py.")]
    [FormerlySerializedAs("rankingPlusMinSeparation")] [SerializeField] private float selectionPlusMinSeparation = 0.08f;
    [Tooltip("Fixed schedule: the session seconds (elapsed, the clock is held in a selection) at which the 1st, 2nd, ... selection becomes due, for example 30, 60, 90, 120, 150 (empty = the patch-leaving rules above). A due selection starts at the next moment no harvest is under way, or after selectionMaxWait seconds at most.")]
    [FormerlySerializedAs("rankingTimes")] [SerializeField] private float[] selectionTimes = new float[0];
    [Tooltip("Fixed schedule: the most seconds a due selection waits for a harvest bout to end; then the bout is cancelled and the selection starts.")]
    [FormerlySerializedAs("rankingMaxWait")] [SerializeField] private float selectionMaxWait = 10f;
    [Tooltip("Dense design (selectionDesign 'dense'): how many bushes the participant picks (harvests) in a selection of the grid, the best of the 25.")]
    [FormerlySerializedAs("rankingPicks")] [SerializeField] private int selectionPicks = 5;
    [Tooltip("Dense design: the distance in world units between neighbouring bushes of the 5x5 grid on the stage. Read by scripts/selection.py.")]
    [FormerlySerializedAs("rankingGridSpacing")] [SerializeField] private float selectionGridSpacing = 7f;
    [Tooltip("Dense design: the distance from the player to the middle of the grid (world units, along the heading). Read by scripts/selection.py.")]
    [FormerlySerializedAs("rankingGridDistance")] [SerializeField] private float selectionGridDistance = 18f;
    [Tooltip("Dense design: the preset of scripts/dense_grid.py that plans the five grids (even, balanced, diverse). Read by scripts/selection.py.")]
    [FormerlySerializedAs("rankingGridPreset")] [SerializeField] private string selectionGridPreset = "balanced";
    [Tooltip("Dense design: points a selection is worth at most (the 'top_k' points mode: 100 x (picked sum - expected sum of a random pick) / (best sum - expected sum), from 0).")]
    [FormerlySerializedAs("rankingTopKPoints")] [SerializeField] private float selectionTopKPoints = 100f;
    [Tooltip("Dense design: which selections pay: 'one' = one selection, drawn from the world seed, pays its points; 'all' = every selection pays.")]
    [FormerlySerializedAs("rankingPaid")] [SerializeField] private string selectionPaid = "one";
    [Tooltip("The halo of the bush being aimed at is a copy of its canopy this many times larger (the main task uses 1.03), so it shows at the selection's distance.")]
    [FormerlySerializedAs("rankingRimScale")] [SerializeField] private float selectionRimScale = 1.15f;
    [Tooltip("How many times brighter the rim of the bush being aimed at is than in the main task.")]
    [FormerlySerializedAs("rankingRimBoost")] [SerializeField] private float selectionRimBoost = 3f;
    [Tooltip("How far above the usual spot the progress ring and the rank number sit, in ring diameters, so they clear the canopy and its halo at the selection's distance.")]
    [FormerlySerializedAs("rankingMarkerLift")] [SerializeField] private float selectionMarkerLift = 0.75f;
    [Tooltip("Size of the rank number, as a multiple of the number's size in the main task's units (the digits are about this times 1.2 degrees tall).")]
    [FormerlySerializedAs("rankingRankScale")] [SerializeField] private float selectionRankScale = 3f;
    [Tooltip("Hidden bonus points per correctly ordered pair (a set of k bushes implies k(k-1)/2 pairs; pairs whose true values are tied are not counted, and a pair with an unranked bush is never correct), shown only on the final screen. Practice sessions award none. Provisional: scoring is decided at analysis time.")]
    [FormerlySerializedAs("rankingBonusPerPair")] [SerializeField] private float selectionBonusPerPair = 4f;
    [Tooltip("How a correct pair is paid: \"pair\" (or empty) is the bonus per correct pair; \"pair_mean_value\" is the bonus times the mean of the pair's two true bush values, so a miss among the best bushes costs more than among the poor ones. scripts/selection.py POINTS_MODES lists the modes; SelectionSets.PairWeight is the same rule.")]
    [FormerlySerializedAs("rankingPointsMode")] [SerializeField] private string selectionPointsMode = "pair";
    [Tooltip("Degrees beyond a canopy's edge at which the crosshair still selects it in a selection when crosshairRadius is 0, the cone rule (0 = the crosshair must be inside the canopy; with the crosshair, selectionCrosshairRadius decides).")]
    [FormerlySerializedAs("rankingAimTolerance")] [SerializeField] private float selectionAimTolerance = 1.5f;
    [Tooltip("The crosshair's hidden hit circle during a selection (degrees), in place of crosshairRadius: the bushes of a set stand at least 2 degrees apart in the view, so a circle of up to 1 degree can touch only one of them. 0 = crosshairRadius. Read by scripts/replay.py from the log.")]
    [FormerlySerializedAs("rankingCrosshairRadius")] [SerializeField] private float selectionCrosshairRadius = 1f;
    [Tooltip("How far below the player's ground the disc's surface lies (units), so the player looks down onto the bushes. The camera is never moved.")]
    [FormerlySerializedAs("rankingStageDrop")] [SerializeField] private float selectionStageDrop = 3f;
    [Tooltip("Degrees the stage tips about the player's right: the far side rises, so the rows behind do not hide each other and the bushes stand upright on a hillside (0 = flat). The camera is never moved.")]
    [FormerlySerializedAs("rankingStageTilt")] [SerializeField] private float selectionStageTilt = 0f;
    [Tooltip("How far the disc's edge lies beyond the outermost bushes of the set (units).")]
    [FormerlySerializedAs("rankingStageMargin")] [SerializeField] private float selectionStageMargin = 4f;
    [Tooltip("How far the real terrain (and the sky's mountains) fade towards grey while a selection runs, 0 to 1. The world's bushes always fade fully.")]
    [Range(0f, 1f)]
    [FormerlySerializedAs("rankingStageWorldGray")] [SerializeField] private float selectionStageWorldGray = 0.6f;

    [Header("Instructions")]
    [Tooltip("File in StreamingAssets shown before this session. '{part}' and '{total}' are replaced by this session's number and the count of sessions.")]
    [SerializeField] private string instructionsFile = "instructions.txt";
    [Tooltip("The small blue line above the title of this session's instruction screens, its hint popups and its end screen, instead of \"Session n of m\" (for example \"Tutorial\"). Empty = the session's number.")]
    [SerializeField] private string sessionLabel = "";
    [Tooltip("Optional file in StreamingAssets of popup hints that appear as the participant acts (the first line of a block is its trigger: see UI/TutorialHints.cs). Empty = no hints.")]
    [SerializeField] private string hintsFile = "";
    [Tooltip("Small texts on the end screen of a session that has selections: under the foraging points, under the selection points, and centred under the total. Empty = none. **bold** works.")]
    [SerializeField] private string scoreCaptionForaging = "";
    [SerializeField] private string scoreCaptionSelection = "";
    [SerializeField] private string scoreNote = "";
    [Tooltip("Optional text kept on screen during the session (empty = none).")]
    [SerializeField] private string controlsReminder = "";
    [Tooltip("Opacity (0-1) of the controls reminder.")]
    [SerializeField] [Range(0f, 1f)] private float controlsReminderOpacity = 0.35f;

    [Header("Reward")]
    [SerializeField] private RewardFunction rewardFunction = new RewardFunction();
    [SerializeField] private float rewardStd = 1.0f;

    [Header("Display")]
    [Tooltip("Frame rate cap (vsync is turned off so the cap applies). 120 matches common VR headset refresh rates and bounds the size of the per-frame trajectory log. Not used in a browser (WebGL), which follows the display's refresh rate: see docs/DECISIONS.md, WebGL frame pacing.")]
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
    [Tooltip("The crosshair's hidden hit circle (degrees of view angle around the centre of the screen): a bush can be harvested only while this circle touches its canopy (the canopy's real shape, above and below as well as to the sides), together with the harvest range. Used by main sessions and selections alike. 0 = the old rule (a 35 degree cone of yaw, harvestMaxAngle; selectionAimTolerance). Read by scripts/replay.py from the log.")]
    [SerializeField] private float crosshairRadius = 7f;
    [Tooltip("A harvest in progress (main sessions) keeps going while the circle, grown by this factor, still touches the bush, so hand tremor at the edge does not pause it. Starting a harvest uses the plain circle.")]
    [SerializeField] private float crosshairReleaseScale = 2f;
    [Tooltip("Opacity of the thin grey crosshair drawn at the centre of the screen, always (0 = hidden, 1 = solid). It brightens on a bush that can be harvested.")]
    [Range(0f, 1f)]
    [SerializeField] private float crosshairAlpha = 0.25f;
    [Tooltip("Apparent diameter, in degrees of the camera's view, of the harvest ring the crosshair becomes on a bush (UI/AimCrosshair). Not the hit circle (crosshairRadius).")]
    [SerializeField] private float crosshairRingSizeDeg = 3.5f;
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
    [Tooltip("Size reference, in degrees of view of the camera, of the rank numbers above the bushes of a selection set (the crosshair's harvest ring has its own, crosshairRingSizeDeg).")]
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
    [Tooltip("Per-fruit reward at which popup size/brightness and sound pitch reach their maximum (about the top of the per-fruit reward range; a fruit worth more takes the top tone). Differs per session, always in points (scripts/design: the map's peak).")]
    [SerializeField] private float rewardFeedbackMax = 6f;
    [Tooltip("How strongly the +X popup's size and brightness follow the reward: 0 = every fruit gets an identical popup, 1 = full scaling. The number itself is always shown.")]
    [SerializeField] [Range(0f, 1f)] private float rewardSizeScaling = 1f;
    [Tooltip("+X popup size multiplier (relative to the prefab) at zero reward.")]
    [SerializeField] private float popupScale = 1.7f;
    [Tooltip("Extra popup size multiplier at rewardFeedbackMax (times rewardSizeScaling).")]
    [SerializeField] private float popupExtraScale = 0.9f;
    [Tooltip("Popup and score-flash color. Keep it pale and near-neutral: fruit hue runs blue to orange, and red/green are not used.")]
    [SerializeField] private Color popupColor = new Color(1f, 0.95f, 0.78f);
    [Tooltip("Pitch range of the fruit-pick sound, in semitones from zero reward (440 Hz) to rewardFeedbackMax, in equal steps per point. 12 (an octave) in every session, so the lowest and the highest tone sound the same whatever the session's maximum. 0 = the same pitch for every reward.")]
    [SerializeField] private float pitchSemitoneRange = 12f;
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
    [Tooltip("Fruit color along the color attribute (0..1): evenly spaced stops, linearly interpolated. Generated by scripts/fruit_ramp.py (plasma re-spaced to equal perceptual steps); do not hand-edit. See docs/DECISIONS.md, \"Fruit colour ramp\". Fewer than two stops fall back to a blue to orange pair.")]
    [SerializeField] private Color[] fruitColorRamp = new Color[0];
    [SerializeField] private Vector2 shapeRange = new Vector2(0f, 1f);
    [SerializeField] private Vector2 canopyWidthRange = new Vector2(2.0f, 5.0f);
    [SerializeField] private Vector2 canopyHeightRange = new Vector2(1.2f, 2.8f);
    [Tooltip("Which world-generator stage lays out the bushes (scripts/world.py LAYOUTS). The only layout is \"tiles\". Read by scripts/world.py: regenerate the world after changing it.")]
    [SerializeField] private string layout = "";
    [Tooltip("Which stage gives each bush its attributes (scripts/world.py ASSIGNMENTS). The only assignment is \"tiles\".")]
    [SerializeField] private string assignment = "";
    [Tooltip("Which stage turns a bush's attributes into its reward (scripts/world.py REWARDS). Empty = the sum of the reward function's bumps.")]
    [SerializeField] private string rewardStage = "";
    [Tooltip("What the experiment's design says about this instance (scripts/design/<code>.py): the instance id, its cell parameters and its hint arm, as JSON. Written by the experiment builder, logged with the rest of this config, read by no game code.")]
    [SerializeField] private string designJson = "";
    [Tooltip("False: every bush has the value shapeWhenFixed, so all canopies are identical, so the reward is read at one shape value. Read by scripts/world.py: regenerate the world after changing it.")]
    [SerializeField] private bool shapeVaries = true;
    [Tooltip("The shape value of every bush when shapeVaries is off (0..1; the canopy size then follows the shape axis). Read by scripts/world.py.")]
    [SerializeField] private float shapeWhenFixed = 0.5f;
    [Tooltip("False: every bush has the value colorWhenFixed, so all fruit have one color, so the reward is read at one color value. Read by scripts/world.py: regenerate the world after changing it.")]
    [SerializeField] private bool colorVaries = true;
    [Tooltip("The color value of every bush when colorVaries is off (0..1). Read by scripts/world.py.")]
    [SerializeField] private float colorWhenFixed = 0.5f;
    [Tooltip("False: the valley has one moisture value (moistureWhenFixed), so the ground is one colour and flat (elevation follows moisture), and moisture cannot pay. Read by scripts/world.py: regenerate the world after changing it.")]
    [SerializeField] private bool moistureVaries = true;
    [Tooltip("The moisture of the whole valley when moistureVaries is off (0..1).")]
    [SerializeField] private float moistureWhenFixed = 0.5f;
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
    [Tooltip("How the bushes lie inside a tile (scripts/tiles.py ARRANGEMENTS). Empty = random.")]
    [SerializeField] private string tileArrangement = "";
    [Tooltip("How the world's pool of bushes (an even cover of the feature plane) is dealt to the tiles (scripts/tiles.py PLACEMENTS: random, balanced). Empty = random.")]
    [SerializeField] private string tilePlacement = "";
    [Tooltip("A tile together with its six neighbours must have bushes in at least this share of the feature plane (4 x 4 cells), for every tile with all six; the assignment is redrawn until it holds. 0 = off.")]
    [SerializeField] [Range(0f, 1f)] private float tileCoverageMin = 0f;
    [Tooltip("The tiles around the start must differ in mean reward by at least this share of the reward's range over the feature plane; the assignment is redrawn until it holds. 0 = off.")]
    [SerializeField] [Range(0f, 1f)] private float tileStartSpreadMin = 0f;
    [Tooltip("No tile's total bush value (points, after the session's gain) may differ from the mean tile total by more than this; the assignment is redrawn until it holds (use with the balanced placement). 0 = off.")]
    [SerializeField] private float tileSumTol = 0f;

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
    [Tooltip("Distance fog on or off (the fog colour is the scene's Lighting > Fog colour). Off by default: fog limits how far bushes can be seen.")]
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
    public int SelectionEvery => selectionEvery;
    public int[] SelectionLeavings => selectionLeavings ?? new int[0];
    public int SelectionSets => selectionSets;
    public float SelectionSeconds => selectionSeconds;
    public float SelectionCooldown => selectionCooldown;
    public float SelectionSettleDepth => selectionSettleDepth;
    public int SelectionPoolSets => selectionPoolSets;
    public float SelectionFadeSeconds => selectionFadeSeconds;
    public float SelectionGraySeconds => selectionGraySeconds;
    public float SelectionFruitSeconds => selectionFruitSeconds;
    public float SelectionLastSeconds => selectionLastSeconds;
    public int SelectionMinBushes => selectionMinBushes;
    public string SelectionText => selectionText;
    public int SelectionSetSize => selectionSetSize;
    public float SelectionArcSpan => selectionArcSpan;
    public float SelectionDistance => selectionDistance;
    public float SelectionTieGap => selectionTieGap;
    public string SelectionDesign => string.IsNullOrEmpty(selectionDesign) ? "ladder" : selectionDesign;
    public string SelectionPlusAxes => string.IsNullOrEmpty(selectionPlusAxes) ? "mixed" : selectionPlusAxes;
    public float SelectionPlusJitter => selectionPlusJitter;
    public float SelectionPlusArm => selectionPlusArm;
    public float SelectionPlusArmRatio => selectionPlusArmRatio;
    public float SelectionPlusMinSeparation => selectionPlusMinSeparation;
    public float[] SelectionTimes => selectionTimes ?? new float[0];
    public float SelectionMaxWait => selectionMaxWait;
    public int SelectionPicks => selectionPicks;
    public float SelectionGridSpacing => selectionGridSpacing;
    public float SelectionGridDistance => selectionGridDistance;
    public string SelectionGridPreset => string.IsNullOrEmpty(selectionGridPreset) ? "balanced" : selectionGridPreset;
    public float SelectionTopKPoints => selectionTopKPoints;
    public string SelectionPaid => string.IsNullOrEmpty(selectionPaid) ? "one" : selectionPaid;
    public string SelectionPlusPlan => string.IsNullOrEmpty(selectionPlusPlan) ? "spiral" : selectionPlusPlan;
    public string SelectionPlusDifficulty => string.IsNullOrEmpty(selectionPlusDifficulty) ? "free" : selectionPlusDifficulty;
    public float SelectionRimScale => selectionRimScale;
    public float SelectionRimBoost => selectionRimBoost;
    public float SelectionMarkerLift => selectionMarkerLift;
    public float SelectionRankScale => selectionRankScale;
    public float SelectionBonusPerPair => selectionBonusPerPair;
    public string SelectionPointsMode => string.IsNullOrEmpty(selectionPointsMode) ? "pair" : selectionPointsMode;
    public float SelectionAimTolerance => selectionAimTolerance;
    public float SelectionCrosshairRadius => selectionCrosshairRadius;
    public float SelectionStageDrop => selectionStageDrop;
    public float SelectionStageMargin => selectionStageMargin;
    public float SelectionStageTilt => selectionStageTilt;
    public float SelectionStageWorldGray => selectionStageWorldGray;
    public string HintsFile => hintsFile;
    public string SessionLabel => sessionLabel;
    public string ScoreCaptionForaging => scoreCaptionForaging;
    public string ScoreCaptionSelection => scoreCaptionSelection;
    public string ScoreNote => scoreNote;

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
    public string TilePlacement => tilePlacement;
    public string TileArrangement => tileArrangement;
    public float TileCoverageMin => tileCoverageMin;
    public float TileStartSpreadMin => tileStartSpreadMin;
    public float TileSumTol => tileSumTol;
    public string DesignJson => designJson;
    public bool ShapeVaries => shapeVaries;
    public float ShapeWhenFixed => shapeWhenFixed;
    public float ColorWhenFixed => colorWhenFixed;
    public bool ColorVaries => colorVaries;
    public bool MoistureVaries => moistureVaries;
    public float MoistureWhenFixed => moistureWhenFixed;

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
    public float CrosshairRingSizeDeg => crosshairRingSizeDeg;
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
