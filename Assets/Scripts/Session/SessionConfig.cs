using UnityEngine;

// What happens to the bush that was not chosen in an Interlude trial once the player starts harvesting one. The order is part of the
// logged format (the manifest stores the number): Allow 0, Lock 1, Exhaust 2, Hide 3.
public enum InterludeSwitchPolicy
{
    Allow,      // nothing: the player may switch bushes; the first bush to reach the required fruit count is the choice
    Lock,       // the other bush stays as it is but can no longer be harvested
    Exhaust,    // the other bush takes the spent look and can no longer be harvested
    Hide        // the other bush shrinks away and is hidden
}

// Which trials scripts/interlude.py generates for an Interlude asset (the game only plays the generated file). The order is part of the
// logged format (the manifest stores the number): RetiredDesigned 0, Random 1, RewardGap 2, FeatureGap 3, Hybrid 4.
public enum InterludeMode
{
    RetiredDesigned,   // the contrast / graded / extrapolation trials were removed (2026-11-09); the generator refuses it. Kept so the numbers below do not move.
    Random,     // independent random shape and color for both bushes (a definite better side in every trial)
    RewardGap,  // one pair per bin of the true reward difference, evenly spread from interludeMinRewardGap to the largest the world offers
    FeatureGap, // one pair per bin of the perceptual distance (shape, color, moisture) between the bushes, from interludeMinFeatureGap up
    Hybrid      // both spreads at once: the reward gaps and the feature gaps of the trials are each evenly spread
}

// How scripts/world.py arranges the bushes' (shape, color) records over the map (scripts/spatial.py). The order is part of the logged format
// (the session row stores the number): Off 0, Tiles 1, TilesAndSwaps 2.
public enum SpatialBalance
{
    Off,            // every bush's attributes are drawn independently of its position (rewarding bushes can cluster by chance)
    Tiles,          // the records are dealt over tiles at several scales so each tile gets an even mix of the reward quantiles
    TilesAndSwaps   // Tiles, then pairs of bushes swap records while that lowers the patchiness of the reward over disks at those scales
}

// How scripts/world.py deals (shape, color) pairs to the bushes besides the independent draw: Plane covers the feature plane evenly (see SessionConfig.featureCoverage).
public enum FeatureCoverage
{
    Off,            // not used: the features are drawn (and balanced) as spatialBalance and featureBalance say
    Plane           // the pairs are a low-discrepancy sample of the plane, dealt so every part of the map gets an even sample of it
}

