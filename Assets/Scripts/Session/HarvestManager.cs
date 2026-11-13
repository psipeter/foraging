using System;
using System.Collections.Generic;
using UnityEngine;

public enum HarvestHint
{
    None,
    Available,
    Paused
}

// One press-to-release (or press-to-exhaustion) of harvesting a single tree.
public class HarvestBout
{
    public Tree tree;
    public float timeStart;
    public float timeEnd;
    public readonly List<float> fruitRewards = new List<float>();
    public float boutTotal;
    public float runningTotal;
    public int fruitsRemaining;
    public bool exhausted;
    // Cut off because the session clock ran out (OnSessionEnd fires a frame later, so listeners can't tell otherwise).
    public bool endedBySession;
}

// Owns targeting, the graded highlight, and the hold-Space harvest. Each frame, for every tree:
//   edge distance = horizontal distance to the canopy axis minus canopy radius
//   bearing       = yaw angle between the view direction and the tree, minus the tree's angular radius
// A bush glows in proportion to (distance ramp x bearing ramp). Within the harvest range and
// the harvest cone it is harvestable; the best such bush is shown as selected and is the target of a Space press.
public class HarvestManager : MonoBehaviour
{
    public SessionConfig sessionConfig;
    [SerializeField] private PlayerController playerController;
    [SerializeField] private CameraController cameraController;
    [SerializeField] private SunController sunController;

    private Tree[] _trees;
    private float[] _levels;
    private bool[] _inRange;
    private bool _aimMode;
    private float _aimTolerance;

    private bool _harvesting;
    private Tree _target;
    private float _fruitTimer;
    private float _fruitSecondsOverride = -1f;
    private HarvestBout _bout;
    private float _runningTotal;
    private bool _highlightsCleared;
    private HarvestHint _hint = HarvestHint.None;
    private bool _targetInCone;
    private bool _blocked;
    private float _targetSignedOffAngle;
    private Vector3 _eye;                       // the camera's position and forward this frame, for the crosshair's hit test
    private Vector3 _forward;

    public static event Action<float, Vector3> OnFruitCollected;
    public static event Action<float> OnScoreChanged;
    public static event Action<HarvestBout> OnHarvestBoutEnded;
    public static event Action<HarvestHint> OnHintChanged;
    public static event Action OnBushExhausted;
    // Raised for every fruit taken, in every session kind (a ranking counts fruits to register a pick).
    public static event Action<Tree> OnFruitTaken;
    // For the DataLogger: a bout started on a tree; a fruit with its index k on that tree (0-based, in the order taken),
    // reward and the session total after it; the target entered (true) or left (false) the harvest range/cone mid-bout.
    public static event Action<Tree> OnHarvestBoutStarted;
    public static event Action<Tree, int, float, float> OnFruitRewarded;
    public static event Action<Tree, bool> OnHarvestConeChanged;

    public bool IsHarvesting => _harvesting;

    // Continuing an interrupted session: the fruits already taken per bush and the score so far (the open bout and the progress
    // on a fruit being picked are not restored; they start over).
    public void RestoreState(TreeCount[] taken, float runningTotal)
    {
        foreach (Tree tree in FindObjectsByType<Tree>(FindObjectsSortMode.None))
        {
            foreach (TreeCount count in taken)
            {
                if (count.tree == tree.treeId)
                {
                    tree.RestoreCollected(count.n);
                }
            }
        }

        _runningTotal = runningTotal;
        OnScoreChanged?.Invoke(_runningTotal);
    }

    // While blocked no bout can start and Space presses are discarded (the gap between ranking sets). The caller
    // ends any open bout first; replay mirrors the window with the trial_end / trial_go events.
    public void SetBlocked(bool blocked)
    {
        _blocked = blocked;
    }
    public int FocusTreeId { get; private set; } = -1;

    private void OnEnable()
    {
        SunController.OnSessionEnd += HandleSessionEnd;
    }

    private void OnDisable()
    {
        SunController.OnSessionEnd -= HandleSessionEnd;
    }

