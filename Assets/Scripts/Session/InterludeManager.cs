using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.UI;

// Runs an Interlude: a short forced-choice block after a session, in that session's own world (terrain, mountains,
// sun) with only two bushes present at a time. The bush table and the trials come from scripts/interlude.py
// (WorldData swaps them in for the session's bushes). The player turns toward the bush they think pays more, walks
// to it and harvests it until interludeHarvestFruits fruits are taken. Unless interludeSwitchPolicy is Allow, the bush whose
// harvest the player starts is the choice from that moment (commitment) and the other bush is taken away (Hide, the default),
// spent (Exhaust) or locked, so the player cannot switch; the trial still ends when the chosen bush has been harvested (or on
// the time limit). With Allow the first bush to reach the fruit count is the choice. Outcomes are never
// shown (HarvestManager suppresses reward feedback in an Interlude). A trial ends on a
// choice or after interludeTrialSeconds, and every choice is logged to interlude.csv. Correct choices add a hidden
// bonus that is shown only on the final screen.
//
// An Interlude is an ordinary session kind (SessionConfig.isInterlude), so the sun, terrain, bushes, harvesting,
// instruction screen, data logger and end screen all run as in any session; this component only drives the trials.
[DefaultExecutionOrder(30)]
public class InterludeManager : MonoBehaviour
{
    [Serializable]
    private class Bush
    {
        public int id;
        public float shape;
        public float color;
        public float moisture;
        public float value;
    }

    [Serializable]
    private class Trial
    {
        public int index;
        public string type;
        public string varied;
        public float[] start;
        public float yaw;
        public string correct;
        public float deltaValue;
        public Bush left;
        public Bush right;
    }

    [Serializable]
    private class TrialFile
    {
        public string session;
        public string interludeFor;
        public int seed;
        public int n;
        public Trial[] trials;
    }

    private enum State
    {
        Waiting,
        Running,
        Transition,
        Finished
    }

    public SessionConfig sessionConfig;
    public HarvestUI harvestUI;
    public DataLogger dataLogger;

    [SerializeField] private PlayerController player;
    [SerializeField] private CameraController cameraController;
    [SerializeField] private HarvestManager harvestManager;
    [SerializeField] private SunController sunController;
    [Tooltip("Seconds to fade to and from black between trials.")]
    [SerializeField] private float fadeSeconds = 0.25f;
    [Tooltip("Seconds held at black between trials, so the next bushes are in place before the view returns.")]
    [SerializeField] private float blackHoldSeconds = 0.2f;
    [Tooltip("Seconds the bush that was not chosen takes to shrink away (policy Hide).")]
    [SerializeField] private float hideSeconds = 0.4f;

    private State _state = State.Waiting;
    private Trial[] _order;
    private Tree[] _treesById;
    private int _position = -1;
    private Trial _trial;
    private float _clock;
    private readonly int[] _fruits = new int[2];
    private int _choice = -1;
    private bool _completed;
    private float _lockTime = -1f;
    private float _choiceTime;
    private float _firstHarvestTime = -1f;
    private int _firstHarvestSide = -1;
    private Image _fade;
    private string _csvPath;

    // True once the trials are loaded and running; SessionTimerUI shows TimerLabel instead of the session clock.
    public bool Active => _order != null && _state != State.Finished;

    public string TimerLabel
    {
        get
        {
            float total = sessionConfig != null ? sessionConfig.InterludeTrialSeconds : 7f;
            int seconds = Mathf.CeilToInt(Mathf.Clamp(total - _clock, 0f, total));
            return $"00:{seconds:D2}";
        }
    }

    private void OnEnable()
    {
        HarvestManager.OnFruitTaken += HandleFruitTaken;
        HarvestManager.OnHarvestBoutStarted += HandleBoutStarted;
    }

    private void OnDisable()
    {
        HarvestManager.OnFruitTaken -= HandleFruitTaken;
        HarvestManager.OnHarvestBoutStarted -= HandleBoutStarted;
    }