// How scripts/world.py shapes the moisture (ground colour and height) field. The order is part of the logged format (the session row stores the number).
public enum MoistureTerraceMode
{
    Levels,     // the smooth field (moistureTerraceLevels < 2) or that many plateau levels, evenly or unevenly spaced (moistureTerraceUnevenness)
    Staircase,  // a random staircase over the field's ranks (plateaus of varied size and height, no level count), with a noise-shifted phase
    Diffusion   // the field smoothed by edge-preserving diffusion: flat regions where it is gentle, steps where it is steep
}

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

    [Header("Interlude")]
    [Tooltip("An Interlude is a short forced-choice block run after a session, in that session's own world (terrain, mountains, sun) with only two bushes present: the player harvests the one they think pays more. Outcomes are never shown. Its reward function and terrain parameters must match the session in interludeFor, and its worldSeed must equal that session's (scripts/interlude.py checks).")]
    [SerializeField] private bool isInterlude;
    [Tooltip("Name of the session asset this Interlude probes (e.g. S1); its world file supplies the terrain.")]
    [SerializeField] private string interludeFor = "";
    [Tooltip("Which trials scripts/interlude.py generates: Hybrid (reward gaps and feature gaps both spread evenly, with repeats; the default), RewardGap, FeatureGap or Random (random pairs, always a correct side). Read by the generator, not by the game: regenerate the Interlude file after changing it.")]
    [SerializeField] private InterludeMode interludeMode = InterludeMode.Hybrid;
    [Tooltip("Number of choice trials.")]
    [SerializeField] private int interludeTrialCount = 10;
    // Set only on the copy GameManager makes for local quick testing (QuickCopy): the Interlude plays only this many of the file's first trials. 0 = all.
    [HideInInspector] [SerializeField] private int interludeTrialLimit;
    [Tooltip("Seconds allowed per trial; the trial moves on when it runs out.")]
    [SerializeField] private float interludeTrialSeconds = 7f;
    [Tooltip("Fruits that must be harvested from a bush to register it as the choice (times fruitHarvestDuration = harvest time). Equal to fruitCount = the whole bush.")]
    [SerializeField] private int interludeHarvestFruits = 10;
    [Tooltip("What happens to the other bush when the player starts harvesting one (commitment: that bush is the choice from then on, and the trial still ends when it has been harvested). Allow = no commitment, the first bush to reach interludeHarvestFruits is the choice.")]
    [SerializeField] private InterludeSwitchPolicy interludeSwitchPolicy = InterludeSwitchPolicy.Hide;
    [Tooltip("Hidden bonus points per correct choice, shown only on the final screen. Practice Interludes award none.")]
    [SerializeField] private float interludeBonusPerCorrect = 5f;
    [Tooltip("Hold the sun still at solar noon (the Interlude is not a day).")]
    [SerializeField] private bool freezeSun;
    [Tooltip("Distance from the spawn point to the nearest point of each bush's canopy (world units). Both bushes are placed so this is equal, whatever their canopy radius (which depends on shape). Placement is searched by scripts/interlude.py: re-run it after changing.")]
    [SerializeField] private float interludeBushDistance = 22.6f;
    [Tooltip("Bearing (degrees from the heading) of each canopy's inner edge, on opposite sides, so the heading bisects the pair and turning to either is the same. Keep it large enough that neither canopy can come into harvest range by walking straight ahead (scripts/interlude.py checks).")]
    [SerializeField] private float interludeBushBearing = 31.5f;
    [Tooltip("Random-mode Interludes only: the two bushes of every trial stand on ground that differs in elevation by at least this many world units (the valley's elevation is (1 - moisture) * terrainMaxElevation), so the terrain difference is clearly visible; 0 = no minimum. Read by scripts/interlude.py: regenerate the Interlude file after changing it.")]
    [SerializeField] private float interludeMinElevationDifference = 0f;
    [Tooltip("RewardGap / Hybrid Interludes only: the smallest true reward difference (points per fruit) between the two bushes of a trial; the trials are spread evenly from here to the largest difference the world offers. About one standard error of a 10-fruit harvest mean by default. Read by scripts/interlude.py: regenerate the Interlude file after changing it.")]
    [SerializeField] private float interludeMinRewardGap = 0.25f;
    [Tooltip("FeatureGap / Hybrid Interludes only: the smallest perceptual distance between the two bushes of a trial (root mean square of the shape, color and moisture differences, each on its 0-1 scale); the trials are spread evenly from here to the largest the world offers. Read by scripts/interlude.py: regenerate the Interlude file after changing it.")]
    [SerializeField] private float interludeMinFeatureGap = 0.1f;
    [Tooltip("RewardGap / Hybrid Interludes only: the largest true reward difference (points per fruit) between the two bushes of a trial, so the trials are spread evenly from interludeMinRewardGap to here instead of to the largest the world offers; 0 = no ceiling. Read by scripts/interlude.py: regenerate the Interlude file after changing it.")]
    [SerializeField] private float interludeMaxRewardGap = 0f;
    [Tooltip("FeatureGap / Hybrid Interludes only: the largest perceptual distance between the two bushes of a trial (same scale as interludeMinFeatureGap); 0 = no ceiling. Read by scripts/interlude.py: regenerate the Interlude file after changing it.")]
    [SerializeField] private float interludeMaxFeatureGap = 0f;
    [Tooltip("RewardGap / FeatureGap / Hybrid Interludes only: how many of the interludeTrialCount trials are exact repeats of an earlier pair (same place, same bushes, same sides; the file gives the repeat bush entries of its own), a check of how consistent a participant's choices are. 0 = none. Read by scripts/interlude.py: regenerate the Interlude file after changing it.")]
    [SerializeField] private int interludeRepeatCount = 0;
    [Tooltip("RewardGap / FeatureGap / Hybrid Interludes only: per-feature trials for each visible feature (a pair that differs in that feature only, the true reward gap spread in units of rewardStd), taken out of interludeTrialCount. 0 = none. Read by scripts/interlude.py: regenerate the Interlude file after changing it.")]
    [SerializeField] private int interludeFeatureTrials = 0;
    [Tooltip("RewardGap / FeatureGap / Hybrid Interludes only: peak trials for a reward function made of Gaussian peaks (RW), taken out of interludeTrialCount: a pair of bushes from two different peaks' top regions or from a peak and from off every peak, split over the pairs the peaks allow. 0 = none. Read by scripts/interlude.py: regenerate the Interlude file after changing it.")]
    [SerializeField] private int interludePeakTrials = 0;
    [Tooltip("RewardGap / FeatureGap / Hybrid Interludes only: interaction trials for a reward function of sigmoid, Gaussian or tilted-bump terms (FI), taken out of interludeTrialCount: pairs of bushes in classes of the reward (high, middle and low parts, one feature varied, along and across a bump), split by a plan per kind of rule, reward gaps spread within a class, no pair closer than the tie gap. 0 = none. Read by scripts/interlude.py: regenerate the Interlude file after changing it.")]
    [SerializeField] private int interludeInteractionTrials = 0;
    [Tooltip("The fewest trials between a repeated pair and its repeat. Read by scripts/interlude.py: regenerate the Interlude file after changing it.")]
    [SerializeField] private int interludeRepeatSeparation = 8;

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
    [Tooltip("Bush placement: a hexagonal lattice with this nearest-neighbour distance (world units) sets bush density (about 2/(sqrt(3)*spacing^2) per square unit); the bush count follows from the valley area. Walk time between neighbouring bushes is roughly spacing / playerMoveSpeed.")]
    [SerializeField] private float treeSpacing = 23f;
    [Tooltip("Random displacement of each bush from its lattice site, as a fraction of treeSpacing (0 = strict lattice). Each bush moves within a disc of radius jitter * spacing / 2, so any two bushes stay at least spacing * (1 - jitter) apart. ~0.5 looks natural with no clusters; above ~0.7 near-pairs begin to form.")]
    [SerializeField] [Range(0f, 1f)] private float placementJitter = 0.5f;
    [Tooltip("No bushes within this distance (world units) of the player's start (the map center). The lattice is anchored so a site sits at the start, so the clearing removes whole hex rings: the first ring (6 sites at ~spacing, up to spacing * (1 + jitter / 2)) needs > 29 at spacing 23 / jitter 0.5; the second ring (at ~1.7x spacing, at least 1.73 * spacing - jitter * spacing / 2) must stay outside it. 12 clears only the center site, 31 clears the first ring too.")]
    [SerializeField] private float startClearingRadius = 31f;
    [SerializeField] private int fruitCount = 10;
    [SerializeField] private float fruitRadius = 0.15f;
    [Tooltip("Fruit color along the color attribute (0..1): evenly spaced stops, linearly interpolated. Generated by scripts/fruit_ramp.py (viridis re-spaced to equal perceptual steps); do not hand-edit. See docs/DECISIONS.md, \"Fruit colour ramp\". Fewer than two stops fall back to a blue to orange pair.")]
    [SerializeField] private Color[] fruitColorRamp = new Color[0];
    [SerializeField] private Vector2 shapeRange = new Vector2(0f, 1f);
    [SerializeField] private Vector2 canopyWidthRange = new Vector2(2.0f, 5.0f);
    [SerializeField] private Vector2 canopyHeightRange = new Vector2(1.2f, 2.8f);
    [Tooltip("Spatial evenness of the reward over the map (scripts/spatial.py): Off = independent draws, Tiles = the (shape, color, random value) records dealt evenly over tiles at several scales, TilesAndSwaps = then swapped between bushes to lower the patchiness further. The marginal distribution of every attribute and of the reward is unchanged, only which bush has which record. Needs a reward that does not depend on moisture. Read by scripts/world.py: regenerate the world after changing it.")]
    [SerializeField] private SpatialBalance spatialBalance = SpatialBalance.Off;
    [Tooltip("Balances each visible feature (shape, color) over the map on its own, the same way for each, so every feature is evener than chance and none is more regular than the others, whether or not it pays; the reward, a sum over the features, is then also more even (not when moisture carries the weight). Off = independent draws. Tiles = dealt evenly over tiles at several scales, TilesAndSwaps = then swapped between bushes until featureBalanceTarget. Use this or spatialBalance, not both (spatialBalance evens the reward itself, which makes the rewarded feature much more regular than the others: a visible cue). Read by scripts/world.py: regenerate the world after changing it.")]
    [SerializeField] private SpatialBalance featureBalance = SpatialBalance.Off;
    [Tooltip("Deals each bush a (shape, color) pair so that the pairs cover the feature plane evenly and every part of the map gets an even sample of it (the sparse-reward experiment: a narrow peak of the reward must have bushes on it, spread over the map). Shape and color are treated alike and the reward is not used, so nothing shows which feature pays; both must vary. Off = not used. Use this, featureBalance or spatialBalance, not two of them. Read by scripts/world.py: regenerate the world after changing it.")]
    [SerializeField] private FeatureCoverage featureCoverage = FeatureCoverage.Off;
    [Tooltip("featureBalance only: how even the features become: the swaps stop when the evenness cost (1 = chance, lower = more even and more regular) reaches this. Lower looks more regular; about 0.7 gives a spread of local means of about 0.8 of chance.")]
    [SerializeField] [Range(0.3f, 1f)] private float featureBalanceTarget = 0.7f;
    [Tooltip("featureBalance only: the sizes (world units) of the tiles and disks the features are evened at; a variety keeps the evenness from showing at any one scale.")]
    [SerializeField] private float[] featureBalanceScales = { 40f, 60f, 120f, 240f };
    [Tooltip("Which world-generator stage lays out the bushes (scripts/world.py LAYOUTS). Empty = the default, the seeded hex lattice. Read by scripts/world.py: regenerate the world after changing it.")]
    [SerializeField] private string layout = "";
    [Tooltip("Which stage gives each bush its attributes (scripts/world.py ASSIGNMENTS). Empty = independent draws, or the spatially balanced assignment when spatialBalance is not Off.")]
    [SerializeField] private string assignment = "";
    [Tooltip("Which stage turns a bush's attributes into its reward (scripts/world.py REWARDS). Empty = the sum of the reward function's terms.")]
    [SerializeField] private string rewardStage = "";
    [Tooltip("What the experiment's design says about this instance (scripts/design/<code>.py): the instance id, its cell parameters and its hint arm, as JSON. Written by the experiment builder, logged with the rest of this config, read by no game code.")]
    [SerializeField] private string designJson = "";
    [Tooltip("False: every bush has the value shapeWhenFixed, so all canopies are identical; give the shape component weight 0. Read by scripts/world.py and scripts/interlude.py: regenerate the world and the Interlude after changing it.")]
    [SerializeField] private bool shapeVaries = true;
    [Tooltip("The shape value of every bush when shapeVaries is off (0..1; the canopy size then follows the shape axis). Read by scripts/world.py and scripts/interlude.py.")]
    [SerializeField] private float shapeWhenFixed = 0.5f;
    [Tooltip("False: every bush has the value colorWhenFixed, so all fruit have one color; give the color component weight 0. Read by scripts/world.py and scripts/interlude.py: regenerate the world and the Interlude after changing it.")]
    [SerializeField] private bool colorVaries = true;
    [Tooltip("The color value of every bush when colorVaries is off (0..1). Read by scripts/world.py and scripts/interlude.py.")]
    [SerializeField] private float colorWhenFixed = 0.5f;
    [Tooltip("False: the valley has one moisture value (moistureWhenFixed), so the ground is one colour and flat (elevation follows moisture), and moisture cannot pay. Read by scripts/world.py: regenerate the world after changing it.")]
    [SerializeField] private bool moistureVaries = true;
    [Tooltip("The moisture of the whole valley when moistureVaries is off (0..1).")]
    [SerializeField] private float moistureWhenFixed = 0.5f;
    [Tooltip("Declare moisture a feature of the task even though it pays nothing: scripts/interlude.py then counts it in the feature gap. Moisture that pays is always counted; with this off and a zero weight it is decoration. Read by scripts/interlude.py.")]
    [SerializeField] private bool moistureIsFeature = false;
    [Tooltip("A per-bush point value drawn uniformly from (min, max) and added to the reward function, independent of every attribute: the practice session's random reward. (0, 0) = off. Pre-drawn in the world file by scripts/world.py; an Interlude of such a session has no correct side.")]
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

    [Header("Terrain")]
    [SerializeField] private float terrainNoiseFrequency = 4f;
    [SerializeField] private int terrainNoiseOctaves = 1;
    [SerializeField] private float terrainMaxElevation = 3f;
    [Tooltip("Number of plateau levels the moisture field is snapped to (0 = smooth continuum). World-shaping: re-run scripts/world.py after changing.")]
    [SerializeField] private int moistureTerraceLevels = 0;
    [Tooltip("Ramp steepness between plateaus: 0 = gentle ramps across the whole cell, 1 = narrow ramps. Only used when moistureTerraceLevels >= 2.")]
    [SerializeField] [Range(0f, 1f)] private float moistureTerraceSharpness = 0.5f;
    [Tooltip("Amplitude (moisture units, +-) of the undulation on plateau tops. Only used when moistureTerraceLevels >= 2.")]
    [SerializeField] [Range(0f, 0.45f)] private float moistureTerraceResidual = 0f;
    [Tooltip("How uneven the plateau levels are: 0 = evenly spaced between 0 and 1, 1 = each level drawn at random within its own share of the range (the order and the full range are kept), so the plateaus are consistent regions whose values are anywhere in the continuum and differ from seed to seed. Only used when moistureTerraceLevels >= 2. Read by scripts/world.py: regenerate the world after changing it.")]
    [SerializeField] [Range(0f, 1f)] private float moistureTerraceUnevenness = 0f;
    [Header("Terrain: plateaus without a level count (read by scripts/world.py: regenerate the world after changing any of them)")]
    [Tooltip("Levels = the smooth field or moistureTerraceLevels plateaus. Staircase = a random staircase over the field's ranks. Diffusion = edge-preserving diffusion of the field. The terrace fields below are used only by Staircase and Diffusion; moistureTerraceSharpness (the ramps between staircase plateaus) and moistureTerraceResidual (the undulation on their tops) apply to Staircase and Levels, the residual also to Diffusion; terrainNoiseFrequency sets the size of the field's features (lower = larger regions).")]
    [SerializeField] private MoistureTerraceMode moistureTerraceMode = MoistureTerraceMode.Levels;
    [Tooltip("Staircase: the typical width of a plateau's band, as a share of the field's range (smaller = more, narrower plateaus; larger = fewer, broader ones).")]
    [SerializeField] [Range(0.04f, 0.6f)] private float terraceMeanWidth = 0.14f;
    [Tooltip("Staircase: how unequal the band widths are (the log spread of the draw): 0 = all alike, 1 = a few very wide plateaus and some narrow ones.")]
    [SerializeField] [Range(0f, 1.5f)] private float terraceWidthSpread = 0.7f;
    [Tooltip("Staircase: no plateau's band is wider than this share of the field's range (it caps how much of the world one plateau can take).")]
    [SerializeField] [Range(0.05f, 1f)] private float terraceMaxBand = 0.3f;
    [Tooltip("Staircase: neighbouring plateaus whose moisture differs by less than this are merged, so every step is at least this visible.")]
    [SerializeField] [Range(0f, 0.4f)] private float terraceMinStep = 0.08f;
    [Tooltip("Staircase: how far a low-frequency noise shifts the field before it is put through the staircase (in the field's rank units). 0 = plateau edges follow the field's own contours; about 0.4 lets a plateau's height vary from place to place.")]
    [SerializeField] [Range(0f, 1f)] private float terracePhaseShift = 0.4f;
    [Tooltip("Staircase: the frequency of that shifting noise (times 0.01 per world unit; lower = broader waves).")]
    [SerializeField] [Range(0.1f, 3f)] private float terracePhaseFrequency = 0.6f;
    [Tooltip("Staircase and Diffusion: how terraced the ground is. 1 = fully, 0 = the smooth field, in between a mix (gently sloping shoulders).")]
    [SerializeField] [Range(0f, 1f)] private float terraceStrength = 1f;
    [Tooltip("Diffusion: the number of smoothing steps (more = larger, flatter regions and fewer of them).")]
    [SerializeField] [Range(0, 6000)] private int terraceDiffusionIterations = 500;
    [Tooltip("Diffusion: the edge threshold as a quantile of the field's slopes. Lower keeps more of the steep edges (more, smaller plateaus); higher smooths across them.")]
    [SerializeField] [Range(0.05f, 0.95f)] private float terraceDiffusionEdge = 0.1f;
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
    public bool IsInterlude => isInterlude;
    public string InterludeFor => interludeFor;

    // The experiment this session belongs to: the part of its asset name before the first underscore (CF_S1 -> "CF"). Its generated files are
    // in StreamingAssets/Experiments/<code>/.
    public string ExperimentCode => name.Split('_')[0];
    public InterludeMode InterludeMode => interludeMode;
    public int InterludeTrialCount => interludeTrialCount;
    public int InterludeFeatureTrials => interludeFeatureTrials;
    public int InterludePeakTrials => interludePeakTrials;
    public int InterludeInteractionTrials => interludeInteractionTrials;
    public int InterludeTrialLimit => interludeTrialLimit;

    // A copy for a reduced run (RunModes.Short; never the asset itself, which would be saved into the file): a session lasts `factor` of its length, an Interlude
    // plays that fraction of its trials. The copy keeps the asset's name, which names the world and Interlude files.
    public SessionConfig ScaledCopy(float factor)
    {
        SessionConfig copy = Instantiate(this);
        copy.name = name;
        if (!isInterlude)
        {
            copy.sessionDuration = RunModes.SessionSeconds(this, factor);
        }
        else
        {
            copy.interludeTrialLimit = RunModes.InterludeTrials(this, factor);
        }

        return copy;
    }
    public float InterludeTrialSeconds => interludeTrialSeconds;
    public int InterludeHarvestFruits => interludeHarvestFruits;
    public InterludeSwitchPolicy InterludeSwitchPolicy => interludeSwitchPolicy;
    public float InterludeBonusPerCorrect => interludeBonusPerCorrect;
    public bool FreezeSun => freezeSun;
    public float InterludeBushDistance => interludeBushDistance;
    public float InterludeBushBearing => interludeBushBearing;
    public float InterludeMinElevationDifference => interludeMinElevationDifference;
    public float InterludeMinRewardGap => interludeMinRewardGap;
    public float InterludeMinFeatureGap => interludeMinFeatureGap;
    public float InterludeMaxRewardGap => interludeMaxRewardGap;
    public float InterludeMaxFeatureGap => interludeMaxFeatureGap;
    public int InterludeRepeatCount => interludeRepeatCount;
    public int InterludeRepeatSeparation => interludeRepeatSeparation;
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
    public float TreeSpacing => treeSpacing;
    public float PlacementJitter => placementJitter;
    public float StartClearingRadius => startClearingRadius;
    public int FruitCount => fruitCount;
    public float FruitRadius => fruitRadius;
    public SpatialBalance SpatialBalance => spatialBalance;
    public SpatialBalance FeatureBalance => featureBalance;
    public FeatureCoverage FeatureCoverage => featureCoverage;
    public float FeatureBalanceTarget => featureBalanceTarget;
    public float[] FeatureBalanceScales => featureBalanceScales;
    public string Layout => layout;
    public string Assignment => assignment;
    public string RewardStage => rewardStage;
    public string DesignJson => designJson;
    public bool ShapeVaries => shapeVaries;
    public float ShapeWhenFixed => shapeWhenFixed;
    public float ColorWhenFixed => colorWhenFixed;
    public bool ColorVaries => colorVaries;
    public float MoistureTerraceUnevenness => moistureTerraceUnevenness;
    public MoistureTerraceMode MoistureTerraceMode => moistureTerraceMode;
    public float TerraceMeanWidth => terraceMeanWidth;
    public float TerraceWidthSpread => terraceWidthSpread;
    public float TerraceMaxBand => terraceMaxBand;
    public float TerraceMinStep => terraceMinStep;
    public float TerracePhaseShift => terracePhaseShift;
    public float TerracePhaseFrequency => terracePhaseFrequency;
    public float TerraceStrength => terraceStrength;
    public int TerraceDiffusionIterations => terraceDiffusionIterations;
    public float TerraceDiffusionEdge => terraceDiffusionEdge;
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
    public float TerrainNoiseFrequency => terrainNoiseFrequency;
    public int TerrainNoiseOctaves => terrainNoiseOctaves;
    public float TerrainMaxElevation => terrainMaxElevation;
    public int MoistureTerraceLevels => moistureTerraceLevels;
    public float MoistureTerraceSharpness => moistureTerraceSharpness;
    public float MoistureTerraceResidual => moistureTerraceResidual;
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