    private void Update()
    {
        if (playerController == null || cameraController == null || sessionConfig == null)
        {
            return;
        }

        if (sunController != null && sunController.SessionComplete)
        {
            if (_harvesting)
            {
                EndBout(true);
            }

            ClearHighlights();
            FocusTreeId = -1;
            SetHint(HarvestHint.None);
            return;
        }

        // A frame with no time (an instruction screen was up when it began) gets no trajectory row from the DataLogger,
        // so nothing may happen in it: replay re-derives harvests from the rows. A press made meanwhile stays latched
        // and is consumed on the first frame with time, which is also where replay sees its key edge.
        if (Time.deltaTime <= 0f)
        {
            return;
        }

        if (_trees == null)
        {
            // Trees are generated in TreeGenerator.Start, so they exist by the first Update.
            _trees = FindObjectsByType<Tree>(FindObjectsSortMode.None);
            _levels = new float[_trees.Length];
            _inRange = new bool[_trees.Length];
        }

        _highlightsCleared = false;

        Vector3 pos = playerController.transform.position;
        float yaw = cameraController.Yaw;
        UpdateAimRay();

        // Pass 1: glow level for every tree; pick the best harvestable one.
        int focusIndex = -1;
        float focusBearing = float.MaxValue;
        float focusEdge = float.MaxValue;
        int targetIndex = -1;

        for (int i = 0; i < _trees.Length; i++)
        {
            Tree tree = _trees[i];
            _levels[i] = 0f;
            _inRange[i] = false;
            if (tree == null || tree.isHarvested)
            {
                continue;
            }

            if (tree == _target)
            {
                targetIndex = i;
            }

            Measure(tree, pos, yaw, out float edge, out float bearing, out _);
            float harvestGap = sessionConfig.HarvestRangeGap(tree.CanopyRadius);
            float highlightGap = Mathf.Max(sessionConfig.HighlightRangeGap, harvestGap + 0.01f);
            float fullAngle = sessionConfig.HighlightFullAngle;
            float fadeAngle = Mathf.Max(sessionConfig.HighlightFadeAngle, fullAngle + 0.01f);

            float distLevel = _aimMode ? 1f : Smooth(Mathf.InverseLerp(highlightGap, harvestGap, edge));
            float angleLevel = 1f - Smooth(Mathf.InverseLerp(fullAngle, fadeAngle, bearing));
            _levels[i] = _aimMode ? 0f : distLevel * angleLevel;        // aiming: only the bush being aimed at is marked (below)

            if (_aimMode || edge <= harvestGap)
            {
                if (UseCrosshair)
                {
                    // the crosshair's circle must touch the canopy; of the bushes it touches, the nearest is the target
                    if (Aimed(tree, sessionConfig.CrosshairRadius))
                    {
                        _inRange[i] = true;
                        if (edge < focusEdge)
                        {
                            focusIndex = i;
                            focusEdge = edge;
                        }
                    }
                }
                else if (bearing <= HarvestAngle)
                {
                    _inRange[i] = true;
                    if (bearing < focusBearing || (Mathf.Approximately(bearing, focusBearing) && edge < focusEdge))
                    {
                        focusIndex = i;
                        focusBearing = bearing;
                        focusEdge = edge;
                    }
                }
            }
        }

        bool pressed = playerController.ConsumeHarvestPress();

        if (!_harvesting)
        {
            if (pressed && !_blocked && playerController.HarvestHeld && focusIndex >= 0)
            {
                StartBout(_trees[focusIndex]);
                targetIndex = focusIndex;
            }
        }
        else if (!_aimMode && !playerController.HarvestHeld)        // aiming: a bout started is finished, whatever the key does (a ranking's commitment)
        {
            EndBout();
            targetIndex = -1;
        }

        if (_harvesting)
        {
            AdvanceHarvest(pos, yaw);
            if (!_harvesting)
            {
                targetIndex = -1;
            }
        }

        // Pass 2: apply highlights. Only the bush you would harvest (or are harvesting) is selected.
        FocusTreeId = _harvesting ? _target.treeId : (focusIndex >= 0 ? _trees[focusIndex].treeId : -1);
        for (int i = 0; i < _trees.Length; i++)
        {
            Tree tree = _trees[i];
            if (tree == null)
            {
                continue;
            }

            bool pulsing = _harvesting ? (i == targetIndex && _targetInCone) : (i == focusIndex);
            tree.SetHighlight(pulsing ? 1f : _levels[i], pulsing, _aimMode);

            // Progress ring on every bush in harvest range (and the one being harvested): remaining fraction,
            // counting the fruit in progress so it ticks down smoothly.
            bool showRing = !tree.isHarvested && (_aimMode ? (i == focusIndex || i == targetIndex) : (_inRange[i] || i == targetIndex));
            float fill = 0f;
            if (showRing)
            {
                float partial = i == targetIndex ? _fruitTimer : tree.PartialProgress;
                float perFruit = Mathf.Max(FruitSeconds, 0.0001f);
                fill = (tree.FruitsRemaining - Mathf.Clamp01(partial / perFruit)) / Mathf.Max(1, tree.FruitCount);
            }

            tree.SetRing(showRing, fill, cameraController.PlayerCamera != null ? cameraController.PlayerCamera.transform : null, _aimMode ? sessionConfig.RankingMarkerLift : 0f);
        }

        if (_harvesting)
        {
            SetHint(_targetInCone ? HarvestHint.None : HarvestHint.Paused);
        }
        else
        {
            SetHint(focusIndex >= 0 ? HarvestHint.Available : HarvestHint.None);
        }
    }