    private void Start()
    {
        if (sessionConfig == null || !sessionConfig.IsInterlude)
        {
            enabled = false;
            return;
        }

        GameManager.BeginInterludeTally();

        TrialFile file = LoadTrials();
        if (file == null || file.trials == null || file.trials.Length == 0)
        {
            Debug.LogError("InterludeManager: no trials loaded; generate them with scripts/interlude.py.");
            enabled = false;
            return;
        }

        // Presentation order is shuffled per participant; the file order is fixed. A participant continuing an interrupted
        // Interlude gets the order they had (from the server), and the trials they had finished are counted again.
        ResumeReply resume = ResumeInfo.MidSession(GameManager.CurrentSessionIndex) ? ResumeInfo.Pending : null;
        _order = resume != null ? OrderFromPlan(file.trials, resume.interlude_plan) : null;
        if (_order == null)
        {
            resume = null;
            _order = (Trial[])file.trials.Clone();
            var rng = new System.Random();
            for (int i = _order.Length - 1; i > 0; i--)
            {
                int j = rng.Next(i + 1);
                (_order[i], _order[j]) = (_order[j], _order[i]);
            }

            // The shuffled order is part of the data (and what a resume must restore).
            dataLogger?.LogInterludePlan(Array.ConvertAll(_order, trial => trial.index));
        }

        Tree[] all = FindObjectsByType<Tree>(FindObjectsSortMode.None);
        int max = 0;
        foreach (Tree tree in all)
        {
            max = Mathf.Max(max, tree.treeId);
        }

        _treesById = new Tree[max + 1];
        foreach (Tree tree in all)
        {
            if (tree.treeId >= 0)
            {
                _treesById[tree.treeId] = tree;
            }
        }

        BuildFadeOverlay();
        int first = 0;
        if (resume != null)
        {
            first = Mathf.Min(resume.trial_rows.Length, _order.Length);
            if (!sessionConfig.IsPractice)
            {
                foreach (TrialTally done in resume.trial_rows)
                {
                    GameManager.RecordInterludeTrial(done.correct == 1, done.bonus);
                }
            }
        }

        if (first >= _order.Length)
        {
            // Every trial was finished before the session was closed: show the end screen.
            _position = _order.Length - 1;
            _trial = _order[_position];
            StartCoroutine(Complete());
            return;
        }

        BeginTrial(first);
    }

    // The trials in the order of a logged plan (trial indices), or null when the plan does not match the trial file.
    private static Trial[] OrderFromPlan(Trial[] trials, int[] plan)
    {
        if (plan == null || plan.Length != trials.Length)
        {
            return null;
        }

        var byIndex = new Dictionary<int, Trial>();
        foreach (Trial trial in trials)
        {
            byIndex[trial.index] = trial;
        }

        var order = new Trial[plan.Length];
        for (int i = 0; i < plan.Length; i++)
        {
            if (!byIndex.TryGetValue(plan[i], out order[i]))
            {
                return null;
            }
        }

        return order;
    }

    private TrialFile LoadTrials()
    {
        string path = WorldData.InterludePathFor(sessionConfig);
        if (!StreamingData.Exists(path))
        {
            Debug.LogError($"Interlude trial file not found: {path}");
            return null;
        }

        try
        {
            return JsonUtility.FromJson<TrialFile>(StreamingData.ReadText(path));
        }
        catch (Exception e)
        {
            Debug.LogError($"Failed to read {path}: {e}");
            return null;
        }
    }

    // Shows only this trial's two bushes, puts the player at the stage spawn facing them, and resets the trial state.
    private void BeginTrial(int position)
    {
        _position = position;
        _trial = _order[position];

        foreach (Tree tree in _treesById)
        {
            if (tree != null)
            {
                tree.gameObject.SetActive(tree.treeId == _trial.left.id || tree.treeId == _trial.right.id);
            }
        }

        harvestManager.RefreshTrees();
        player.TeleportTo(_trial.start[0], _trial.start[1]);
        float pitch = PitchTowardsPair();
        cameraController.SetView(_trial.yaw, pitch);
        if (dataLogger != null)
        {
            dataLogger.LogEvent("teleport", payload: Json.Obj(("x", _trial.start[0]), ("z", _trial.start[1]), ("yaw", _trial.yaw), ("pitch", pitch)));
            dataLogger.LogEvent("trial_start", payload: Json.Obj(("order", position), ("trial", _trial.index), ("left", _trial.left.id), ("right", _trial.right.id)));
        }

        _fruits[0] = _fruits[1] = 0;
        _choice = -1;
        _completed = false;
        _lockTime = -1f;
        _firstHarvestTime = -1f;
        _firstHarvestSide = -1;
        _clock = 0f;

        if (harvestUI != null)
        {
            harvestUI.SetProgressText($"{position + 1}/{_order.Length}");
        }
    }

