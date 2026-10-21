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

    private bool _harvesting;
    private Tree _target;
    private float _fruitTimer;
    private HarvestBout _bout;
    private float _runningTotal;
    private bool _highlightsCleared;
    private HarvestHint _hint = HarvestHint.None;
    private bool _targetInCone;
    private float _targetSignedOffAngle;

    public static event Action<float, Vector3> OnFruitCollected;
    public static event Action<float> OnScoreChanged;
    public static event Action<HarvestBout> OnHarvestBoutEnded;
    public static event Action<HarvestHint> OnHintChanged;
    public static event Action OnBushExhausted;
    // Raised for every fruit taken, in every session kind (the Interlude counts fruits to register a choice).
    public static event Action<Tree> OnFruitTaken;

    public bool IsHarvesting => _harvesting;
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
                EndBout();
            }

            ClearHighlights();
            FocusTreeId = -1;
            SetHint(HarvestHint.None);
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

            float distLevel = Smooth(Mathf.InverseLerp(highlightGap, harvestGap, edge));
            float angleLevel = 1f - Smooth(Mathf.InverseLerp(fullAngle, fadeAngle, bearing));
            _levels[i] = distLevel * angleLevel;

            if (edge <= harvestGap && bearing <= sessionConfig.HarvestMaxAngle)
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

        bool pressed = playerController.ConsumeHarvestPress();

        if (!_harvesting)
        {
            if (pressed && playerController.HarvestHeld && focusIndex >= 0)
            {
                StartBout(_trees[focusIndex]);
                targetIndex = focusIndex;
            }
        }
        else if (!playerController.HarvestHeld)
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
            tree.SetHighlight(pulsing ? 1f : _levels[i], pulsing);

            // Progress ring on every bush in harvest range (and the one being harvested): remaining fraction,
            // counting the fruit in progress so it ticks down smoothly.
            bool showRing = !tree.isHarvested && (_inRange[i] || i == targetIndex);
            float fill = 0f;
            if (showRing)
            {
                float partial = i == targetIndex ? _fruitTimer : tree.PartialProgress;
                float perFruit = Mathf.Max(sessionConfig.FruitHarvestDuration, 0.0001f);
                fill = (tree.FruitsRemaining - Mathf.Clamp01(partial / perFruit)) / Mathf.Max(1, tree.FruitCount);
            }

            tree.SetRing(showRing, fill, cameraController.PlayerCamera != null ? cameraController.PlayerCamera.transform : null);
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
    }

    private void AdvanceHarvest(Vector3 pos, float yaw)
    {
        Measure(_target, pos, yaw, out float edge, out float bearing, out float signedBearing);
        float harvestGap = sessionConfig.HarvestRangeGap(_target.CanopyRadius);
        _targetInCone = edge <= harvestGap && bearing <= sessionConfig.HarvestMaxAngle;
        _targetSignedOffAngle = signedBearing;

        if (!_targetInCone)
        {
            return;
        }

        _fruitTimer += Time.deltaTime;
        float perFruit = Mathf.Max(sessionConfig.FruitHarvestDuration, 0.0001f);
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
        _target.CollectFruit(index, sessionConfig.FruitPopDuration);

        _runningTotal += fruitReward;
        _bout.fruitRewards.Add(fruitReward);
        _bout.boutTotal += fruitReward;

        OnFruitTaken?.Invoke(_target);

        // Events fire in every session kind. In an Interlude the consumers hide the outcome (no +X popup or score; the
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

    private void EndBout()
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
        HarvestBout finished = _bout;

        _bout = null;
        _target = null;
        _fruitTimer = 0f;
        OnHarvestBoutEnded?.Invoke(finished);
    }

    // The Interlude swaps which bushes are active between trials: stop any harvest first, then call this so the
    // next Update re-finds the active trees.
    public void RefreshTrees()
    {
        _trees = null;
    }

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