    private void StartBout(Tree tree)
    {
        _harvesting = true;
        _target = tree;
        _fruitTimer = tree.PartialProgress;
        _targetInCone = true;
        _bout = new HarvestBout
        {
            tree = tree,
            timeStart = SessionTimeRemaining()
        };
        playerController.SetMovementLocked(true);
        OnHarvestBoutStarted?.Invoke(tree);
    }

    private void AdvanceHarvest(Vector3 pos, float yaw)
    {
        Measure(_target, pos, yaw, out float edge, out float bearing, out float signedBearing);
        float harvestGap = sessionConfig.HarvestRangeGap(_target.CanopyRadius);
        bool wasInCone = _targetInCone;
        // (the crosshair rule: the circle grown by crosshairReleaseScale still touches the bush; the old rule: the cone)
        _targetInCone = _aimMode || (edge <= harvestGap && (UseCrosshair ? Aimed(_target, sessionConfig.CrosshairRadius * Mathf.Max(sessionConfig.CrosshairReleaseScale, 1f)) : bearing <= HarvestAngle));       // aiming: the crosshair may leave the bush, the harvest goes on
        _targetSignedOffAngle = _aimMode ? 0f : signedBearing;                             // (and the view is not held to it)
        if (_targetInCone != wasInCone)
        {
            OnHarvestConeChanged?.Invoke(_target, _targetInCone);
        }

        if (!_targetInCone)
        {
            return;
        }

        _fruitTimer += Time.deltaTime;
        float perFruit = Mathf.Max(FruitSeconds, 0.0001f);
        while (_fruitTimer >= perFruit && _harvesting)
        {
            _fruitTimer -= perFruit;
            CollectNextFruit();
        }
    }