    // Pitch (degrees, + = looking down) that puts the middle of the two bushes' visible canopies on the view's horizontal
    // centre line, from the eye position at the stage spawn. The yaw (from the trial file) already faces their midpoint.
    private float PitchTowardsPair()
    {
        Camera cam = cameraController.PlayerCamera;
        Tree left = _trial.left.id >= 0 && _trial.left.id < _treesById.Length ? _treesById[_trial.left.id] : null;
        Tree right = _trial.right.id >= 0 && _trial.right.id < _treesById.Length ? _treesById[_trial.right.id] : null;
        if (cam == null || left == null || right == null)
        {
            return 0f;
        }

        Vector3 eye = cam.transform.position;
        Vector3 mid = (left.GetVisibleCenter() + right.GetVisibleCenter()) * 0.5f;
        float horizontal = Mathf.Sqrt((mid.x - eye.x) * (mid.x - eye.x) + (mid.z - eye.z) * (mid.z - eye.z));
        float pitch = Mathf.Atan2(eye.y - mid.y, Mathf.Max(horizontal, 0.01f)) * Mathf.Rad2Deg;
        return Mathf.Clamp(pitch, -sessionConfig.LookPitchLimit, sessionConfig.LookPitchLimit);
    }

    private void Update()
    {
        switch (_state)
        {
            case State.Waiting:
                // The instruction screen holds Time.timeScale at 0; the first trial's clock starts when it closes.
                if (Time.timeScale > 0f)
                {
                    _state = State.Running;
                }

                break;

            case State.Running:
                if (Time.timeScale <= 0f)
                {
                    break;
                }

                _clock += Time.deltaTime;
                if (_firstHarvestTime < 0f && harvestManager.IsHarvesting)
                {
                    _firstHarvestTime = _clock;
                    _firstHarvestSide = harvestManager.FocusTreeId == _trial.left.id ? 0 : 1;
                }

                if (_completed)
                {
                    harvestManager.CancelBout();
                    Finish(false);
                }
                else if (_clock >= sessionConfig.InterludeTrialSeconds)
                {
                    harvestManager.CancelBout();
                    Finish(true);
                }

                break;
        }
    }

    // Commitment: starting to harvest a bush chooses it (unless the policy is Allow) and takes the other bush away.
    private void HandleBoutStarted(Tree tree)
    {
        InterludeSwitchPolicy policy = sessionConfig != null ? sessionConfig.InterludeSwitchPolicy : InterludeSwitchPolicy.Allow;
        if (policy == InterludeSwitchPolicy.Allow || _state != State.Running || tree == null || _trial == null || _choice >= 0)
        {
            return;
        }

        int side = tree.treeId == _trial.left.id ? 0 : (tree.treeId == _trial.right.id ? 1 : -1);
        if (side < 0)
        {
            return;
        }

        _choice = side;
        _lockTime = _clock;
        int otherId = side == 0 ? _trial.right.id : _trial.left.id;
        Tree other = otherId >= 0 && otherId < _treesById.Length ? _treesById[otherId] : null;
        if (other != null)
        {
            switch (policy)
            {
                case InterludeSwitchPolicy.Hide:
                    other.ShrinkAwayAndHide(hideSeconds);
                    break;
                case InterludeSwitchPolicy.Exhaust:
                    other.MarkSpent();
                    break;
                default:
                    other.isHarvested = true;
                    break;
            }
        }

        if (dataLogger != null)
        {
            dataLogger.LogEvent("choice_lock", tree.treeId, payload: Json.Obj(("committed", tree.treeId), ("locked", otherId), ("policy", policy.ToString())));
        }
    }

    // A fruit counts toward the bush it came from; the first bush to reach the required count completes the trial (and,
    // under Allow, is the choice).
    private void HandleFruitTaken(Tree tree)
    {
        if (_state != State.Running || tree == null || _trial == null)
        {
            return;
        }

        int side = tree.treeId == _trial.left.id ? 0 : (tree.treeId == _trial.right.id ? 1 : -1);
        if (side < 0)
        {
            return;
        }

        _fruits[side]++;
        if (!_completed && _fruits[side] >= sessionConfig.InterludeHarvestFruits)
        {
            _completed = true;
            _choiceTime = _clock;
            if (_choice < 0)
            {
                _choice = side;
            }
        }
    }

    private void Finish(bool timedOut)
    {
        // A committed choice counts even when the clock runs out before the bush is finished.
        bool correct = _choice >= 0 && (_trial.correct == "either"
                                        || (_choice == 0 && _trial.correct == "left")
                                        || (_choice == 1 && _trial.correct == "right"));
        float bonus = correct && !sessionConfig.IsPractice ? sessionConfig.InterludeBonusPerCorrect : 0f;
        if (!sessionConfig.IsPractice)
        {
            GameManager.RecordInterludeTrial(correct, bonus);
        }

        WriteRow(timedOut, correct, bonus);
        if (dataLogger != null)
        {
            string side = _choice == 0 ? "left" : (_choice == 1 ? "right" : "none");
            dataLogger.LogEvent("trial_end", payload: Json.Obj(("choice", side), ("correct", correct ? 1 : 0), ("timed_out", timedOut ? 1 : 0)));
        }

        // No harvest may start between trials (during the fade a press would take fruit outside any trial and the bout
        // would carry into the next one).
        harvestManager.SetBlocked(true);
        _state = State.Transition;
        StartCoroutine(_position + 1 < _order.Length ? TransitionTo(_position + 1) : Complete());
    }

    private IEnumerator TransitionTo(int next)
    {
        player.SetFrozen(true);
        yield return Fade(0f, 1f);
        BeginTrial(next);
        yield return new WaitForSecondsRealtime(blackHoldSeconds);
        yield return Fade(1f, 0f);
        player.SetFrozen(false);
        harvestManager.SetBlocked(false);
        if (dataLogger != null)
        {
            // The end of the harvest block: replay ignores presses from the trial's end up to and including this frame.
            dataLogger.LogEvent("trial_go");
        }

        _state = State.Running;
    }

    private IEnumerator Complete()
    {
        player.SetFrozen(true);
        yield return new WaitForSecondsRealtime(0.2f);
        _state = State.Finished;
        sunController.EndSession();
    }

    private IEnumerator Fade(float from, float to)
    {
        float t = 0f;
        float seconds = Mathf.Max(fadeSeconds, 0.01f);
        while (t < seconds)
        {
            t += Time.unscaledDeltaTime;
            SetFade(Mathf.Lerp(from, to, t / seconds));
            yield return null;
        }

        SetFade(to);
    }

    private void SetFade(float alpha)
    {
        if (_fade != null)
        {
            _fade.color = new Color(0f, 0f, 0f, alpha);
        }
    }

    private void BuildFadeOverlay()
    {
        Canvas canvas = harvestUI != null ? harvestUI.GetComponent<Canvas>() : null;
        if (canvas == null)
        {
            return;
        }

        var go = new GameObject("InterludeFade", typeof(RectTransform), typeof(Image));
        RectTransform rect = go.GetComponent<RectTransform>();
        rect.SetParent(canvas.transform, false);
        rect.anchorMin = Vector2.zero;
        rect.anchorMax = Vector2.one;
        rect.offsetMin = Vector2.zero;
        rect.offsetMax = Vector2.zero;
        _fade = go.GetComponent<Image>();
        _fade.raycastTarget = false;
        SetFade(0f);
    }

    // One interlude_trials row, in TrialRow.Columns order.
    private void WriteRow(bool timedOut, bool correct, float bonus)
    {
        if (dataLogger == null)
        {
            return;
        }

        string choice = _choice == 0 ? "left" : (_choice == 1 ? "right" : "none");
        string firstSide = _firstHarvestSide == 0 ? "left" : (_firstHarvestSide == 1 ? "right" : "none");
        float response = timedOut ? sessionConfig.InterludeTrialSeconds : _choiceTime;
        var cells = new List<string>
        {
            _position.ToString(), _trial.index.ToString(), _trial.type, _trial.varied, F(_trial.start[0]), F(_trial.start[1]),
        };
        AddBush(cells, _trial.left);
        AddBush(cells, _trial.right);
        cells.Add(_trial.correct);
        cells.Add(choice);
        cells.Add(correct ? "1" : "0");
        cells.Add(timedOut ? "1" : "0");
        cells.Add(F(response));
        cells.Add(_firstHarvestTime < 0f ? "" : F(_firstHarvestTime));
        cells.Add(firstSide);
        cells.Add(_fruits[0].ToString());
        cells.Add(_fruits[1].ToString());
        cells.Add(F(bonus));
        cells.Add(_lockTime < 0f ? "" : F(_lockTime));
        dataLogger.LogTrial(cells.ToArray());
    }

    private static void AddBush(List<string> cells, Bush b)
    {
        cells.Add(b.id.ToString());
        cells.Add(F(b.shape));
        cells.Add(F(b.color));
        cells.Add(F(b.moisture));
        cells.Add(F(b.value));
    }

    private static string F(float value)
    {
        return value.ToString("0.####", CultureInfo.InvariantCulture);
    }
}