    private void CollectNextFruit()
    {
        Vector3 cameraPos = cameraController.PlayerCamera != null
            ? cameraController.PlayerCamera.transform.position
            : playerController.transform.position;
        int index = _target.NextFruitIndexTowards(cameraPos);
        if (index < 0)
        {
            ExhaustTarget();
            return;
        }

        // Per-fruit rewards are pre-drawn in the world file (independent per fruit; reproducible from the seed).
        int storedReward = _target.NextFruitReward();
        float fruitReward;
        if (storedReward >= 0)
        {
            fruitReward = storedReward;
        }
        else
        {
            float bushReward = _target.Evaluate(sessionConfig.RewardFunction);
            fruitReward = Mathf.Max(0f, Mathf.RoundToInt(bushReward + GaussianNoise() * sessionConfig.RewardStd));
        }

        Vector3 worldPos = _target.GetFruitWorldPosition(index);
        int fruitOrder = _target.FruitCount - _target.FruitsRemaining;
        _target.CollectFruit(index, sessionConfig.FruitPopDuration);

        _runningTotal += fruitReward;
        OnFruitRewarded?.Invoke(_target, fruitOrder, fruitReward, _runningTotal);
        _bout.fruitRewards.Add(fruitReward);
        _bout.boutTotal += fruitReward;

        OnFruitTaken?.Invoke(_target);

        // Events fire in every session kind. In a ranking the consumers hide the outcome (no +X popup or score; the
        // pick sound plays at a fixed pitch, see HarvestUI and FeedbackAudio).
        OnFruitCollected?.Invoke(fruitReward, worldPos);
        OnScoreChanged?.Invoke(_runningTotal);

        if (_target.FruitsRemaining == 0)
        {
            ExhaustTarget();
        }
    }

    // All fruit gone: the bush stays but eases into its spent look, and the bout ends.
    private void ExhaustTarget()
    {
        _target.isHarvested = true;
        _target.PartialProgress = 0f;
        _target.MarkSpent();
        OnBushExhausted?.Invoke();
        EndBout();
    }

    private void EndBout(bool bySession = false)
    {
        if (!_harvesting)
        {
            return;
        }

        _harvesting = false;
        playerController.SetMovementLocked(false);

        if (_target != null && !_target.isHarvested)
        {
            _target.PartialProgress = _fruitTimer;
        }

        _bout.timeEnd = SessionTimeRemaining();
        _bout.runningTotal = _runningTotal;
        _bout.fruitsRemaining = _target != null ? _target.FruitsRemaining : 0;
        _bout.exhausted = _target != null && _target.isHarvested;
        _bout.endedBySession = bySession;
        HarvestBout finished = _bout;

        _bout = null;
        _target = null;
        _fruitTimer = 0f;
        OnHarvestBoutEnded?.Invoke(finished);
    }

    // A ranking swaps which bushes are active between sets: stop any harvest first, then call this so the
    // next Update re-finds the active trees.
    public void RefreshTrees()
    {
        _trees = null;
    }

    // Ranking: the player stands still and picks by aiming; a harvest started (Space pressed on the bush aimed at) runs to the bush's last fruit whatever the
    // key and the crosshair do afterwards (the commitment: the rank of a bush is the order of starting and of finishing alike). The harvest range is ignored (any bush in view can be harvested) and the
    // crosshair must be within `toleranceDegrees` of the canopy's edge (0 = inside the canopy) instead of HarvestMaxAngle; the progress ring is
    // shown only on the bush aimed at or harvested, the rank number replacing it once the bush is finished). scripts/replay.py and scripts/visibility.py mirror this rule.
    public void SetAimMode(bool on, float toleranceDegrees)
    {
        _aimMode = on;
        _aimTolerance = toleranceDegrees;
    }

    // Seconds per fruit: the session's, or the ranking break's quick harvest while it overrides it (SetFruitSeconds; below 0 clears it).
    private float FruitSeconds => _fruitSecondsOverride > 0f ? _fruitSecondsOverride : sessionConfig.FruitHarvestDuration;

    public void SetFruitSeconds(float seconds)
    {
        _fruitSecondsOverride = seconds;
    }

    private bool UseCrosshair => sessionConfig.CrosshairRadius > 0f;

    // The camera's position and forward (from the view's yaw and pitch, + pitch = down, as scripts/replay.py rebuilds them from the log).
    private void UpdateAimRay()
    {
        Camera cam = cameraController.PlayerCamera;
        _eye = cam != null ? cam.transform.position : playerController.transform.position;
        float yaw = cameraController.Yaw * Mathf.Deg2Rad;
        float pitch = cameraController.Pitch * Mathf.Deg2Rad;
        _forward = new Vector3(Mathf.Sin(yaw) * Mathf.Cos(pitch), -Mathf.Sin(pitch), Mathf.Cos(yaw) * Mathf.Cos(pitch));
    }

    // True when the view ray passes within `radiusDegrees` of the bush's canopy: the ray meets the canopy's ellipsoid (horizontal radius, half the height vertically, centred on
    // the ground) grown by distance x tan(radius), the width of the circle at the bush. scripts/replay.py mirrors this.
    private bool Aimed(Tree tree, float radiusDegrees)
    {
        Vector3 centre = tree.GetWorldCenter();
        float grow = (_eye - centre).magnitude * Mathf.Tan(radiusDegrees * Mathf.Deg2Rad);
        var radii = new Vector3(tree.CanopyRadius + grow, tree.CanopyHalfHeight + grow, tree.CanopyRadius + grow);
        Vector3 p = Vector3.Scale(_eye - centre, new Vector3(1f / radii.x, 1f / radii.y, 1f / radii.z));
        Vector3 q = Vector3.Scale(_forward, new Vector3(1f / radii.x, 1f / radii.y, 1f / radii.z));
        float a = Vector3.Dot(q, q);
        float b = Vector3.Dot(p, q);
        float c = Vector3.Dot(p, p) - 1f;
        float discriminant = b * b - a * c;
        return discriminant >= 0f && (-b + Mathf.Sqrt(discriminant)) / a > 0f;
    }

    private float HarvestAngle => _aimMode ? _aimTolerance : sessionConfig.HarvestMaxAngle;

    public void CancelBout()
    {
        EndBout();
    }

    // Signed yaw offset (degrees, + = bush to the right of the view) of the bush being harvested, with its
    // angular radius removed from the magnitude. False when not harvesting. Used for look resistance.
    public bool TryGetHarvestOffAngle(out float signedOffAngle)
    {
        signedOffAngle = _targetSignedOffAngle;
        return _harvesting && _target != null;
    }

    private static void Measure(Tree tree, Vector3 playerPos, float yawDegrees, out float edgeDistance, out float bearing, out float signedBearing)
    {
        Vector3 center = tree.GetWorldCenter();
        float dx = center.x - playerPos.x;
        float dz = center.z - playerPos.z;
        float dist = Mathf.Sqrt(dx * dx + dz * dz);
        float radius = tree.CanopyRadius;
        edgeDistance = dist - radius;

        float toTree = Mathf.Atan2(dx, dz) * Mathf.Rad2Deg;
        float delta = Mathf.DeltaAngle(yawDegrees, toTree);
        float angularRadius = dist > 0.0001f ? Mathf.Asin(Mathf.Clamp01(radius / dist)) * Mathf.Rad2Deg : 90f;
        bearing = Mathf.Max(0f, Mathf.Abs(delta) - angularRadius);
        signedBearing = Mathf.Sign(delta) * bearing;
    }

    private static float Smooth(float t)
    {
        t = Mathf.Clamp01(t);
        return t * t * (3f - 2f * t);
    }

    private float SessionTimeRemaining()
    {
        return sunController != null ? sunController.SessionTimeRemaining : Time.time;
    }

    private void SetHint(HarvestHint hint)
    {
        if (!sessionConfig.ShowHarvestHint)
        {
            hint = HarvestHint.None;
        }

        if (hint == _hint)
        {
            return;
        }

        _hint = hint;
        OnHintChanged?.Invoke(hint);
    }

    private void ClearHighlights()
    {
        if (_highlightsCleared || _trees == null)
        {
            return;
        }

        _highlightsCleared = true;
        for (int i = 0; i < _trees.Length; i++)
        {
            if (_trees[i] != null)
            {
                _trees[i].SetHighlight(0f, false);
            }
        }
    }

    private void HandleSessionEnd()
    {
        EndBout();
    }

    private float GaussianNoise()
    {
        float u1 = 1f - UnityEngine.Random.value;
        float u2 = 1f - UnityEngine.Random.value;
        return Mathf.Sqrt(-2f * Mathf.Log(u1)) * Mathf.Sin(2f * Mathf.PI * u2);
    }
}
